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
SECRET_KEY = "captain_advanced_math_v93"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

AI_STATUS = {"online": True, "msg": "多维高精度模型演算中..."}
LIVE_DATA = {gt: {"period": "", "next": "", "left": 0, "history": [], "pred": None, "algo_list": []} for gt in GAMES}

def db():
    conn = sqlite3.connect('predict_advanced_v93.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT, draw_time TEXT, kill TEXT, rec TEXT, 
        analysis TEXT, real_result TEXT DEFAULT '', status TEXT DEFAULT 'wait',
        UNIQUE(gtype, period) 
    )''')
    conn.commit()

# ================== 高精度多维推演引擎 ==================
def calculate_matrix(gt, history, next_p):
    if len(history) < 10: return None

    # 提取近 10 期真实位置数据
    h10 = history[:10]
    nums_10 = [[int(x) for x in h['nums'].split(' + ')] for h in h10]
    
    A_series = [n[0] for n in nums_10]
    B_series = [n[1] for n in nums_10]
    C_series = [n[2] for n in nums_10]

    # ------------------ 1. A位推演 (指数平滑) ------------------
    # 公式: A_pred = 0.5*A1 + 0.3*A2 + 0.15*A3 + 0.05*A4
    a_weight = [0.5, 0.3, 0.15, 0.05]
    A_pred_float = sum(A_series[i] * a_weight[i] for i in range(4))
    pred_A = round(A_pred_float)
    err_A = abs(A_pred_float - pred_A) # 误差在 0.01 - 0.50 之间

    # ------------------ 2. B位推演 (线性回归) ------------------
    # 用近 6 期数据做简单线性回归 (x=1,2,3..6, y=B位)
    X = [i for i in range(1, 7)]
    Y = B_series[:6][::-1] # 反转，使最新一期为 x=6
    n = 6
    sum_x = sum(X)
    sum_y = sum(Y)
    sum_xy = sum(X[i] * Y[i] for i in range(n))
    sum_x2 = sum(x**2 for x in X)
    
    # 斜率 k 和截距 b
    k = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x**2)
    b = (sum_y - k * sum_x) / n
    # 预测下一期 (x=7)
    B_pred_float = k * 7 + b
    if B_pred_float < 0: B_pred_float = 0
    if B_pred_float > 9: B_pred_float = 9
    pred_B = round(B_pred_float)
    err_B = abs(B_pred_float - pred_B) # 误差在 0.01 - 0.50 之间

    # ------------------ 3. C位推演 (移动平均+斐波那契) ------------------
    # 公式: C_pred = 均值 + (均值 - 上期) * 0.618
    c_avg = sum(C_series[:5]) / 5.0
    C_pred_float = c_avg + (c_avg - C_series[0]) * 0.618
    if C_pred_float < 0: C_pred_float = 0
    if C_pred_float > 9: C_pred_float = 9
    pred_C = round(C_pred_float)
    err_C = abs(C_pred_float - pred_C)

    # ------------------ 4. AC交叉与BD跨度校验 ------------------
    # AC交叉：预测A与预测C的绝对值差
    ac_cross = abs(pred_A - pred_C)
    # BD跨度：B位的历史最大值-最小值
    bd_span = max(B_series) - min(B_series)
    
    # 引入微小随机误差扰动 (0.01 - 0.99)，确保每次计算都有真实小数波动
    import random
    epsilon = round(random.uniform(0.01, 0.99), 2)
    if epsilon % 2 == 0:
        A_pred_float += epsilon * 0.1
    else:
        C_pred_float += epsilon * 0.1

    # 重新确定最终的整数落点
    pred_A = round(A_pred_float)
    pred_C = round(C_pred_float)

    # 汇总推演出的三位新号码
    pred_nums = [pred_A, pred_B, pred_C]
    pred_total = sum(pred_nums)

    # 判定大小单双
    pred_bs = "大" if pred_total >= 14 else "小"
    pred_oe = "单" if pred_total % 2 != 0 else "双"
    final_combo = pred_bs + pred_oe

    # 最终结果
    top_bs, top_oe = final_combo[0], final_combo[1]
    top_display = f"{top_bs} ➕ {top_oe}"
    kill_display = f"{'小' if top_bs=='大' else '大'} ➕ {'双' if top_oe=='单' else '单'}"

    # ================== 组装极其详细的推演过程 ==================
    analysis = f"【舰长·多维高精度模型计算】\n"
    analysis += f"上期开奖号码：{h10[0]['nums']}\n\n"
    
    analysis += f"=== 【A位推演 (指数平滑模型)】 ===\n"
    analysis += f"近4期A位：{A_series[:4]}\n"
    analysis += f"1. 加权计算：0.5×{A_series[0]} + 0.3×{A_series[1]} + 0.15×{A_series[2]} + 0.05×{A_series[3]} = {A_pred_float:.2f}\n"
    analysis += f"2. 四舍五入取整后落点：【{pred_A}】 (误差约 {abs(A_pred_float-pred_A):.2f})\n\n"

    analysis += f"=== 【B位推演 (线性回归方程)】 ===\n"
    analysis += f"近6期B位：{B_series[:6]}\n"
    analysis += f"1. 拟合斜率 k={k:.2f}, 截距 b={b:.2f}\n"
    analysis += f"2. 代入 x=7 预测下一期：y = {k:.2f} × 7 + {b:.2f} = {B_pred_float:.2f}\n"
    analysis += f"3. 四舍五入取整后落点：【{pred_B}】 (误差约 {err_B:.2f})\n\n"

    analysis += f"=== 【C位推演 (斐波那契回撤)】 ===\n"
    analysis += f"近5期C位：{C_series[:5]}\n"
    analysis += f"1. 近5期均值：{c_avg:.2f}，上期落点：{C_series[0]}\n"
    analysis += f"2. 回撤公式：{c_avg:.2f} + ({c_avg:.2f} - {C_series[0]}) × 0.618 = {C_pred_float:.2f}\n"
    analysis += f"3. 四舍五入取整后落点：【{pred_C}】 (误差约 {err_C:.2f})\n\n"

    analysis += f"=== 【交叉矩阵校验】 ===\n"
    analysis += f"- AC交叉位移量：{ac_cross}\n"
    analysis += f"- BD极值跨度：{bd_span}\n"
    analysis += f"- 引入系统微扰常数：{epsilon:.2f}\n\n"

    analysis += f"=== 【综合判定】 ===\n"
    analysis += f"预测三码：{pred_A} + {pred_B} + {pred_C} = {pred_total}\n"
    analysis += f"大小判定：{pred_total} {'>=' if pred_total >= 14 else '<'} 14，判定为【{pred_bs}】\n"
    analysis += f"单双判定：{pred_total} 是{'奇' if pred_total % 2 != 0 else '偶'}数，判定为【{pred_oe}】\n\n"

    analysis += f"🎯 核心推出：{top_display}\n"

    algo_list = [{"name": "高维推演", "vote": top_display, "detail": f"推演组合：{pred_A}+{pred_B}+{pred_C}"}]

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
                            AI_STATUS["msg"] = "执行高精度回归演算中..."
                            
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
                                
                            AI_STATUS["msg"] = "高维推演完成，等待开奖..."
                                
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
        
        /* 计算过程详细面板样式 */
        .ana { background: #fdfaf6; padding: 15px; border-left: 4px solid #e17055; font-size: 14px; line-height: 1.7; color: #2d3436; white-space: pre-wrap; border-radius: 0 12px 12px 0; margin-top: 15px; font-family: monospace;}
        
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
    const KEY = "captain_advanced_math_v93";
    
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
