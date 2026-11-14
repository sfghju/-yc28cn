import urllib.request
import ssl
import json
import time
import threading
import os
import sqlite3
import re
import random
import hashlib
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
SECRET_KEY = "ultimate_blockchain_sniper"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

AI_STATUS = {"online": True, "msg": "系统运转中"}
# 增加 snipe_done 状态标记，防止一期内重复压秒
LIVE_DATA = {gt: {"period": "", "next": "", "left": 0, "history": [], "pred": None, "btc_hash": None, "snipe_done": False} for gt in GAMES}

# ================== 数据库 ==================
def db():
    conn = sqlite3.connect('predict_sniper.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT, kill TEXT, rec TEXT, 
        analysis TEXT, real_result TEXT DEFAULT '', status TEXT DEFAULT 'wait', algo_ids TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS algo_pool (
        gtype TEXT, algo_id INTEGER, streak INTEGER DEFAULT 0, PRIMARY KEY (gtype, algo_id))''')
    for gt in GAMES:
        for i in range(1, 201):
            conn.execute("INSERT OR IGNORE INTO algo_pool (gtype, algo_id, streak) VALUES (?, ?, 0)", (gt, i))
    conn.commit()

# ================== 区块链压秒狙击计算 ==================
def calculate_btc_hash_logic(seed_string):
    try:
        sha256_hash = hashlib.sha256(seed_string.encode('utf-8')).hexdigest()
        first_16 = sha256_hash[:16]
        dec_val = int(first_16, 16)
        result_float = dec_val / (2**64)
        str_val = f"{result_float:.10f}"
        decimal_part = str_val.split('.')[1][:3]
        
        return {
            "hash": sha256_hash,
            "first_16": first_16,
            "dec": dec_val,
            "float": result_float,
            "result": int(decimal_part),
            "combo": ("大" if int(decimal_part) >= 14 else "小") + ("单" if int(decimal_part) % 2 != 0 else "双")
        }
    except Exception:
        return None

# 极速获取（使用 mempool.space 接口，比 blockchain.info 更快）
def get_live_blockchain_prediction():
    ctx = ssl._create_unverified_context()
    try:
        # 获取最近的交易，速度极快
        url = "https://mempool.space/api/mempool/recent"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3, context=ctx) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            # 按照平台的逻辑，将哈希字符串拼接
            # mempool.space 返回格式: [{"txid": "...", "fee": ...}, ...]
            combined_str = "".join([tx['txid'] for tx in data])
            return calculate_btc_hash_logic(combined_str)
    except Exception as e:
        print("狙击抓取失败:", e)
        return None

# ================== 6算法共识引擎 (保持不变) ==================
def run_single_algo(algo_id, h7):
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
    camp = algo_id % 4 
    
    if camp == 0: 
        if s_bs >= 2: 
            for k in scores: 
                if bs[0] == 1 and '大' in k: scores[k] += 15
                if bs[0] == 0 and '小' in k: scores[k] += 15
        if s_oe >= 2:
            for k in scores:
                if oe[0] == 1 and '单' in k: scores[k] += 10
                if oe[0] == 0 and '双' in k: scores[k] += 10
    elif camp == 1: 
        if s_bs >= 3:
            for k in scores:
                if bs[0] == 1 and '大' in k: scores[k] -= 15
                if bs[0] == 0 and '小' in k: scores[k] -= 15
        if s_oe >= 3:
            for k in scores:
                if oe[0] == 1 and '单' in k: scores[k] -= 15
                if oe[0] == 0 and '双' in k: scores[k] -= 15
    elif camp == 2: 
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
    elif camp == 3: 
        combos = [h['big_small'] + h['odd_even'] for h in h7]
        if combos[0] == combos[1]: scores[combos[0]] -= 15
        if big + odd >= 8: scores["大单"] += 10; scores["小双"] -= 10
        if big + odd <= 4: scores["小单"] += 10; scores["大双"] -= 10

    random.seed(algo_id + int(h7[0]['total']))
    for k in scores: scores[k] += random.uniform(-2.0, 2.0)

    return sorted(scores.items(), key=lambda x: x[1])[0][0]

def calculate_consensus(gtype, history):
    if len(history) < 7: return {"kill": "数据不足", "rec": "-", "analysis": "等待数据...", "algo_ids": ""}
    
    with db() as conn:
        last_log = conn.execute("SELECT algo_ids FROM logs WHERE gtype=? ORDER BY id DESC LIMIT 1", (gtype,)).fetchone()
        last_used = last_log['algo_ids'].split(',') if last_log and last_log['algo_ids'] else []
        algos = conn.execute("SELECT * FROM algo_pool WHERE gtype=? ORDER BY streak DESC", (gtype,)).fetchall()
        candidates = [a for a in algos if str(a['algo_id']) not in last_used]
        if len(candidates) < 6: candidates = algos[:6]
        selected_algos = candidates[:6]
        
    votes = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
    algo_records = []
    
    for a in selected_algos:
        kill_vote = run_single_algo(a['algo_id'], history[:7])
        votes[kill_vote] += 1
        algo_records.append({"id": a['algo_id'], "streak": a['streak'], "vote": kill_vote})
        
    sorted_v = sorted(votes.items(), key=lambda x: x[1], reverse=True)
    kill_str = sorted_v[0][0]
    rem = [x[0] for x in sorted_v[1:]]
    main_atk, defend, backup = rem[0], rem[1], rem[2]

    body = f"本期系统选中 6 套独立算法参赛：\n"
    for i, a in enumerate(algo_records):
        body += f"{i+1}. 算法{a['id']:03d}(连中{a['streak']}期)，投出绝杀票：【{a['vote']}】。\n"
    outro = f"\n综合投票，【{kill_str}】票数最高。主攻【{main_atk}】，防守【{defend}】，备选【{backup}】。"

    return {
        "kill": kill_str, "rec": f"{main_atk}(主攻)、{defend}(防守)、{backup}(备选)",
        "analysis": body + outro, "algo_ids": ",".join([str(a['id']) for a in algo_records])
    }

# ================== 主循环 (加入压秒狙击) ==================
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
                        
                        # 发现新的一期开奖了
                        if LIVE_DATA[gt]['period'] != latest['period']:
                            if LIVE_DATA[gt]['period'] != "" and LIVE_DATA[gt]['pred']:
                                real = latest['big_small'] + latest['odd_even']
                                p_kill = LIVE_DATA[gt]['pred']['kill']
                                a_ids = LIVE_DATA[gt]['pred']['algo_ids'].split(',')
                                
                                with db() as conn:
                                    status = 'win' if real != p_kill else 'lose'
                                    conn.execute("UPDATE logs SET real_result=?, status=? WHERE gtype=? AND period=?", (real, status, gt, latest['period']))
                                    for aid in a_ids:
                                        if status == 'win': conn.execute("UPDATE algo_pool SET streak = streak + 1 WHERE gtype=? AND algo_id=?", (gt, int(aid)))
                                        else: conn.execute("UPDATE algo_pool SET streak = 0 WHERE gtype=? AND algo_id=?", (gt, int(aid)))
                                    conn.commit()

                            dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            LIVE_DATA[gt].update({
                                "period": latest['period'], "next": str(int(latest['period'])+1),
                                "target_time": (dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])).timestamp(), 
                                "history": history,
                                "snipe_done": False,  # 重置压秒状态
                                "btc_hash": None      # 清空上期哈希
                            })
                            
                            pred = calculate_consensus(gt, history)
                            LIVE_DATA[gt]['pred'] = pred
                            
                            with db() as conn:
                                conn.execute('''INSERT INTO logs (gtype, period, kill, rec, analysis, algo_ids) VALUES (?,?,?,?,?,?)''', 
                                             (gt, LIVE_DATA[gt]['next'], pred["kill"], pred["rec"], pred["analysis"], pred["algo_ids"]))
                                conn.commit()
                                
                        # 计算倒计时
                        diff = LIVE_DATA[gt]['target_time'] - datetime.utcnow().timestamp()
                        LIVE_DATA[gt]['left'] = max(0, int(diff))
                        
                        # 🚨 核心：压秒狙击逻辑 (只针对比特和分分)
                        if gt in ("3", "13"):
                            # 如果距离下期开奖只剩 4 秒，且还没压秒过，立即触发抓取
                            if 0 < diff <= 4 and not LIVE_DATA[gt]['snipe_done']:
                                AI_STATUS["msg"] = "压秒狙击触发！正在截胡..."
                                print(f"⚡ {cfg['name']} 触发压秒狙击，正在极速抓取哈希...")
                                btc_pred = get_live_blockchain_prediction()
                                if btc_pred:
                                    LIVE_DATA[gt]["btc_hash"] = btc_pred
                                LIVE_DATA[gt]['snipe_done'] = True
                                AI_STATUS["msg"] = "系统运转中"
                                
            except Exception:
                pass
        time.sleep(0.5) # 稍微加快主循环频率

threading.Thread(target=fetch_loop, daemon=True).start()

# ================== API 与 前端 (保持不变) ==================
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
        conn.execute("UPDATE algo_pool SET streak = 0 WHERE gtype=?", (gt,))
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
    <title>6算法 + 压秒区块链狙击</title>
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
        
        /* 倒计时变红闪烁 */
        .cd.danger { color: #d63031; animation: flash 0.5s infinite alternate;}
        @keyframes flash { 0% { opacity: 0.4; } 100% { opacity: 1; } }

        .ana { background: #fdfaf6; padding: 15px; border-left: 4px solid #e17055; font-size: 14px; line-height: 1.7; color: #2d3436; white-space: pre-wrap; }
        
        .btc-box { display: none; background: #222f3e; color: #c8d6e5; margin: 12px; padding: 15px; border-radius: 12px; font-family: monospace; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
        .btc-title { color: #feca57; font-weight: bold; margin-bottom: 10px; font-size: 14px; display: flex; justify-content: space-between;}
        .btc-result { font-size: 36px; font-weight: bold; color: #1dd1a1; text-align: center; margin: 10px 0; text-shadow: 0 0 10px rgba(29, 209, 161, 0.5);}
        .btc-detail { font-size: 11px; word-break: break-all; margin-bottom: 5px; color: #8395a7;}
        .btc-detail span { color: #c8d6e5; }

        .log-item { border-bottom: 1px solid #f1f2f6; padding: 10px 0; font-size: 13px; display: flex; justify-content: space-between; }
        .win { color: #00b894; font-weight: bold; } .lose { color: #d63031; font-weight: bold; }
        .btn-clear { float:right; font-size:12px; padding:5px 10px; border:1px solid #d63031; color:#d63031; border-radius:6px;}
        .log-scroll { max-height: 400px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="head">6算法 + 压秒区块链狙击</div>
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

    <!-- 压秒狙击面板 -->
    <div class="btc-box" id="btc-box">
        <div class="btc-title">
            <span>⛓️ 压秒哈希狙击 (倒计时4秒触发)</span>
            <span style="color:#ff6b6b;" id="btc-status">等待触发...</span>
        </div>
        <div class="btc-result" id="btc-res">--</div>
        <div class="btc-detail">哈希头: <span id="btc-hash">--</span></div>
        <div class="btc-detail">前16位: <span id="btc-16">--</span></div>
        <div class="btc-detail">10进制: <span id="btc-dec">--</span></div>
        <div class="btc-detail">除以2^64: <span id="btc-float">--</span></div>
        <div style="color:#ff9f43; font-size:12px; margin-top:8px; border-top: 1px dashed #576574; padding-top: 8px;">
            * 极速引擎会在开奖前 4 秒瞬间抓取比特币内存池，计算最终结果。与平台拼手速！
        </div>
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
    const KEY = "ultimate_blockchain_sniper";
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

            // 只在分分和比特显示区块链
            if (curG === '3' || curG === '13') {
                if (d.btc_hash) {
                    document.getElementById('btc-box').style.display = 'block';
                    document.getElementById('btc-res').innerText = d.btc_hash.result + " (" + d.btc_hash.combo + ")";
                    document.getElementById('btc-hash').innerText = d.btc_hash.hash.slice(0, 20) + "...";
                    document.getElementById('btc-16').innerText = d.btc_hash.first_16;
                    document.getElementById('btc-dec').innerText = d.btc_hash.dec;
                    document.getElementById('btc-float').innerText = d.btc_hash.float.toFixed(10);
                    document.getElementById('btc-status').innerText = "压秒截胡成功！";
                    document.getElementById('btc-status').style.color = "#1dd1a1";
                } else {
                    document.getElementById('btc-box').style.display = 'block';
                    document.getElementById('btc-res').innerText = "--";
                    document.getElementById('btc-status').innerText = "等待最后4秒...";
                    document.getElementById('btc-status').style.color = "#ff9f43";
                }
            } else {
                document.getElementById('btc-box').style.display = 'none';
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
                if (left <= 5) cdEl.classList.add('danger'); else cdEl.classList.remove('danger');
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
                        <div>绝杀:<span class="lose">${l.kill}</span> | 推荐:${l.rec.split('、')[0]}</div>
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
        if(!confirm("清空所有记录并重置算法？")) return;
        fetch(`/api/clear/${curG}`, { method: 'POST', headers: {'X-Token': KEY} }).then(() => fetchLogs());
    }
    fetchData(); fetchLogs();
    setInterval(fetchData, 1000); // 加快前端刷新率，应对最后几秒
    setInterval(fetchLogs, 5000);
</script>
</body>
</html>
    """

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8888))
    app.run(host='0.0.0.0', port=port)
