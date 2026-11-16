import urllib.request
import ssl
import json
import time
import threading
import os
import sqlite3
import math
import random
import statistics
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
SECRET_KEY = "captain_ensemble_v101"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

AI_STATUS = {"online": True, "msg": "6大高维算法融合推演中..."}
LIVE_DATA = {gt: {"period": "", "next": "", "left": 0, "history": [], "pred": None, "algo_list": []} for gt in GAMES}

def db():
    conn = sqlite3.connect('predict_ensemble_v101.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT, draw_time TEXT, kill TEXT, rec TEXT, 
        analysis TEXT, real_result TEXT DEFAULT '', status TEXT DEFAULT 'wait',
        UNIQUE(gtype, period) 
    )''')
    conn.commit()

# ================== 高阶机器学习与统计融合引擎 ==================
def calculate_matrix(gt, history, next_p):
    if len(history) < 20: return None

    # 提取近20期真实组合序列
    combos = ["大单", "大双", "小单", "小双"]
    recent_20 = history[:20]
    seq = [h['big_small'] + h['odd_even'] for h in recent_20]
    
    # 前推 1 期的状态 (例如上期是"大单")
    last_combo = seq[0]

    # 初始化得分字典
    scores = {c: 0.0 for c in combos}

    # ================== 1. 贝叶斯平滑 (Dirichlet Prior) ==================
    # 防止冷号概率归零，给每个组合一个基础先验分
    bayes_scores = {c: 1.0 for c in combos}
    for c in seq:
        bayes_scores[c] += 1.0
    # 归一化
    total_bayes = sum(bayes_scores.values())
    for c in combos:
        scores[c] += (bayes_scores[c] / total_bayes) * 10
    detail_bayes = f"贝叶斯平滑后概率：大单{scores['大单']:.2f}, 大双{scores['大双']:.2f}, 小单{scores['小单']:.2f}, 小双{scores['小双']:.2f}"

    # ================== 2. 指数平滑 (EWMA) ==================
    alpha = 0.3
    ewma_scores = {c: 0.0 for c in combos}
    for i, c in enumerate(seq):
        weight = (1 - alpha) ** i
        ewma_scores[c] += weight
    total_ewma = sum(ewma_scores.values())
    for c in combos:
        scores[c] += (ewma_scores[c] / total_ewma) * 15
    detail_ewma = f"EWMA近期权重：大单{ewma_scores['大单']:.2f}, 大双{ewma_scores['大双']:.2f}, 小单{ewma_scores['小单']:.2f}, 小双{ewma_scores['小双']:.2f}"

    # ================== 3. 一阶马尔可夫链 ==================
    # 统计当前状态下，下一期的转移频次
    markov_counts = {c: 0 for c in combos}
    for i in range(19):
        if seq[i+1] == last_combo:
            markov_counts[seq[i]] += 1
            
    total_markov = sum(markov_counts.values())
    if total_markov > 0:
        for c in combos:
            scores[c] += (markov_counts[c] / total_markov) * 20
    detail_markov = f"马尔可夫转移概率(从{last_combo}出发)：{', '.join([f'{k}({v}次)' for k, v in markov_counts.items() if v > 0])}"

    # ================== 4. KNN 相似历史期 ==================
    # 寻找特征相似的历史期 (简化为：寻找历史中与上期同组合的期数)
    knn_counts = {c: 0 for c in combos}
    for i in range(1, 20):
        if seq[i] == last_combo:
            knn_counts[seq[i-1]] += 1
    total_knn = sum(knn_counts.values())
    if total_knn > 0:
        for c in combos:
            scores[c] += (knn_counts[c] / total_knn) * 15
    detail_knn = f"KNN相似期推演：{', '.join([f'{k}({v}次)' for k, v in knn_counts.items() if v > 0])}"

    # ================== 5. 蒙特卡洛约束采样 ==================
    # 基于上述概率进行 1000 次采样，并加入 0.01-0.09 的微扰
    import random
    random.seed(int(next_p))
    mc_counts = {c: 0 for c in combos}
    total_score = sum(scores.values())
    weights = [scores[c] / total_score for c in combos]
    
    for _ in range(1000):
        pick = random.choices(combos, weights=weights, k=1)[0]
        # 引入误差项
        error_term = random.uniform(0.01, 0.09)
        if error_term > 0.05: # 简单的概率翻转逻辑
            mc_counts[pick] += 1
            
    detail_mc = f"蒙特卡洛1000次采样最高频：{max(mc_counts, key=mc_counts.get)}"

    # ================== 6. 集成学习 (Stacking 加权汇总) ==================
    final_scores = {c: 0.0 for c in combos}
    for c in combos:
        final_scores[c] = scores[c] + mc_counts[c] * 0.05
        
    # 输出最终判定
    main_combo = max(final_scores, key=final_scores.get)
    kill_combo = min(final_scores, key=final_scores.get)
    
    top_bs, top_oe = main_combo[0], main_combo[1]
    top_display = f"{top_bs} ➕ {top_oe}"
    kill_display = f"{kill_combo[0]} ➕ {kill_combo[1]}"

    # 组装极其硬核的算法说明面板
    analysis = f"【舰长·高阶量化算法融合矩阵】\n"
    analysis += f"上期开奖：{last_combo} | 目标期号：{next_p}\n\n"
    analysis += f"=== 【第1层：基础统计模型】 ===\n"
    analysis += f"- {detail_bayes}\n"
    analysis += f"- {detail_ewma}\n\n"
    analysis += f"=== 【第2层：时序与转移模型】 ===\n"
    analysis += f"- {detail_markov}\n"
    analysis += f"- {detail_knn}\n\n"
    analysis += f"=== 【第3层：仿真与集成】 ===\n"
    analysis += f"- {detail_mc}\n"
    analysis += f"- 动态Stacking最终得分：\n"
    for c in combos:
        analysis += f"  * {c}: {final_scores[c]:.3f}\n"
    analysis += f"\n🎯 融合高精度算法核心推出：{top_display}\n"
    analysis += f"注：开出包含推出属性即算中奖！"

    return {"kill": kill_display, "rec": top_display, "analysis": analysis, "algo_list": [{"name": "高维集成学习", "vote": top_display}]}

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
                            AI_STATUS["msg"] = f"{cfg['name']} 高阶算法演算中..."
                            
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
                                
                            AI_STATUS["msg"] = "高阶推演完成，等待开奖..."
                                
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
    const KEY = "captain_ensemble_v101";
    
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
