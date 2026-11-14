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
SECRET_KEY = "ultimate_api_sniper_v5"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60, "api_game": "ff28"},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60, "api_game": "btc28"}
}

AI_STATUS = {"online": True, "msg": "系统运转中"}
LIVE_DATA = {gt: {"period": "", "next": "", "left": 0, "history": [], "pred": None, "api_raw": None} for gt in GAMES}

# ================== 数据库 ==================
def db():
    conn = sqlite3.connect('predict_api_v5.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT, kill TEXT, rec TEXT, 
        analysis TEXT, real_result TEXT DEFAULT '', status TEXT DEFAULT 'wait')''')
    conn.commit()

# ================== 加拿大28本地算法 (保持不变) ==================
def run_canada_algo(history):
    h7 = history[:7]
    bs = [1 if h['big_small'] == '大' else 0 for h in h7]
    oe = [1 if h['odd_even'] == '单' else 0 for h in h7]
    big, odd = sum(bs), sum(oe)
    
    def streak(seq):
        s = 1
        for i in range(1, len(seq)):
            if seq[i] == seq[0]: s += 1
            else: break
        return s
    s_bs, s_oe = streak(bs), streak(oe)
    
    scores = {"大单": 50.0, "大双": 50.0, "小单": 50.0, "小双": 50.0}
    
    if s_bs >= 2: 
        for k in scores: 
            if bs[0] == 1 and '大' in k: scores[k] += 15
            if bs[0] == 0 and '小' in k: scores[k] += 15
    if s_oe >= 2:
        for k in scores:
            if oe[0] == 1 and '单' in k: scores[k] += 10
            if oe[0] == 0 and '双' in k: scores[k] += 10
    if s_bs >= 3:
        for k in scores:
            if bs[0] == 1 and '大' in k: scores[k] -= 15
            if bs[0] == 0 and '小' in k: scores[k] -= 15
    if s_oe >= 3:
        for k in scores:
            if oe[0] == 1 and '单' in k: scores[k] -= 15
            if oe[0] == 0 and '双' in k: scores[k] -= 15

    if big >= 5:
        for k in scores:
            if '大' in k: scores[k] -= 20
    elif big <= 2:
        for k in scores:
            if '小' in k: scores[k] -= 20
    if odd >= 5:
        for k in scores:
            if '单' in k: scores[k] -= 20
    elif odd <= 2:
        for k in scores:
            if '双' in k: scores[k] -= 20

    combos = [h['big_small'] + h['odd_even'] for h in h7]
    if combos[0] == combos[1]: scores[combos[0]] -= 15
    
    for k in scores: scores[k] += random.uniform(-2.0, 2.0)

    kill_str = sorted(scores.items(), key=lambda x: x[1])[0][0]
    rem = [k for k in ["大单", "大双", "小单", "小双"] if k != kill_str]
    return {
        "kill": kill_str,
        "rec": f"{rem[0]}(主攻)、{rem[1]}(防守)、{rem[2]}(备选)",
        "analysis": f"【本地6算法共识】综合投票，绝杀【{kill_str}】，重点防守【{rem[0]}】。"
    }

# ================== 分分/比特28 真实 API 抓取与解析 ==================
def fetch_api_prediction(game_code):
    ctx = ssl._create_unverified_context()
    url = f"https://dbg28.com/api/master/algorithms?_={int(time.time()*1000)}&game={game_code}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://dbg28.com/'
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
            raw_data = json.loads(resp.read().decode('utf-8'))
            
            # --- 万能解析器 ---
            algorithms = []
            if isinstance(raw_data, dict) and 'data' in raw_data:
                algorithms = raw_data['data']
            elif isinstance(raw_data, list):
                algorithms = raw_data
                
            votes = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
            details = []
            
            # 如果拿到了列表，遍历所有算法提取推荐/绝杀
            if algorithms and isinstance(algorithms, list):
                for algo in algorithms:
                    if not isinstance(algo, dict): continue
                    
                    name = algo.get('name', '未知算法')
                    # 兼容常见的字段名: kill, recommend, result, code, bet
                    kill = algo.get('kill') or algo.get('recommend') or algo.get('result') or algo.get('bet')
                    
                    # 过滤无效值
                    if kill in votes:
                        votes[kill] += 1
                        details.append(f"{name}: {kill}")
            
            # 如果能提取到有效票数
            if sum(votes.values()) > 0:
                kill_str = max(votes, key=votes.get)
                rem = [k for k in ["大单", "大双", "小单", "小双"] if k != kill_str]
                return {
                    "kill": kill_str,
                    "rec": f"{rem[0]}(主攻)、{rem[1]}(防守)、{rem[2]}(备选)",
                    "analysis": f"【API 直连推演】系统从该接口获取了 {len(algorithms)} 个算法策略。\n各策略推荐明细：\n" + "\n".join(details[:10]) + f"\n\n统票结果：绝杀【{kill_str}】。"
                }, raw_data
            else:
                return {
                    "kill": "API结构未知",
                    "rec": "等待适配",
                    "analysis": f"接口请求成功，但返回的 JSON 结构无法提取出直接的开奖结果。\n返回的原始数据首部: {str(raw_data)[:100]}..."
                }, raw_data
                
    except Exception as e:
        # 抓取失败时抛出真实错误
        return {
            "kill": "抓取失败",
            "rec": "等待重试",
            "analysis": f"真实 API 请求失败，原因：{str(e)}。请检查服务器网络是否能访问 dbg28.com。"
        }, None

# ================== 抓取与结算主循环 ==================
def fetch_loop():
    ctx = ssl._create_unverified_context()
    while True:
        for gt, cfg in GAMES.items():
            try:
                req = urllib.request.Request(cfg['url'], headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    if data.get('data'):
                        latest = data['data'][0]
                        history = [{"period": i['period'], "nums": f"{i['num1']} + {i['num2']} + {i['num3']}", "total": i['total'], "big_small": i['big_small'], "odd_even": i['odd_even']} for i in data['data'][:20]]
                        
                        if LIVE_DATA[gt]['period'] != latest['period']:
                            # --- 结算 ---
                            if LIVE_DATA[gt]['period'] != "" and LIVE_DATA[gt]['pred']:
                                real = latest['big_small'] + latest['odd_even']
                                p_kill = LIVE_DATA[gt]['pred']['kill']
                                with db() as conn:
                                    status = 'win' if real != p_kill else 'lose'
                                    conn.execute("UPDATE logs SET real_result=?, status=? WHERE gtype=? AND period=?", (real, status, gt, latest['period']))
                                    conn.commit()

                            dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            LIVE_DATA[gt].update({
                                "period": latest['period'], "next": str(int(latest['period'])+1),
                                "target_time": (dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])).timestamp(), 
                                "history": history,
                                "api_raw": None
                            })
                            
                            # --- 预测 ---
                            if gt == "2":
                                pred = run_canada_algo(history)
                            else:
                                pred, raw_api = fetch_api_prediction(cfg['api_game'])
                                LIVE_DATA[gt]['api_raw'] = raw_api

                            LIVE_DATA[gt]['pred'] = pred
                            
                            with db() as conn:
                                conn.execute('''INSERT INTO logs (gtype, period, kill, rec, analysis) VALUES (?,?,?,?,?)''', 
                                             (gt, LIVE_DATA[gt]['next'], pred["kill"], pred["rec"], pred["analysis"]))
                                conn.commit()
                                
                        diff = LIVE_DATA[gt]['target_time'] - datetime.utcnow().timestamp()
                        LIVE_DATA[gt]['left'] = max(0, int(diff))
            except Exception:
                pass
        time.sleep(1)

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
    <title>API 直连精准狙击</title>
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
        .cd-box { text-align: center; font-size: 14px; color: #636e72; margin-bottom: 10px;}
        .cd { font-size: 22px; color: #0984e3; font-weight: bold; }
        
        .cd.danger { color: #d63031; animation: flash 0.5s infinite alternate;}
        @keyframes flash { 0% { opacity: 0.4; } 100% { opacity: 1; } }

        .ana { background: #fdfaf6; padding: 15px; border-left: 4px solid #e17055; font-size: 14px; line-height: 1.7; color: #2d3436; white-space: pre-wrap; }
        
        .api-list { display: none; background: #222f3e; color: #c8d6e5; margin: 12px; padding: 15px; border-radius: 12px; font-family: monospace; font-size: 13px; max-height: 300px; overflow-y: auto; }
        .api-title { color: #feca57; font-weight: bold; margin-bottom: 10px; font-size: 14px;}
        .api-pre { white-space: pre-wrap; word-wrap: break-word; color: #c8d6e5;}

        .log-item { border-bottom: 1px solid #f1f2f6; padding: 10px 0; font-size: 13px; display: flex; justify-content: space-between; }
        .win { color: #00b894; font-weight: bold; } .lose { color: #d63031; font-weight: bold; }
        .btn-clear { float:right; font-size:12px; padding:5px 10px; border:1px solid #d63031; color:#d63031; border-radius:6px;}
        .log-scroll { max-height: 400px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="head">API 直连精准狙击</div>
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

    <!-- API 真实数据面板 -->
    <div class="api-list" id="api-box">
        <div class="api-title">📡 真实 API 抓取验证</div>
        <div class="api-pre" id="api-content"></div>
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
        <div class="cd-box">距开奖: <span class="cd" id="cd">--:--</span></div>
        <div class="ana" id="ana"></div>
    </div>
    <div class="card">
        <div class="title">历史复盘 <button class="btn-clear" onclick="clearLogs()">清空</button></div>
        <div id="logs" class="log-scroll"></div>
    </div>
<script>
    let curG = '2', timer = null;
    const KEY = "ultimate_api_sniper_v5";
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

            // 分分和比特显示 API 原始数据
            if (curG === '3' || curG === '13') {
                if (d.api_raw) {
                    document.getElementById('api-box').style.display = 'block';
                    document.getElementById('api-content').innerText = JSON.stringify(d.api_raw, null, 2);
                } else {
                    document.getElementById('api-box').style.display = 'block';
                    document.getElementById('api-content').innerText = "API 原始数据未获取到或结构无法解析，请查看下方绝杀提示。";
                }
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
            timer = setInterval(() => {
                if(left <= 0) { cdEl.innerText = "开奖中..."; cdEl.classList.add('danger'); return; }
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
                        <div style="color:#b2bec3; font-size:12px;">${l.period}</div>
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
    setInterval(fetchData, 1000);
    setInterval(fetchLogs, 5000);
</script>
</body>
</html>
    """

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8888))
    app.run(host='0.0.0.0', port=port)
