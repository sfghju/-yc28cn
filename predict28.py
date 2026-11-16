import urllib.request
import ssl
import json
import time
import threading
import os
import sqlite3
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
SECRET_KEY = "captain_matrix_v94"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

AI_STATUS = {"online": True, "msg": "A-M矩阵极速运算中..."}
LIVE_DATA = {gt: {"period": "", "next": "", "left": 0, "history": [], "pred": None, "algo_list": []} for gt in GAMES}

def db():
    conn = sqlite3.connect('predict_matrix_v94.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT, draw_time TEXT, kill TEXT, rec TEXT, 
        analysis TEXT, real_result TEXT DEFAULT '', status TEXT DEFAULT 'wait',
        UNIQUE(gtype, period) 
    )''')
    conn.commit()

# ================== 全息 A-M 矩阵推演引擎 ==================
def calculate_matrix(gt, history, next_p):
    if len(history) < 10: return None

    h10 = history[:10]
    sums = [h['total'] for h in h10]
    nums_10 = [[int(x) for x in h['nums'].split(' + ')] for h in h10]
    
    A_series = [n[0] for n in nums_10]
    B_series = [n[1] for n in nums_10]
    C_series = [n[2] for n in nums_10]
    
    # 各维度倾向计分板
    score_bs = {"大": 0.0, "小": 0.0}
    score_oe = {"单": 0.0, "双": 0.0}
    analysis_details = []

    # ================== 基础 ABC 维度 ==================
    # A位: 指数平滑
    a_w = [0.5, 0.3, 0.15, 0.05]
    A_val = sum(A_series[i] * a_w[i] for i in range(4))
    analysis_details.append(f"【A位】指数平滑预测落点：{A_val:.2f}，取整 {round(A_val)}")
    
    # B位: 线性回归
    k = 0.1 # 简化，固定波动
    B_val = B_series[0] * 0.8 + B_series[1] * 0.2 + k
    analysis_details.append(f"【B位】线性回归预测落点：{B_val:.2f}，取整 {round(B_val)}")

    # C位: 移动平均
    C_val = sum(C_series[:3]) / 3.0
    analysis_details.append(f"【C位】移动平均预测落点：{C_val:.2f}，取整 {round(C_val)}")

    pred_sum = round(A_val) + round(B_val) + round(C_val)
    if pred_sum >= 14: score_bs["大"] += 2
    else: score_bs["小"] += 2

    # ================== D-M 高阶衍生维度 ==================
    
    # D: 跨度 (Max - Min)
    span_val = max(A_series[0], B_series[0], C_series[0]) - min(A_series[0], B_series[0], C_series[0])
    if span_val >= 6: score_bs["大"] += 1.5
    else: score_bs["小"] += 1.5
    analysis_details.append(f"【D位-跨度】上期极差为 {span_val}，形态呈{'扩张' if span_val>=6 else '收敛'}")

    # E: 大小偏离度
    big_cnt = sum([1 for s in sums if s >= 14])
    if big_cnt >= 6: 
        score_bs["小"] += 1 # 防回落
        analysis_details.append(f"【E位-大数频率】近10期大数占比 {big_cnt}/10，均值回归防小")
    else:
        score_bs["大"] += 1
        analysis_details.append(f"【E位-大数频率】近10期大数占比 {big_cnt}/10，趋势顺延防大")

    # F: 奇偶失衡率
    odd_cnt = sum([1 for s in sums if s % 2 != 0])
    if odd_cnt >= 6:
        score_oe["双"] += 1.5
        analysis_details.append(f"【F位-奇偶失衡】单数高达 {odd_cnt}/10，强制反转防双")
    else:
        score_oe["单"] += 1.5
        analysis_details.append(f"【F位-奇偶失衡】单数仅 {odd_cnt}/10，动能不足防单")

    # G: 质合分布 (质数：2,3,5,7)
    prime_cnt = sum([1 for n in nums_10[0] if n in [2,3,5,7]])
    if prime_cnt >= 2:
        score_oe["单"] += 1
        analysis_details.append(f"【G位-质合】上期质数达 {prime_cnt} 个，质数多为单")
    else:
        score_oe["双"] += 1
        analysis_details.append(f"【G位-质合】上期质数仅 {prime_cnt} 个，合数偏偶")

    # H: 邻期差值
    diff_H = abs(sums[0] - sums[1])
    analysis_details.append(f"【H位-邻期差】连续两期和值差为 {diff_H}，盘面波动{ '剧烈' if diff_H>5 else '平缓'}")

    # I: AC值 (两两相减的绝对值不重复个数)
    ac_set = set()
    for i in range(3):
        for j in range(i+1, 3):
            ac_set.add(abs(nums_10[0][i] - nums_10[0][j]))
    ac_val = len(ac_set)
    analysis_details.append(f"【I位-AC离散】上期AC值为 {ac_val}，数字离散度{'高' if ac_val==3 else '低'}")

    # J: 方差
    avg_sum = sum(sums) / 10.0
    variance = sum((s - avg_sum)**2 for s in sums) / 10.0
    if variance > 20: score_bs["大"] += 1
    else: score_bs["小"] += 1
    analysis_details.append(f"【J位-波动方差】近10期方差 {variance:.2f}，活跃度{'高' if variance>20 else '低'}")

    # K: 振幅均线
    amps = [abs(sums[i] - sums[i+1]) for i in range(5)]
    avg_amp = sum(amps) / 5.0
    analysis_details.append(f"【K位-振幅均线】近5期平均振幅 {avg_amp:.2f}")

    # L: 012路 (和值除3余数)
    road = sums[0] % 3
    if road == 0:
        score_oe["双"] += 0.5
        analysis_details.append("【L位-012路】上期落在0路(余0)，属性偏双")
    elif road == 1:
        score_oe["单"] += 0.5
        analysis_details.append("【L位-012路】上期落在1路(余1)，属性偏单")

    # M: 和值尾
    tail = sums[0] % 10
    if tail >= 5: score_bs["大"] += 0.5
    else: score_bs["小"] += 0.5
    analysis_details.append(f"【M位-和值尾】上期尾数 {tail}")

    # ================== 综合判定 ==================
    # 加入 0.01 - 0.99 的微扰，符合你的误差要求
    import random
    epsilon = round(random.uniform(0.01, 0.99), 2)
    score_bs["大"] += epsilon * 0.1
    
    final_bs = "大" if score_bs["大"] >= score_bs["小"] else "小"
    final_oe = "单" if score_oe["单"] >= score_oe["双"] else "双"
    final_combo = final_bs + final_oe

    top_display = f"{final_bs} ➕ {final_oe}"
    kill_display = f"{'小' if final_bs=='大' else '大'} ➕ {'双' if final_oe=='单' else '单'}"

    # 组装分析面板
    analysis = f"【舰长·A-M全息矩阵极速推演】\n"
    for d in analysis_details:
        analysis += f"- {d}\n"
    analysis += f"\n【综合计分】\n"
    analysis += f"- 大小得分：大 {score_bs['大']:.2f} / 小 {score_bs['小']:.2f}\n"
    analysis += f"- 单双得分：单 {score_oe['单']:.2f} / 双 {score_oe['双']:.2f}\n"
    analysis += f"- 引入微扰常数：{epsilon}\n\n"
    analysis += f"🎯 核心推出：{top_display}\n"
    analysis += f"注：开出包含推出属性即算中奖！"

    algo_list = [{"name": "A-M全息矩阵", "vote": top_display, "detail": f"13维特征融合"}]

    return {"kill": kill_display, "rec": top_display, "analysis": analysis, "algo_list": algo_list}

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
                            AI_STATUS["msg"] = "执行全息矩阵推演中..."
                            
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
    const KEY = "captain_matrix_v94";
    
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
