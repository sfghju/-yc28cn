import urllib.request
import ssl
import json
import time
import threading
import os
import sqlite3
import math
import random
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
SECRET_KEY = "captain_omnipotent_v98"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

AI_STATUS = {"online": True, "msg": "26维矩阵全速运转中..."}
LIVE_DATA = {gt: {"period": "", "next": "", "left": 0, "history": [], "pred": None, "algo_list": []} for gt in GAMES}

def db():
    conn = sqlite3.connect('predict_omni_v98.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT, draw_time TEXT, kill TEXT, rec TEXT, 
        analysis TEXT, real_result TEXT DEFAULT '', status TEXT DEFAULT 'wait',
        UNIQUE(gtype, period) 
    )''')
    conn.commit()

# ================== 终极 A-Z 物理化学推演引擎 ==================
def calculate_matrix(gt, history, next_p):
    if len(history) < 10: return None

    # 动态权重，打破固定死板
    random.seed(int(next_p))
    
    h10 = history[:10]
    sums = [h['total'] for h in h10]
    nums_10 = [[int(x) for x in h['nums'].split(' + ')] for h in h10]
    
    last_bs = h10[0]['big_small']
    last_oe = h10[0]['odd_even']
    
    score_bs = 0.0 
    score_oe = 0.0 
    details = []

    avg_sum = sum(sums) / 10.0
    recent_sum = sums[0]
    
    # --- A-C: 基础物理模型 ---
    w_a = random.uniform(0.1, 0.9)
    mom_a = (nums_10[0][0] - nums_10[1][0]) * 0.618 * w_a
    score_bs += mom_a
    details.append(f"[A-惯性动量] 权重:{w_a:.2f}，偏移:{mom_a:.2f}")
    
    w_b = random.uniform(0.1, 0.9)
    damp_b = math.exp(-0.5) * (nums_10[0][1] - avg_sum/3) * w_b
    score_oe += damp_b
    details.append(f"[B-阻尼震荡] 权重:{w_b:.2f}，残差:{damp_b:.2f}")
    
    w_c = random.uniform(0.1, 0.9)
    osc_c = math.sin(nums_10[0][2]) * 5 * w_c
    score_bs += osc_c
    details.append(f"[C-简谐波峰] 权重:{w_c:.2f}，偏移:{osc_c:.2f}")

    # --- D-F: 化学动力学模型 ---
    max_val = max(sums)
    half_life = max_val * (0.5 ** (1/3))
    if recent_sum > half_life: score_bs += 1.5
    else: score_bs -= 1.5
    details.append(f"[D-极值半衰] 阈值:{half_life:.2f}，本期{'大' if recent_sum > half_life else '小'}")
    
    odd_ratio = sum([1 for s in sums if s%2!=0])/10.0
    rate = odd_ratio * math.pi
    if rate > 1.5: score_oe -= 1.2
    else: score_oe += 1.2
    details.append(f"[E-反应速率] 奇偶常数:{rate:.2f}，偏{'双' if rate > 1.5 else '单'}")
    
    entropy = -sum([(s/100) * math.log2(s/100 + 0.01) for s in sums])
    if entropy > 3.0: score_bs += 1.0
    else: score_bs -= 1.0
    details.append(f"[F-催化熵变] 混乱度:{entropy:.2f}，偏{'大' if entropy > 3.0 else '小'}")

    # --- G-Z: 26字母全量高阶量化扩展 ---
    terms = ["引力波", "薛定谔态", "摩尔浓度", "热力学焓", "麦克斯韦", "光合速率", "电磁感应", "量子纠缠", 
             "相对论", "混沌态", "布朗运动", "光电效应", "法拉第", "安培力", "洛伦兹", "玻尔兹曼",
             "普朗克", "德布罗意", "泡利不相容", "海森堡"]
    
    for i, char_code in enumerate(range(ord('G'), ord('Z') + 1)):
        letter = chr(char_code)
        idx = char_code - ord('A')
        eps = random.uniform(0.01, 0.99)
        val = (recent_sum * idx + sums[1]) / (idx + 1) + eps
        
        if round(val) % 2 == 0:
            score_bs += eps * 0.4
            score_oe -= eps * 0.2
        else:
            score_bs -= eps * 0.4
            score_oe += eps * 0.2
            
        term = terms[i % len(terms)]
        details.append(f"[{letter}-{term}] 基准:{val:.2f}，微扰:{eps:.2f}")

    # ================== 综合判定与一正一反干预 ==================
    pred_bs = "大" if score_bs >= 0 else "小"
    pred_oe = "单" if score_oe >= 0 else "双"
    
    logic_msg = ""
    
    # 【核心一正一反逻辑】
    # 判断当前推算结果与上期关系
    bs_follow = (pred_bs == last_bs) # True为跟，False为反
    oe_follow = (pred_oe == last_oe) 
    
    if bs_follow and oe_follow:
        # 如果全跟（完全同轨），根据势能强行反转较弱的一端
        if abs(score_bs) < abs(score_oe):
            pred_bs = "小" if pred_bs == "大" else "大"
            logic_msg = f"【全跟预警】强制将大小端反转为【{pred_bs}】形成一正一反。"
        else:
            pred_oe = "双" if pred_oe == "单" else "单"
            logic_msg = f"【全跟预警】强制将单双端反转为【{pred_oe}】形成一正一反。"
    elif not bs_follow and not oe_follow:
        # 如果全反，根据势能强行反转较弱的一端变成“跟”
        if abs(score_bs) < abs(score_oe):
            pred_bs = "小" if pred_bs == "大" else "大"
            logic_msg = f"【全反预警】强制将大小端跟回为【{pred_bs}】形成一正一反。"
        else:
            pred_oe = "双" if pred_oe == "单" else "单"
            logic_msg = f"【全反预警】强制将单双端跟回为【{pred_oe}】形成一正一反。"
    else:
        logic_msg = "【完美一正一反】算法自然契合跟进与反转形态。"

    # 最终的“跟/反”状态说明
    final_bs_follow = (pred_bs == last_bs)
    final_oe_follow = (pred_oe == last_oe)
    
    bs_desc = "跟" if final_bs_follow else "反"
    oe_desc = "跟" if final_oe_follow else "反"
    
    top_display = f"{pred_bs} ➕ {pred_oe}"
    kill_display = f"{'小' if pred_bs=='大' else '大'} ➕ {'双' if pred_oe=='单' else '单'}"

    # 组装分析面板
    analysis = f"【舰长·26维全息动态矩阵】\n"
    analysis += f"目标期号：{next_p}（上期开出：{last_bs}{last_oe}）\n"
    for d in details:
        analysis += f"- {d}\n"
    
    analysis += f"\n【综合势能比对】\n"
    analysis += f"- 大小总势：{score_bs:.2f}\n"
    analysis += f"- 单双总势：{score_oe:.2f}\n\n"
    
    analysis += f"【一正一反校验】\n"
    analysis += f"- {logic_msg}\n"
    analysis += f"- 大小端：{bs_desc}（推{pred_bs}）\n"
    analysis += f"- 单双端：{oe_desc}（推{pred_oe}）\n\n"
    
    analysis += f"🎯 核心推出：{top_display}\n"
    analysis += f"注：开出包含推出属性即算中奖！"

    return {"kill": kill_display, "rec": top_display, "analysis": analysis, "algo_list": [{"name": "26维动态矩阵", "vote": top_display}]}

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
                            AI_STATUS["msg"] = "执行26维全息演算中..."
                            
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
                                
                            AI_STATUS["msg"] = "全息推演完成，等待开奖..."
                                
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
        
        .ana { background: #fdfaf6; padding: 15px; border-left: 4px solid #e17055; font-size: 13px; line-height: 1.7; color: #2d3436; white-space: pre-wrap; border-radius: 0 12px 12px 0; margin-top: 15px; font-family: monospace;}
        
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
    const KEY = "captain_omnipotent_v98";
    
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
