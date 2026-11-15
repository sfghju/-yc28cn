import urllib.request
import ssl
import json
import time
import threading
import os
import sqlite3
import hashlib
from collections import Counter
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
SECRET_KEY = "algo_mid_streak_v67"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

AI_STATUS = {"online": True, "msg": "正在筛选中等连中算法..."}
LIVE_DATA = {gt: {"period": "", "next": "", "left": 0, "history": [], "pred": None, "algo_list": []} for gt in GAMES}

def db():
    conn = sqlite3.connect('predict_v67.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT, draw_time TEXT, kill TEXT, rec TEXT, 
        analysis TEXT, real_result TEXT DEFAULT '', status TEXT DEFAULT 'wait',
        UNIQUE(gtype, period) 
    )''')
    conn.commit()

# ================== 核心：200套独立算法引擎 ==================
def run_single_algo(aid, history):
    if len(history) < 10: return "数据不足"
    
    bs_seq = [h['big_small'] for h in history]
    oe_seq = [h['odd_even'] for h in history]
    
    # 1-100为顺势阵营，101-200为逆势阵营
    is_follow = aid <= 100
    mode = (aid % 10) if is_follow else ((aid - 100) % 10)
    param = aid // 10
    
    push_bs, push_oe = "大", "单"
    
    if mode == 0: # 均线逻辑
        w = 5 + (param % 5)
        recent_bs, recent_oe = bs_seq[:w], oe_seq[:w]
        if is_follow: # 顺势：谁多推谁
            push_bs = "大" if recent_bs.count('大') >= w/2 else "小"
            push_oe = "单" if recent_oe.count('单') >= w/2 else "双"
        else: # 逆势：反杀多数
            push_bs = "小" if recent_bs.count('大') >= w/2 else "大"
            push_oe = "双" if recent_oe.count('单') >= w/2 else "单"
    elif mode == 1: # 极值逻辑
        w = 3 + (param % 4)
        recent_bs, recent_oe = bs_seq[:w], oe_seq[:w]
        if is_follow: # 顺势：跟着长龙
            push_bs, push_oe = bs_seq[0], oe_seq[0]
        else: # 逆势：抓断点
            push_bs = "小" if recent_bs.count('大') == w else ("大" if recent_bs.count('小') == w else bs_seq[0])
            push_oe = "双" if recent_oe.count('单') == w else ("单" if recent_oe.count('双') == w else oe_seq[0])
    elif mode == 2: # 纯顺势
        push_bs, push_oe = bs_seq[0], oe_seq[0]
    elif mode == 3: # 纯交替
        push_bs = "小" if bs_seq[0] == "大" else "大"
        push_oe = "双" if oe_seq[0] == "单" else "单"
    elif mode == 4: # 尾数
        t = history[0]['total'] % 10
        push_bs = "大" if t >= 5 else "小"
        push_oe = "单" if t % 2 != 0 else "双"
    elif mode == 5: # 交叉
        n0 = [int(x) for x in history[0]['nums'].split(' + ')]
        n1 = [int(x) for x in history[1]['nums'].split(' + ')]
        val = n0[0] + n1[1]
        push_bs = "大" if val >= 10 else "小"
        push_oe = "单" if val % 2 != 0 else "双"
    elif mode == 6: # 哈希
        h = hashlib.md5(f"{aid}_{history[0]['period']}".encode()).hexdigest()
        v = int(h[:4], 16)
        push_bs = "大" if v % 2 == 0 else "小"
        push_oe = "单" if (v // 2) % 2 == 0 else "双"
    elif mode == 7: # 断点
        push_bs = ("小" if bs_seq[0] == "大" else "大") if (bs_seq[0] == bs_seq[1] == bs_seq[2]) else bs_seq[1]
        push_oe = ("双" if oe_seq[0] == "单" else "单") if (oe_seq[0] == oe_seq[1] == oe_seq[2]) else oe_seq[1]
    elif mode == 8: # 平滑
        c_bs, c_oe = bs_seq[:10].count('大'), oe_seq[:10].count('单')
        if is_follow:
            push_bs = "大" if c_bs >= 5 else "小"
            push_oe = "单" if c_oe >= 5 else "双"
        else:
            push_bs = "小" if c_bs >= 5 else "大"
            push_oe = "双" if c_oe >= 5 else "单"
    else: # 混沌
        h = hashlib.sha256(f"{aid}_{history[0]['period']}".encode()).hexdigest()
        v = int(h[:6], 16)
        push_bs = "大" if (v + param) % 3 == 0 else "小"
        push_oe = "单" if (v + param) % 2 == 0 else "双"

    return push_bs + push_oe

# ================== 中等连中筛选引擎 ==================
def calculate_matrix(gt, history, next_p):
    if len(history) < 20: return None

    algo_list = []
    
    # 1. 统计200套算法近20期战绩
    for aid in range(1, 201):
        win_cnt = 0; lose_cnt = 0; curr_streak = 0; curr_type = ""
        
        for i in range(20):
            if i+1 >= len(history): break
            p = run_single_algo(aid, history[i+1:])
            r_bs, r_oe = history[i]['big_small'], history[i]['odd_even']
            is_win = (r_bs == p[0] or r_oe == p[1])
            
            if is_win:
                win_cnt += 1
                curr_streak = curr_streak + 1 if curr_type == "win" else 1
                curr_type = "win"
            else:
                lose_cnt += 1
                curr_streak = curr_streak + 1 if curr_type == "lose" else 1
                curr_type = "lose"
                
        pred_now = run_single_algo(aid, history)
        algo_list.append({
            "id": aid, "vote": f"{pred_now[0]} ➕ {pred_now[1]}", 
            "win": win_cnt, "lose": lose_cnt, "streak": curr_streak, "type": curr_type,
            "camp": "顺势" if aid <= 100 else "逆势"
        })

    # 2. 筛选“当前连中”的算法
    winners = [a for a in algo_list if a['type'] == 'win']
    target_algo = None
    select_msg = ""

    if winners:
        # 提取所有正在连中的期数
        streaks = sorted([a['streak'] for a in winners])
        # 找中位数
        mid_streak = streaks[len(streaks)//2]
        
        # 寻找连中数等于中位数，且胜率最高的
        candidates = [a for a in winners if a['streak'] == mid_streak]
        # 如果中位数没找到（极少情况），放宽到中位数附近
        if not candidates:
            candidates = [a for a in winners if abs(a['streak'] - mid_streak) <= 1]
            
        candidates.sort(key=lambda x: x['win'], reverse=True)
        target_algo = candidates[0]
        select_msg = f"锁定处于中等连中（{target_algo['streak']}期）的王者算法。"
    else:
        # 连中都断了（比如全在连错），那就直接找总对最高的
        algo_list.sort(key=lambda x: x['win'], reverse=True)
        target_algo = algo_list[0]
        select_msg = "当前无连中算法，强制锁定总对最高算法。"

    top_display = target_algo['vote']
    k_bs = '小' if top_display[0] == '大' else '大'
    k_oe = '双' if top_display[2] == '单' else '单'
    kill_display = f"{k_bs} ➕ {k_oe}"

    analysis = f"【中等连中·猎杀机制】\n"
    analysis += f"200套算法（100顺势，100逆势）已完成20期回测。\n"
    analysis += f"当前锁定：【算法{target_algo['id']}】 ({target_algo['camp']})\n"
    analysis += f"战绩：对({target_algo['win']})错({target_algo['lose']})，当前连中{target_algo['streak']}期。\n"
    analysis += f"{select_msg}\n\n"
    analysis += f"🎯 核心推出：{top_display}\n"
    analysis += f"注：开出包含推出属性即算中奖！"

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
                            AI_STATUS["msg"] = "正在锁定中等连中算法..."
                            
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
                                
                            AI_STATUS["msg"] = "推演完毕，等待下一期..."
                                
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

@app.route('/api/filter/<gt>', methods=['POST'])
def api_filter(gt):
    if not verify(): return jsonify({"ok": False})
    filter_type = request.json.get('filter_type')
    if 'algo_list' not in LIVE_DATA[gt] or not LIVE_DATA[gt]['algo_list']: return jsonify({"algos": []})
        
    algos = LIVE_DATA[gt]['algo_list']
    if filter_type == "current_win": result = sorted([a for a in algos if a['type'] == 'win' and a['streak'] >= 3], key=lambda x: x['streak'], reverse=True)
    elif filter_type == "current_lose": result = sorted([a for a in algos if a['type'] == 'lose' and a['streak'] >= 3], key=lambda x: x['streak'], reverse=True)
    elif filter_type == "highest_win": result = sorted(algos, key=lambda x: (x['win'], x['streak']), reverse=True)[:20]
    elif filter_type == "highest_lose": result = sorted(algos, key=lambda x: x['lose'], reverse=True)[:20]
    else: result = []
    return jsonify({"algos": result})

@app.route('/api/logs/<gt>')
def api_logs(gt):
    if not verify(): return "<h1>Access Denied</h1>", 403
    with db() as conn:
        logs = conn.execute("SELECT * FROM logs WHERE gtype=? GROUP BY period ORDER BY id DESC", (gt,)).fetchall()
        settled = [l['status'] for l in logs if l['status'] in ('win', 'lose')]
        stats = {
            "current_win": 0, "current_lose": 0, 
            "total_win": settled.count('win'), "total_lose": settled.count('lose'),
            "total_pred": len(logs)  # 总预测期数
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
    <title>中等连中·猎杀机制</title>
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
        
        .filter-bar { display: flex; gap: 8px; margin-bottom: 15px; }
        .btn-filter { flex: 1; padding: 8px 0; text-align: center; font-size: 13px; font-weight: bold; border-radius: 6px; border: 1px solid #ddd; background: #fff; cursor: pointer; transition: 0.2s;}
        .btn-filter:active { background: #f0f2f5; }
        .btn-filter.on { background: #e8f4f8; color: #0984e3; border-color: #0984e3; }
        
        .algo-list { background: #222f3e; color: #c8d6e5; border-radius: 12px; padding: 15px; font-family: monospace; font-size: 13px; max-height: 400px; overflow-y: auto;}
        .algo-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px dashed #2c3e50;}
        .algo-row span.win { color: #00b894; } .algo-row span.lose { color: #d63031; }
        .algo-row span.push { color: #feca57; font-weight: bold; font-size: 15px;}
        
        .log-item { border-bottom: 1px solid #f1f2f6; padding: 12px 0; font-size: 13px; display: flex; justify-content: space-between; }
        .win { color: #00b894; font-weight: bold; } .lose { color: #d63031; font-weight: bold; }
        .btn-clear { float:right; font-size:12px; padding:5px 10px; border:1px solid #d63031; color:#d63031; border-radius:6px;}
        .log-scroll { max-height: 400px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="head">中等连中·猎杀机制</div>
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
        <div class="title">📊 独立算法大盘 (点击按钮筛选)</div>
        <div class="filter-bar">
            <div class="btn-filter" onclick="filterAlgos('current_win', this)">当前连中</div>
            <div class="btn-filter" onclick="filterAlgos('current_lose', this)">当前连错</div>
            <div class="btn-filter" onclick="filterAlgos('highest_win', this)">最高总对</div>
            <div class="btn-filter" onclick="filterAlgos('highest_lose', this)">最高总错</div>
        </div>
        <div class="algo-list" id="algo-list">
            <div style="text-align: center; color: #8395a7; margin-top: 20px;">请点击上方按钮加载算法数据</div>
        </div>
    </div>
    
    <div class="card">
        <div class="title">历史复盘 <button class="btn-clear" onclick="clearLogs()">清空</button></div>
        <div id="logs" class="log-scroll"></div>
    </div>
    
<script>
    let curG = '2', timer = null;
    const KEY = "algo_mid_streak_v67";
    
    function switchG(g, el) {
        curG = g;
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
        el.classList.add('on');
        document.getElementById('pred-box').style.display = 'none';
        document.getElementById('algo-list').innerHTML = '<div style="text-align: center; color: #8395a7; margin-top: 20px;">请点击上方按钮加载算法数据</div>';
        document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('on'));
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
                cdEl.innerText = "正在分析预测中...";
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

    function filterAlgos(type, btn) {
        document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('on'));
        btn.classList.add('on');
        
        fetch(`/api/filter/${curG}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-Token': KEY},
            body: JSON.stringify({ filter_type: type })
        }).then(r => r.json()).then(res => {
            let algos = res.algos;
            if (!algos || algos.length === 0) {
                document.getElementById('algo-list').innerHTML = '<div style="text-align: center; color: #8395a7; margin-top: 20px;">未找到符合条件的算法 (如：无3连及以上)</div>';
                return;
            }
            
            let html = '';
            algos.forEach(a => {
                let statusStr = a.type === 'win' ? `<span class="win">连中${a.streak}</span>` : `<span class="lose">连错${a.streak}</span>`;
                if (a.streak === 0) statusStr = '<span style="color:#8395a7">平局</span>';
                html += `<div class="algo-row">
                    <div><span style="color:#8395a7">[算法${a.id}]</span> <span style="color:#f39c12">${a.camp}</span> | 近20期 <span class="win">对${a.win}</span> <span class="lose">错${a.lose}</span> | ${statusStr}</div>
                    <div class="push">${a.vote}</div>
                </div>`;
            });
            document.getElementById('algo-list').innerHTML = html;
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
