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
SECRET_KEY = "simple_combo_v55"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

AI_STATUS = {"online": True, "msg": "近40期极简推演中..."}
LIVE_DATA = {gt: {"period": "", "next": "", "left": 0, "history": [], "pred": None, "algo_list": []} for gt in GAMES}

def db():
    conn = sqlite3.connect('predict_v55.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT, draw_time TEXT, kill TEXT, rec TEXT, 
        analysis TEXT, real_result TEXT DEFAULT '', status TEXT DEFAULT 'wait')''')
    conn.commit()

# ================== 40期极简冷热推演引擎 ==================
def calculate_prediction(gt, history, next_p):
    # 采用近40期数据
    h_len = min(40, len(history))
    if h_len < 10:
        return {"kill": "", "rec": "数据不足", "analysis": "等待数据...", "algo_list": []}
        
    hx = history[:h_len]
    bs_list = [h['big_small'] for h in hx]
    oe_list = [h['odd_even'] for h in hx]
    
    big_cnt = bs_list.count('大')
    small_cnt = bs_list.count('小')
    odd_cnt = oe_list.count('单')
    even_cnt = oe_list.count('双')
    
    # 默认逻辑：谁多杀谁，谁少推谁
    kill_bs = "大" if big_cnt >= small_cnt else "小"
    push_bs = "小" if kill_bs == "大" else "大"
    
    kill_oe = "单" if odd_cnt >= even_cnt else "双"
    push_oe = "双" if kill_oe == "单" else "单"

    # 检测长龙 (>=6连)
    def check_dragon(seq):
        streak = 1
        for i in range(1, len(seq)):
            if seq[i] == seq[0]: streak += 1
            else: break
        return streak >= 6, streak, seq[0]

    has_bs_dragon, bs_streak, bs_dragon_type = check_dragon(bs_list)
    has_oe_dragon, oe_streak, oe_dragon_type = check_dragon(oe_list)

    dragon_msg = ""
    
    # 长龙防回马枪逻辑：多的跟，少的反
    if has_bs_dragon:
        push_bs = bs_dragon_type 
        kill_bs = "小" if push_bs == "大" else "大"
        dragon_msg += f"【大小长龙】已连开 {bs_streak} 期【{bs_dragon_type}】，顺势跟进，防回马枪。\n"
        
    if has_oe_dragon:
        push_oe = oe_dragon_type
        kill_oe = "双" if push_oe == "单" else "单"
        dragon_msg += f"【单双长龙】已连开 {oe_streak} 期【{oe_dragon_type}】，顺势跟进，防回马枪。\n"

    if not dragon_msg:
        dragon_msg = "【盘面平稳】遵循少跟多反原则。\n"

    # 组合
    push_combo = f"{push_bs} ➕ {push_oe}"
    kill_combo = f"{kill_bs} ➕ {kill_oe}"

    analysis = f"【近{h_len}期冷热推演】\n"
    analysis += f"- 大小统计：大({big_cnt}) / 小({small_cnt})\n"
    analysis += f"- 单双统计：单({odd_cnt}) / 双({even_cnt})\n"
    analysis += f"- {dragon_msg}"
    analysis += f"\n🎯 推出组合：{push_combo}\n"
    analysis += f"注：只要开出包含推出属性的组合（如推大单，开大双或小单），均算中奖！"

    algo_list = [
        {"name": "大小风向", "vote": push_bs, "detail": f"大{big_cnt} 小{small_cnt}"},
        {"name": "单双风向", "vote": push_oe, "detail": f"单{odd_cnt} 双{even_cnt}"}
    ]

    return {
        "kill": kill_combo, # 后台计算击杀组合用于校验命中率
        "rec": push_combo, 
        "analysis": analysis, 
        "algo_list": algo_list
    }

# ================== 极速抓取主循环 ==================
def fetch_loop():
    ctx = ssl._create_unverified_context()
    while True:
        for gt, cfg in GAMES.items():
            try:
                req_url = f"{cfg['url']}&_={int(time.time()*1000)}"
                req = urllib.request.Request(req_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    if data.get('data'):
                        # 拉取60期数据，取前40期做分析，足以展示
                        raw_data = data['data'][:60] 
                        latest = raw_data[0]
                        
                        history = [{
                            "period": i['period'], 
                            "nums": f"{i['num1']} + {i['num2']} + {i['num3']}", 
                            "total": i['total'], 
                            "big_small": i['big_small'], 
                            "odd_even": i['odd_even']
                        } for i in raw_data]
                        
                        if LIVE_DATA[gt]['period'] != latest['period']:
                            # 结算逻辑
                            if LIVE_DATA[gt]['period'] != "" and LIVE_DATA[gt]['pred']:
                                real = latest['big_small'] + latest['odd_even']
                                p_kill_combo = LIVE_DATA[gt]['pred']['kill']
                                
                                if p_kill_combo:
                                    k_bs, k_oe = p_kill_combo.replace(" ", "").split("➕")
                                    if real == (k_bs + k_oe):
                                        status = 'lose'
                                    else:
                                        status = 'win' 
                                else:
                                    status = 'win'

                                with db() as conn:
                                    conn.execute("UPDATE logs SET real_result=?, status=? WHERE gtype=? AND period=?", (real, status, gt, latest['period']))
                                    conn.commit()

                            dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            next_p = str(int(latest['period'])+1)
                            LIVE_DATA[gt].update({
                                "period": latest['period'], "next": next_p,
                                "target_time": (dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])).timestamp(), 
                                "history": history
                            })

                            pred = calculate_prediction(gt, history, next_p)
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
        time.sleep(0.1)

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
        
        # 完美统计，过滤掉等待状态
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
    <title>极简推出组合</title>
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
        
        /* 极简展示区 */
        .result-box { display: flex; flex-direction: column; gap: 15px; margin-top: 10px; }
        .res-push { padding: 25px; border-radius: 12px; text-align: center; font-size: 36px; font-weight: 900; letter-spacing: 2px; color: #0984e3; background: #e8f4f8; border: 1px solid #b2d8ef; box-shadow: 0 4px 15px rgba(9,132,227,0.1);}
        
        .cd-box { text-align: center; font-size: 14px; color: #636e72; margin-bottom: 10px;}
        .cd { font-size: 22px; color: #0984e3; font-weight: bold; }
        .cd.danger { color: #d63031; animation: flash 0.5s infinite alternate;}
        @keyframes flash { 0% { opacity: 0.4; } 100% { opacity: 1; } }
        
        .ana { background: #fdfaf6; padding: 15px; border-left: 4px solid #e17055; font-size: 14px; line-height: 1.7; color: #2d3436; white-space: pre-wrap; border-radius: 0 12px 12px 0; margin-top: 15px;}
        
        .log-item { border-bottom: 1px solid #f1f2f6; padding: 12px 0; font-size: 13px; display: flex; justify-content: space-between; }
        .win { color: #00b894; font-weight: bold; } .lose { color: #d63031; font-weight: bold; }
        .btn-clear { float:right; font-size:12px; padding:5px 10px; border:1px solid #d63031; color:#d63031; border-radius:6px;}
        .log-scroll { max-height: 400px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="head">极简推出组合</div>
    <div class="status" id="status"><span class="dot"></span> 系统运转正常</div>
    <div class="tabs">
        <div class="tab on" onclick="switchG('2', this)">加拿大28</div>
        <div class="tab" onclick="switchG('3', this)">分分28</div>
        <div class="tab" onclick="switchG('13', this)">比特28</div>
    </div>
    
    <!-- 顶部统计恢复 -->
    <div class="stats-bar">
        <div class="stats-item">当前连中<span class="stats-val win" id="st-cw" style="color:#00b894;">0</span></div>
        <div class="stats-item">当前连错<span class="stats-val lose" id="st-cl" style="color:#d63031;">0</span></div>
        <div class="stats-item">总命中<span class="stats-val win" id="st-tw" style="color:#00b894;">0</span></div>
        <div class="stats-item">总被杀<span class="stats-val lose" id="st-tl" style="color:#d63031;">0</span></div>
    </div>

    <div class="card">
        <div class="title">近 40 期 独立盘面</div>
        <div class="history" id="history"></div>
    </div>
    
    <div class="card" id="pred-box" style="display:none">
        <div class="title">目标拦截: <span id="next-period" style="color:#0984e3;"></span></div>
        
        <div class="result-box">
            <div class="res-push">🎯 推出：<span id="rec-item"></span></div>
        </div>

        <div class="cd-box" style="margin-top:20px;">距开奖: <span class="cd" id="cd">--:--</span></div>
        <div class="ana" id="ana"></div>
    </div>
    
    <div class="card">
        <div class="title">历史复盘 <button class="btn-clear" onclick="clearLogs()">清空</button></div>
        <div id="logs" class="log-scroll"></div>
    </div>
    
<script>
    let curG = '2', timer = null;
    const KEY = "simple_combo_v55";
    
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
            
            // 展示 40 期数据
            document.getElementById('history').innerHTML = d.history.slice(0, 40).map(h => `
                <div class="h-item">
                    <div class="h-period">${h.period.slice(-4)}期</div>
                    <div class="h-nums">${h.nums}</div>
                    <div class="h-total">${h.total}</div>
                    <div>${h.big_small}${h.odd_even}</div>
                </div>`).join('');

            if(d.pred) {
                document.getElementById('pred-box').style.display = 'block';
                document.getElementById('next-period').innerText = d.next;
                document.getElementById('rec-item').innerText = d.pred.rec;
                document.getElementById('ana').innerText = d.pred.analysis;
            }
            
            if(timer) clearInterval(timer);
            let left = d.left || 0;
            let cdEl = document.getElementById('cd');
            
            if(left <= 0) {
                cdEl.innerText = "开奖中...";
                cdEl.classList.add('danger');
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
            // 更新统计数字
            document.getElementById('st-cw').innerText = res.stats.current_win;
            document.getElementById('st-cl').innerText = res.stats.current_lose;
            document.getElementById('st-tw').innerText = res.stats.total_win;
            document.getElementById('st-tl').innerText = res.stats.total_lose;
            
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
