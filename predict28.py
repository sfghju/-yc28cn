import urllib.request
import ssl
import json
import time
import threading
import os
import sqlite3
import re
import random
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
SECRET_KEY = "ultimate_strict10_v26"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

AI_STATUS = {"online": True, "msg": "极速监控中..."}
LIVE_DATA = {gt: {"period": "", "next": "", "left": 0, "history": [], "pred": None, "algo_list": []} for gt in GAMES}

LAST_KILL_STR = {"2": "", "3": "", "13": ""}

def db():
    conn = sqlite3.connect('predict_strict10_v26.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT, draw_time TEXT, kill TEXT, rec TEXT, 
        analysis TEXT, real_result TEXT DEFAULT '', status TEXT DEFAULT 'wait')''')
    conn.commit()

ALGO_NAMES = {i: f"策略算法{i:03d}" for i in range(1, 101)}

# ================== 算法计算库 ==================
def run_single_algo(algo_id, h7, period, game_type):
    bs = [1 if h['big_small'] == '大' else 0 for h in h7]
    oe = [1 if h['odd_even'] == '单' else 0 for h in h7]
    sums = [h['total'] for h in h7]
    big_cnt, odd_cnt = sum(bs), sum(oe)
    
    random.seed(algo_id + int(period) + (13 if game_type == "13" else (3 if game_type == "3" else 2)))
    score_bs = big_cnt - 3.5 + random.uniform(-1.2, 1.2)
    score_oe = odd_cnt - 3.5 + random.uniform(-1.2, 1.2)
    
    if 1 <= algo_id <= 25: 
        if bs[0] == 1: score_bs *= 1.5
        if oe[0] == 1: score_oe *= 1.5
    elif 26 <= algo_id <= 50: 
        if big_cnt >= 4: score_bs = -score_bs * 1.8
        if odd_cnt >= 4: score_oe = -score_oe * 1.8
    elif 51 <= algo_id <= 75: 
        if sums[0] > 15: score_bs -= 1.0
        if sums[0] < 12: score_bs += 1.0
    elif 76 <= algo_id <= 100: 
        if algo_id in [86, 98]: score_bs = -score_bs; score_oe = -score_oe
    return ("大" if score_bs >= 0 else "小") + ("单" if score_oe >= 0 else "双")

# ================== 核心预测与防重逻辑 ==================
def calculate_dynamic_prediction(gt, history, next_p):
    h20 = history[:20]
    scores = {i: 0.0 for i in range(1, 101)}
    
    for i in range(5):
        test_h = h20[i : i+7]
        if len(test_h) < 7: continue
        real_res = test_h[0]['big_small'] + test_h[0]['odd_even']
        for aid in range(1, 101):
            pred = run_single_algo(aid, test_h[1:7], int(next_p) - i - 1, gt)
            if pred == real_res: scores[aid] += 1
            else: scores[aid] -= 1

    sorted_algos = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    offset = {"2": 0, "3": 20, "13": 40}[gt]
    
    core_10 = [aid for aid, sc in sorted_algos[offset : offset+10]]
    pool_strict = [aid for aid, sc in sorted_algos[offset+10 : offset+30]]
    strict_10 = pool_strict[:10]
    
    selected_algos = core_10 + strict_10

    votes = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
    algo_records = []
    for aid in selected_algos:
        res = run_single_algo(aid, history[:7], next_p, gt)
        votes[res] += 1
        algo_records.append({"id": aid, "name": ALGO_NAMES[aid], "vote": res, "score": scores[aid]})

    sorted_v = sorted(votes.items(), key=lambda x: x[1], reverse=True)
    
    main_atk = sorted_v[0][0] 
    defend = sorted_v[1][0]   
    kill_str = sorted_v[2][0] 
    backup = sorted_v[3][0]   
    
    if kill_str == LAST_KILL_STR[gt]:
        kill_str = backup  
        backup = sorted_v[2][0]
        if kill_str == LAST_KILL_STR[gt]:
            kill_str = defend
            defend = sorted_v[2][0]
            
    LAST_KILL_STR[gt] = kill_str

    analysis = f"【严格考核模型】本期由 10 名连任主力 + 10 名严格考核的新锐算法出战。\n主攻指向【{main_atk}】({votes[main_atk]}票)；\n防守布置于【{defend}】({votes[defend]}票)；\n【防重机制启动】坚决规避，本期绝杀【{kill_str}】！"
    return {"kill": kill_str, "rec": f"{main_atk}(主攻)、{defend}(防守)、{backup}(备选)", "analysis": analysis, "algo_list": algo_records}

# ================== 抓取主循环 ==================
def fetch_loop():
    ctx = ssl._create_unverified_context()
    while True:
        for gt, cfg in GAMES.items():
            try:
                # 加毫秒级时间戳，彻底粉碎缓存
                req_url = f"{cfg['url']}&_={int(time.time()*1000)}"
                req = urllib.request.Request(req_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    if data.get('data'):
                        latest = data['data'][0]
                        history = [{"period": i['period'], "nums": f"{i['num1']} + {i['num2']} + {i['num3']}", "total": i['total'], "big_small": i['big_small'], "odd_even": i['odd_even']} for i in data['data'][:20]]
                        
                        if LIVE_DATA[gt]['period'] != latest['period']:
                            if LIVE_DATA[gt]['period'] != "" and LIVE_DATA[gt]['pred']:
                                real = latest['big_small'] + latest['odd_even']
                                p_kill = LIVE_DATA[gt]['pred']['kill']
                                with db() as conn:
                                    status = 'win' if real != p_kill else 'lose'
                                    conn.execute("UPDATE logs SET real_result=?, status=? WHERE gtype=? AND period=?", (real, status, gt, latest['period']))
                                    conn.commit()

                            dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            next_p = str(int(latest['period'])+1)
                            LIVE_DATA[gt].update({
                                "period": latest['period'], "next": next_p,
                                "target_time": (dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])).timestamp(), 
                                "history": history
                            })

                            pred = calculate_dynamic_prediction(gt, history, next_p)
                            LIVE_DATA[gt]['pred'] = pred
                            LIVE_DATA[gt]['algo_list'] = pred['algo_list']
                            
                            with db() as conn:
                                conn.execute('''INSERT INTO logs (gtype, period, draw_time, kill, rec, analysis) VALUES (?,?,?,?,?,?)''', 
                                             (gt, LIVE_DATA[gt]['next'], latest['draw_time'], pred["kill"], pred["rec"], pred["analysis"]))
                                conn.commit()
                                
                        diff = LIVE_DATA[gt]['target_time'] - datetime.utcnow().timestamp()
                        LIVE_DATA[gt]['left'] = max(0, int(diff))
                                
            except Exception as e:
                pass
        time.sleep(0.1) # 极端提速：0.1 秒扫描一次接口

threading.Thread(target=fetch_loop, daemon=True).start()

# ================== API 与 前端 ==================
def verify(): return request.headers.get('X-Token') == SECRET_KEY

@app.route('/api/data/<gt>')
def api_data(gt):
    if not verify(): return "<h1>Access Denied</h1>", 403
    return jsonify({"status": AI_STATUS, "data": LIVE_DATA.get(gt, {})})

@app.route('/api/logs/<gt>')
def api_logs(gt):
    if not verify(): return "<h1>Access Denied</h1>", 403
    with db() as conn:
        logs = conn.execute("SELECT * FROM logs WHERE gtype=? ORDER BY id DESC", (gt,)).fetchall()
        stats = {"current_win": 0, "current_lose": 0, "total_win": 0, "total_lose": 0}
        settled = [l['status'] for l in logs if l['status'] in ('win', 'lose')]
        for st in settled:
            if st == 'win': stats['total_win'] += 1
            elif st == 'lose': stats['total_lose'] += 1
        for st in settled:
            if st == 'win': 
                if stats['current_lose'] > 0: break 
                stats['current_win'] += 1
            elif st == 'lose':
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
    <title>极速同步实战预测</title>
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
        .stats-bar { display: flex; background: #fff; margin: 12px; padding: 10px; border-radius: 12px; font-size: 13px; font-weight: bold; text-align: center;}
        .stats-item { flex: 1; border-right: 1px solid #f1f2f6;}
        .stats-item:last-child { border-right: none; }
        .stats-val { display: block; font-size: 18px; margin-top: 4px;}
        .card { background: #fff; margin: 12px; padding: 15px; border-radius: 12px; }
        .title { font-size: 14px; font-weight: bold; margin-bottom: 10px; color: #2d3436;}
        .history { display: flex; overflow-x: auto; gap: 10px; padding-bottom: 5px; }
        .h-item { background: #f8f9fa; padding: 10px; border-radius: 8px; min-width: 95px; text-align: center; border: 1px solid #eee;}
        .h-period { color: #b2bec3; font-size: 11px;}
        .h-nums { color: #636e72; font-size: 12px; margin: 4px 0; }
        .h-total { color: #d63031; font-weight: bold; font-size: 16px; }
        .kill { color: #d63031; font-size: 22px; font-weight: 900; text-align: center; margin: 10px 0; background: #fff5f5; padding: 12px; border-radius: 8px; }
        .rec-main { color: #fff; background: #e17055; font-size: 22px; font-weight: bold; text-align: center; margin-bottom: 10px; padding: 15px; border-radius: 8px; }
        .rec-other { display: flex; gap: 10px; margin-bottom: 15px;}
        .rec-def { flex: 1; color: #0984e3; background: #e8f4f8; font-size: 16px; font-weight: bold; text-align: center; padding: 12px; border-radius: 8px;}
        .rec-bak { flex: 1; color: #636e72; background: #f1f2f6; font-size: 16px; font-weight: bold; text-align: center; padding: 12px; border-radius: 8px;}
        
        /* 优化倒计时体验 */
        .cd-box { text-align: center; font-size: 14px; color: #636e72; margin-bottom: 10px; display: flex; align-items: center; justify-content: center;}
        .cd { font-size: 22px; color: #0984e3; font-weight: bold; margin-left: 5px;}
        .cd.danger { color: #d63031; animation: flash 0.5s infinite alternate;}
        @keyframes flash { 0% { opacity: 0.4; } 100% { opacity: 1; } }
        
        .ana { background: #fdfaf6; padding: 15px; border-left: 4px solid #e17055; font-size: 14px; line-height: 1.7; color: #2d3436; white-space: pre-wrap; }
        
        .api-list { display: none; background: #222f3e; color: #c8d6e5; margin: 12px; padding: 15px; border-radius: 12px; font-family: monospace; font-size: 12px; max-height: 400px; overflow-y: auto; }
        .api-title { color: #feca57; font-weight: bold; margin-bottom: 10px; font-size: 14px; position: sticky; top: 0; background: #222f3e; padding-bottom: 5px; border-bottom: 1px solid #576574; z-index: 10;}
        .api-row { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px dashed #2c3e50; }
        .api-row span.red { color: #ff6b6b; font-weight: bold; }

        .log-item { border-bottom: 1px solid #f1f2f6; padding: 10px 0; font-size: 13px; display: flex; justify-content: space-between; }
        .win { color: #00b894; font-weight: bold; } .lose { color: #d63031; font-weight: bold; }
        .btn-clear { float:right; font-size:12px; padding:5px 10px; border:1px solid #d63031; color:#d63031; border-radius:6px;}
        .log-scroll { max-height: 400px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="head">极速同步实战预测</div>
    <div class="status" id="status"><span class="dot"></span> 系统运转正常</div>
    <div class="tabs">
        <div class="tab on" onclick="switchG('2', this)">加拿大28</div>
        <div class="tab" onclick="switchG('3', this)">分分28</div>
        <div class="tab" onclick="switchG('13', this)">比特28</div>
    </div>
    
    <div class="stats-bar">
        <div class="stats-item">当前连中<span class="stats-val win" id="st-cw">0</span></div>
        <div class="stats-item">当前连错<span class="stats-val lose" id="st-cl">0</span></div>
        <div class="stats-item">总命中<span class="stats-val win" id="st-tw">0</span></div>
        <div class="stats-item">总被杀<span class="stats-val lose" id="st-tl">0</span></div>
    </div>

    <div class="api-list" id="api-box">
        <div class="api-title" id="api-title">📡 严格筛选出的 20 套算法明细</div>
        <div id="api-content"></div>
    </div>

    <div class="card">
        <div class="title">近 20 期 独立盘面</div>
        <div class="history" id="history"></div>
    </div>
    <div class="card" id="pred-box" style="display:none">
        <div class="title">目标拦截: <span id="next-period" style="color:#0984e3;"></span></div>
        <div class="kill">🚫 高危绝杀: <span id="kill-item"></span></div>
        <div class="rec-main">🔥 核心主攻: <span id="main-item"></span></div>
        <div class="rec-other">
            <div class="rec-def">🛡️ 重点防守: <span id="def-item"></span></div>
            <div class="rec-bak">🎯 战术备选: <span id="bak-item"></span></div>
        </div>
        <div class="cd-box">状态: <span class="cd" id="cd">--:--</span></div>
        <div class="ana" id="ana"></div>
    </div>
    <div class="card">
        <div class="title">历史复盘 <button class="btn-clear" onclick="clearLogs()">清空</button></div>
        <div id="logs" class="log-scroll"></div>
    </div>
<script>
    let curG = '2', timer = null;
    const KEY = "ultimate_strict10_v26";
    
    function switchG(g, el) {
        curG = g;
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
        el.classList.add('on');
        document.getElementById('pred-box').style.display = 'none';
        fetchData(); fetchLogs();
    }

    function fetchData() {
        fetch(`/api/data/${curG}`, { headers: {'X-Token': KEY} }).then(r => r.json()).then(res => {
            let d = res.data;
            if(!d.period) return;
            
            document.getElementById('history').innerHTML = d.history.slice(0, 10).map(h => `
                <div class="h-item">
                    <div class="h-period">${h.period.slice(-4)}期</div>
                    <div class="h-nums">${h.nums}</div>
                    <div class="h-total">${h.total}</div>
                    <div>${h.big_small}${h.odd_even}</div>
                </div>`).join('');

            if (d.algo_list && d.algo_list.length > 0) {
                document.getElementById('api-box').style.display = 'block';
                let html = '';
                d.algo_list.forEach(algo => {
                    html += `<div class="api-row">
                        <div>[${algo.id}] ${algo.name} (得分${algo.score})</div>
                        <div class="red">${algo.vote}</div>
                    </div>`;
                });
                document.getElementById('api-content').innerHTML = html;
            } else {
                document.getElementById('api-box').style.display = 'none';
            }

            if(d.pred) {
                document.getElementById('pred-box').style.display = 'block';
                document.getElementById('next-period').innerText = d.next;
                document.getElementById('kill-item').innerText = d.pred.kill;
                document.getElementById('ana').innerText = d.pred.analysis;
                try {
                    let parts = d.pred.rec.split('、');
                    document.getElementById('main-item').innerText = parts[0].replace('(主攻)', '');
                    document.getElementById('def-item').innerText = parts[1].replace('(防守)', '');
                    document.getElementById('bak-item').innerText = parts[2].replace('(备选)', '');
                } catch(e) {}
            }
            
            if(timer) clearInterval(timer);
            let left = d.left || 0;
            let cdEl = document.getElementById('cd');
            
            // 核心修改：倒计时归零，强制展示红色高亮拉取状态！
            if(left <= 0) {
                cdEl.innerText = "极速拉取官方开奖中...";
                cdEl.classList.add('danger');
                // 倒计时结束，强制高频刷新数据（100毫秒一次），轰炸后端拿新结果
                setTimeout(fetchData, 100); 
                return;
            }
            
            timer = setInterval(() => {
                if(left <= 0) { 
                    clearInterval(timer); 
                    fetchData(); 
                    return; 
                }
                left--;
                cdEl.innerText = `${Math.floor(left/60).toString().padStart(2,'0')}:${(left%60).toString().padStart(2,'0')}`;
                if (left <= 3) cdEl.classList.add('danger'); else cdEl.classList.remove('danger');
            }, 1000);
            
        });
    }
    
    function fetchLogs() {
        fetch(`/api/logs/${curG}`, { headers: {'X-Token': KEY} }).then(r => r.json()).then(res => {
            document.getElementById('st-cw').innerText = res.stats.current_win;
            document.getElementById('st-cl').innerText = res.stats.current_lose;
            document.getElementById('st-tw').innerText = res.stats.total_win;
            document.getElementById('st-tl').innerText = res.stats.total_lose;
            
            document.getElementById('logs').innerHTML = res.logs.map(l => `
                <div class="log-item">
                    <div>
                        <div style="color:#b2bec3; font-size:12px;">${l.period} | 开奖时间: ${l.draw_time || '---'}</div>
                        <div>绝杀:<span class="lose">${l.kill}</span> | 推荐:${l.rec}</div>
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
