import urllib.request
import ssl
import json
import time
import threading
import os
import sqlite3
import hashlib
import random
from collections import Counter
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
SECRET_KEY = "captain_final_v81"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

AI_STATUS = {"online": True, "msg": "双向强制变化推演中..."}
LIVE_DATA = {gt: {"period": "", "next": "", "left": 0, "history": [], "pred": None, "algo_list": []} for gt in GAMES}

# 记录上期的预测，用于防死板
LAST_PRED_STR = {"2": "", "3": "", "13": ""}

def db():
    conn = sqlite3.connect('predict_final_v81.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT, draw_time TEXT, kill TEXT, rec TEXT, 
        analysis TEXT, real_result TEXT DEFAULT '', status TEXT DEFAULT 'wait',
        UNIQUE(gtype, period) 
    )''')
    conn.commit()

# ================== 50套算法引擎 ==================
def run_single_algo(aid, history):
    if len(history) < 10: return "数据不足"
    sums = [h['total'] for h in history]
    bs = [1 if h['big_small'] == '大' else 0 for h in history]
    oe = [1 if h['odd_even'] == '单' else 0 for h in history]
    
    is_follow = aid <= 25
    model_id = (aid % 5) if is_follow else ((aid - 25) % 5)
    param = aid // 5
    
    push_bs, push_oe = 1, 1 
    
    if model_id == 0:
        w = 3 + (param % 5)
        ma = sum(sums[:w]) / w
        push_bs = (1 if ma >= 13.5 else 0) if is_follow else (0 if ma >= 13.5 else 1)
        push_oe = (1 if ma % 2 >= 1 else 0) if is_follow else (0 if ma % 2 >= 1 else 1)
    elif model_id == 1:
        w = 3 + (param % 4)
        ma = sum(sums[:w]) / w
        dev = sums[0] - ma
        push_bs = (1 if dev > 0 else 0) if is_follow else (0 if dev > 0 else 1)
        push_oe = oe[0] if is_follow else 1 - oe[0]
    elif model_id == 2:
        threshold = 2 + (param % 3)
        streak = 1
        for i in range(1, threshold+1):
            if bs[i] == bs[0]: streak += 1
            else: break
        pred = bs[0] if streak < threshold else 1 - bs[0]
        push_bs = pred if is_follow else 1 - pred
        push_oe = oe[0]
    elif model_id == 3:
        w = 2 + (param % 4)
        mom = sums[0] - sums[w]
        pred = 1 if mom > 0 else 0
        push_bs = pred if is_follow else 1 - pred
        push_oe = pred 
    else:
        w = 3 + (param % 3)
        ups = sum([1 for i in range(w) if sums[i] > sums[i+1]])
        pred = 1 if ups >= w/2 else 0
        push_bs = pred if is_follow else 1 - pred
        push_oe = (0 if ups == w else (1 if ups == 0 else pred)) if is_follow else (1 if ups == w else (0 if ups == 0 else 1-pred))

    return ("大" if push_bs == 1 else "小") + ("单" if push_oe == 1 else "双")

# ================== 强制变向与共识引擎 ==================
def calculate_matrix(gt, history, next_p):
    if len(history) < 10: return None

    # 使用真实毫秒级时间作为种子
    random.seed(int(time.time() * 1000) + int(next_p))
    
    algo_stats = []
    for aid in range(1, 51):
        pred_now = run_single_algo(aid, history)
        win_cnt = 0; curr_streak = 0; curr_type = ""
        
        for i in range(10):
            if i+1 >= len(history): break
            p = run_single_algo(aid, history[i+1:])
            r_bs, r_oe = history[i]['big_small'], history[i]['odd_even']
            if (r_bs == p[0] or r_oe == p[1]):
                win_cnt += 1; curr_streak = curr_streak + 1 if curr_type == "win" else 1; curr_type = "win"
            else:
                curr_streak = 0; curr_type = "lose"

        algo_stats.append({
            "id": aid, "pred": pred_now, "win": win_cnt, 
            "streak": curr_streak if curr_type == "win" else 0
        })

    # 排序并强制去重（允许算法连续出场，但预测属性必须不同）
    algo_stats.sort(key=lambda x: (x['streak'], x['win']), reverse=True)
    
    unique_pool = []
    seen_preds = set()
    for a in algo_stats:
        if a['pred'] not in seen_preds:
            unique_pool.append(a)
            seen_preds.add(a['pred'])

    final_group = unique_pool[:5]
    if len(final_group) < 5:
        for a in algo_stats:
            if a not in final_group:
                final_group.append(a)
                if len(final_group) == 5: break

    # 共识裁决
    votes = Counter([a['pred'] for a in final_group])
    top_combo, count = votes.most_common(1)[0]
    
    final_pred = top_combo if count >= 3 else final_group[0]['pred']
    consensus_msg = f"【{count}票共识】" if count >= 3 else "【强制主帅裁决】"

    # 【核心逻辑：强制变化防死板】
    # 如果这期推出来的组合跟上期一模一样，强行把大小或单双翻转
    if final_pred == LAST_PRED_STR[gt]:
        # 翻转大小
        flipped_bs = '小' if final_pred[0] == '大' else '大'
        final_pred = flipped_bs + final_pred[1]
        consensus_msg += " (检测到连续重复，强制反向纠偏)"

    LAST_PRED_STR[gt] = final_pred

    top_display = f"{final_pred[0]} ➕ {final_pred[1]}"
    kill_display = f"{'小' if final_pred[0]=='大' else '大'} ➕ {'双' if final_pred[1]=='单' else '单'}"

    top5_details = "\n".join([f"- 算法{a['id']}: 连中{a['streak']}期，近10对{a['win']}，推【{a['pred']}】" for a in final_group])

    analysis = f"【舰长·终极结论机制】\n"
    analysis += f"严格筛选 50 套算法，本期出战阵容：\n{top5_details}\n\n"
    analysis += f"逻辑判定：{consensus_msg}\n"
    analysis += f"🎯 最终结论：坚决主推【{top_display}】\n"
    analysis += f"注：开出包含推出属性即算中奖！"

    return {"kill": kill_display, "rec": top_display, "analysis": analysis, "algo_list": final_group}

# ================== 极速抓取主循环 ==================
def fetch_loop():
    ctx = ssl._create_unverified_context()
    while True:
        for gt, cfg in GAMES.items():
            try:
                req = urllib.request.Request(f"{cfg['url']}&_={int(time.time()*1000)}", headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                    data = json.loads(resp.read().decode('utf-8')).get('data')
                    if data:
                        latest = data[0]
                        history = [{"period": i['period'], "nums": f"{i['num1']} + {i['num2']} + {i['num3']}", "total": i['total'], "big_small": i['big_small'], "odd_even": i['odd_even']} for i in data[:30]]
                        
                        if LIVE_DATA[gt]['period'] != latest['period']:
                            AI_STATUS["msg"] = "双向强制变化演算中..."
                            
                            if LIVE_DATA[gt]['period'] != "" and LIVE_DATA[gt]['pred']:
                                real_bs, real_oe = latest['big_small'], latest['odd_even']
                                real_full = real_bs + real_oe
                                prev_rec = LIVE_DATA[gt]['pred']['rec']
                                p_bs, p_oe = prev_rec.replace(" ➕ ", "")
                                status = 'win' if (real_bs == p_bs or real_oe == p_oe) else 'lose'
                                
                                with db() as conn:
                                    conn.execute("UPDATE logs SET real_result=?, status=? WHERE gtype=? AND period=?", (real_full, status, gt, latest['period']))
                                    conn.commit()

                            dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            next_p = str(int(latest['period'])+1)
                            LIVE_DATA[gt].update({
                                "period": latest['period'], "next": next_p, 
                                "target_time": (dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])).timestamp(), 
                                "history": history
                            })
                            
                            pred = calculate_matrix(gt, history, next_p)
                            if pred:
                                LIVE_DATA[gt]['pred'] = pred
                                LIVE_DATA[gt]['algo_list'] = pred['algo_list']
                                
                                with db() as conn:
                                    conn.execute('''INSERT OR IGNORE INTO logs (gtype, period, draw_time, kill, rec, analysis) VALUES (?,?,?,?,?,?)''', 
                                                 (gt, next_p, latest['draw_time'], pred["kill"], pred["rec"], pred["analysis"]))
                                    conn.commit()
                                
                            AI_STATUS["msg"] = "结论已出，等待开奖..."
                                
                        LIVE_DATA[gt]['left'] = max(0, int(LIVE_DATA[gt]['target_time'] - datetime.utcnow().timestamp()))
            except Exception: pass
        time.sleep(0.1)

threading.Thread(target=fetch_loop, daemon=True).start()

# ================== API 接口 ==================
def verify(): return request.headers.get('X-Token') == SECRET_KEY

@app.route('/api/data/<gt>')
def api_data(gt):
    if not verify(): return "<h1>Access Denied</h1>", 403
    return jsonify({"status": AI_STATUS, "data": LIVE_DATA.get(gt, {})})

@app.route('/api/logs/<gt>')
def api_logs(gt):
    if not verify(): return "<h1>Access Denied</h1>", 403
    with db() as conn:
        logs = conn.execute("SELECT * FROM logs WHERE gtype=? GROUP BY period ORDER BY id DESC", (gt,)).fetchall()
        settled = [l['status'] for l in logs if l['status'] in ('win', 'lose')]
        stats = {
            "current_win": 0, "current_lose": 0, 
            "total_win": settled.count('win'), "total_lose": settled.count('lose'),
            "total_pred": len(logs)
        }
        
        for st in settled:
            if st == 'win': 
                if stats['current_lose'] > 0: break 
                stats['current_win'] += 1
            else: 
                if stats['current_win'] > 0: break
                stats['current_lose'] += 1
    return jsonify({"logs": [dict(l) for l in logs], "stats": stats})

@app.route('/api/clear/<gt>', methods=['POST'])
def api_clear(gt):
    if not verify(): return jsonify({"ok": False})
    with db() as conn:
        conn.execute("DELETE FROM logs WHERE gtype=?", (gt,))
        conn.commit()
    LAST_PRED_STR[gt] = ""
    return jsonify({"ok": True})

@app.route('/')
def index():
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>舰长预测</title>
    <style>
        * { box-sizing: border-box; }
        body { background: #f4f6f9; margin: 0; font-family: -apple-system, sans-serif; color: #333; }
        .head { background: #0b0f19; color: #fff; padding: 15px; text-align: center; font-size: 20px; font-weight: bold; }
        .status { text-align: center; padding: 10px; font-size: 14px; background: #fff; border-bottom: 1px solid #eaeaea; font-weight: bold; display: flex; justify-content: center; align-items: center;}
        .dot { width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; background: #00b894; box-shadow: 0 0 8px #00b894; animation: p 1.5s infinite;} 
        @keyframes p { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
        .tabs { display: flex; padding: 10px; gap: 10px; background: #fff; border-bottom: 1px solid #f1f2f6;}
        .tab { flex: 1; padding: 10px; text-align: center; background: #f0f2f5; border-radius: 8px; font-weight: bold; font-size: 14px; cursor: pointer; }
        .tab.on { background: #0984e3; color: #fff; }
        .stats-bar { display: flex; background: #fff; margin: 12px; padding: 12px 10px; border-radius: 12px; font-size: 13px; font-weight: bold; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.03);}
        .stats-item { flex: 1; border-right: 1px solid #f1f2f6;}
        .stats-item:last-child { border-right: none; }
        .stats-val { display: block; font-size: 20px; margin-top: 4px;}
        .card { background: #fff; margin: 12px; padding: 15px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .title { font-size: 14px; font-weight: bold; margin-bottom: 10px; color: #2d3436;}
        .history { display: flex; overflow-x: auto; gap: 10px; padding-bottom: 5px; }
        .h-item { background: #f8f9fa; padding: 10px; border-radius: 8px; min-width: 95px; text-align: center; border: 1px solid #eee;}
        .h-period { color: #b2bec3; font-size: 11px;}
        .h-nums { color: #636e72; font-size: 12px; margin: 4px 0; }
        .h-total { color: #d63031; font-weight: bold; font-size: 16px; }
        .res-push { padding: 25px; border-radius: 12px; text-align: center; font-size: 36px; font-weight: 900; letter-spacing: 2px; color: #0984e3; background: #e8f4f8; border: 1px solid #b2d8ef; margin-top: 10px; }
        .cd-box { text-align: center; font-size: 14px; color: #636e72; margin-bottom: 10px;}
        .cd { font-size: 22px; color: #0984e3; font-weight: bold; }
        .cd.analyzing { color: #d63031; font-size: 20px; animation: flash 0.5s infinite alternate;}
        @keyframes flash { 0% { opacity: 0.4; } 100% { opacity: 1; } }
        .ana { background: #fdfaf6; padding: 15px; border-left: 4px solid #e17055; font-size: 14px; line-height: 1.7; color: #2d3436; white-space: pre-wrap; border-radius: 0 12px 12px 0; margin-top: 15px;}
        
        .log-item { border-bottom: 1px solid #f1f2f6; padding: 12px 0; font-size: 13px; display: flex; justify-content: space-between; }
        .win { color: #00b894; font-weight: bold; } .lose { color: #d63031; font-weight: bold; }
        .btn-clear { float:right; font-size:12px; padding:5px 10px; border:1px solid #d63031; color:#d63031; border-radius:6px;}
        .log-scroll { max-height: 400px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="head">舰长预测</div>
    <div class="status" id="status"><span class="dot"></span> 系统运转正常</div>
    <div class="tabs">
        <div class="tab on" onclick="switchG('2', this)">加拿大28</div>
        <div class="tab" onclick="switchG('3', this)">分分28</div>
        <div class="tab" onclick="switchG('13', this)">比特28</div>
    </div>
    
    <div class="stats-bar">
        <div class="stats-item">当前连中<span class="stats-val win" id="st-cw" style="color:#00b894;">0</span></div>
        <div class="stats-item">当前连错<span class="stats-val lose" id="st-cl" style="color:#d63031;">0</span></div>
        <div class="stats-item">总命中<span class="stats-val win" id="st-tw" style="color:#00b894;">0</span></div>
        <div class="stats-item">总被杀<span class="stats-val lose" id="st-tl" style="color:#d63031;">0</span></div>
        <div class="stats-item">累计预测<span class="stats-val" id="st-tp" style="color:#0984e3;">0</span></div>
    </div>

    <div class="card">
        <div class="title">近 30 期 独立盘面</div>
        <div class="history" id="history"></div>
    </div>
    
    <div class="card" id="pred-box" style="display:none">
        <div class="title">目标拦截: <span id="next-period" style="color:#0984e3;"></span></div>
        <div class="res-push">🎯 推出：<span id="rec-item"></span></div>
        <div class="cd-box" style="margin-top:20px;">状态: <span class="cd" id="cd">--:--</span></div>
        <div class="ana" id="ana"></div>
    </div>
    
    <div class="card">
        <div class="title">历史复盘 <button class="btn-clear" onclick="clearLogs()">清空</button></div>
        <div id="logs" class="log-scroll"></div>
    </div>
    
<script>
    let curG = '2', timer = null;
    const KEY = "captain_final_v81";
    
    function switchG(g, el) {
        curG = g;
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
        el.classList.add('on');
        document.getElementById('pred-box').style.display = 'none';
        fetchData(); fetchLogs();
    }

    function fetchData() {
        fetch(`/api/data/${curG}`, { headers: {'X-Token': KEY} }).then(r => r.json()).then(res => {
            let d = res.data, st = res.status;
            document.getElementById('status').innerHTML = `<span class="dot" style="background:${st.online ? '#00b894' : '#d63031'}"></span> ${st.msg}`;
            if(!d.period) return;
            
            document.getElementById('history').innerHTML = d.history.map(h => `
                <div class="h-item"><div class="h-period">${h.period.slice(-4)}期</div>
                <div class="h-nums">${h.nums}</div><div class="h-total">${h.total}</div>
                <div>${h.big_small}${h.odd_even}</div></div>`).join('');

            if(d.pred) {
                document.getElementById('pred-box').style.display = 'block';
                document.getElementById('next-period').innerText = d.next;
                document.getElementById('rec-item').innerText = d.pred.rec;
                document.getElementById('ana').innerText = d.pred.analysis;
            }
            
            if(timer) clearInterval(timer);
            let left = d.left || 0, cdEl = document.getElementById('cd');
            
            if(left <= 0) {
                cdEl.innerText = "极速共识分析中...";
                cdEl.className = 'cd analyzing';
                setTimeout(fetchData, 100); 
                return;
            } else {
                cdEl.className = 'cd';
            }
            
            timer = setInterval(() => {
                if(left <= 0) { clearInterval(timer); fetchData(); return; }
                left--;
                cdEl.innerText = `${Math.floor(left/60).toString().padStart(2,'0')}:${(left%60).toString().padStart(2,'0')}`;
                if (left <= 3) cdEl.className = 'cd analyzing'; else cdEl.className = 'cd';
            }, 1000);
        });
    }
    
    function fetchLogs() {
        fetch(`/api/logs/${curG}`, { headers: {'X-Token': KEY} }).then(r => r.json()).then(res => {
            document.getElementById('st-cw').innerText = res.stats.current_win;
            document.getElementById('st-cl').innerText = res.stats.current_lose;
            document.getElementById('st-tw').innerText = res.stats.total_win;
            document.getElementById('st-tl').innerText = res.stats.total_lose;
            document.getElementById('st-tp').innerText = res.stats.total_pred;
            
            document.getElementById('logs').innerHTML = res.logs.map(l => `
                <div class="log-item">
                    <div>
                        <div style="color:#b2bec3; font-size:12px;">${l.period} | ${l.draw_time || '---'}</div>
                        <div style="margin-top:4px;">推:<span style="color:#0984e3; font-weight:bold;">${l.rec}</span></div>
                    </div>
                    <div style="text-align:right">
                        <div class="${l.status === 'win' ? 'win' : (l.status === 'lose' ? 'lose' : '')}">
                            ${l.status === 'win' ? '🀄 命中' : (l.status === 'lose' ? '💀 被杀' : '⏳ 等待')}
                        </div>
                        <div style="color:#b2bec3; font-size:12px;">${l.real_result ? `(实开:${l.real_result})` : ''}</div>
                    </div>
                </div>`).join('') || '<div style="text-align:center; padding:20px;">暂无记录</div>';
        });
    }
    
    function clearLogs() {
        if(!confirm("清空所有记录？")) return;
        fetch(`/api/clear/${curG}`, { method: 'POST', headers: {'X-Token': KEY} }).then(() => fetchLogs());
    }
    
    fetchData(); fetchLogs();
    setInterval(fetchLogs, 3000);
</script>
</body>
</html>
    """

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8888))
    app.run(host='0.0.0.0', port=port)
