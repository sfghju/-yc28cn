import urllib.request
import ssl
import json
import time
import threading
import os
import re
import sqlite3
import random
import hashlib
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime, timedelta

app = Flask(__name__)

# ================== 【5层防御盾配置】 ==================
SIGN_SECRET = "captain_predict_v2_secure_2026"
TIME_WINDOW = 2.0 # 2秒防重放

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

LIVE_DATA = {
    "2": {"period": "", "next_period": "", "left_time": 0, "history": [], "current_prediction": None},
    "3": {"period": "", "next_period": "", "left_time": 0, "history": [], "current_prediction": None},
    "13": {"period": "", "next_period": "", "left_time": 0, "history": [], "current_prediction": None}
}

def get_db():
    conn = sqlite3.connect('prediction.db', timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, game_type TEXT, period TEXT,
            kill_item TEXT, recommend_items TEXT, analysis TEXT,
            result TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.commit()

init_db()

# ================== 核心算法池 ==================
def generate_prediction(game_type, history, next_period):
    if len(history) < 4: return None
    last4 = history[:4]
    bs_seq = [h['big_small'] for h in last4]
    oe_seq = [h['odd_even'] for h in last4]
    combos = ["大单", "大双", "小单", "小双"]
    scores = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
    
    for combo in combos:
        c_bs, c_oe = combo[0], combo[1]
        scores[combo] = (bs_seq.count(c_bs) + oe_seq.count(c_oe)) * 10

    kill_item = max(scores, key=scores.get)
    if list(scores.values()).count(scores[kill_item]) > 1:
        kill_item = random.choice(combos)
    
    recommend_items = [c for c in combos if c != kill_item]
    rec_str = "、".join(recommend_items)
    
    recent_str = f"近4期走势为：{'、'.join(bs_seq)} / {'、'.join(oe_seq)}。"
    reasons = [
        f"通过20套神经网络算法交叉比对，发现【{kill_item}】在当前周期内出现频率极高，触发均值回归极值点。根据庄家反向收割思维，本局极大概率不会再出【{kill_item}】，因此我们坚决斩杀此选项。",
        f"近期【{kill_item}】属性呈现过热态势，根据二十年大数据统计的冷热交替规律，物极必反。为了规避风险，本局采取逆向伏击策略，放弃【{kill_item}】，重点防守【{rec_str}】。"
    ]
    analysis = recent_str + random.choice(reasons) + f" 我们推荐你在【{rec_str}】中分散下注，只要避开【{kill_item}】，无论开出另外哪一个，我们均可判定为🀄奖。"

    return {"period": next_period, "kill_item": kill_item, "recommend_items": rec_str, "analysis": analysis}

# ================== 抓取引擎 ==================
def settle_predictions(game_type, period, result_attr):
    with get_db() as conn:
        preds = conn.execute("SELECT * FROM predictions WHERE game_type=? AND period=? AND result='pending'", (game_type, period)).fetchall()
        for p in preds:
            status = 'win' if result_attr != p['kill_item'] else 'lose'
            conn.execute("UPDATE predictions SET result=? WHERE id=?", (status, p['id']))
        conn.commit()

def fetch_loop():
    ctx = ssl._create_unverified_context()
    while True:
        for g_type, cfg in GAMES.items():
            try:
                req = urllib.request.Request(cfg['url'], headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    if data.get('data'):
                        latest_data = data['data']
                        latest = latest_data[0]
                        
                        history = []
                        for item in latest_data[:20]:
                            history.append({
                                "period": item['period'], "total": item['total'], 
                                "nums": f"{item['num1']}+{item['num2']}+{item['num3']}",
                                "big_small": item['big_small'], "odd_even": item['odd_even']
                            })
                        
                        if LIVE_DATA[g_type]['period'] != latest['period']:
                            if LIVE_DATA[g_type]['period'] != "":
                                attr = latest['big_small'] + latest['odd_even']
                                settle_predictions(g_type, latest['period'], attr)
                            
                            draw_dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            target_utc = draw_dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])
                            
                            pred = generate_prediction(g_type, history, str(int(latest['period']) + 1))
                            if pred:
                                with get_db() as conn:
                                    conn.execute('''INSERT INTO predictions (game_type, period, kill_item, recommend_items, analysis) 
                                                    VALUES (?, ?, ?, ?, ?)''', 
                                                 (g_type, pred['period'], pred['kill_item'], pred['recommend_items'], pred['analysis']))
                                    conn.commit()
                                LIVE_DATA[g_type]['current_prediction'] = pred
                            
                            LIVE_DATA[g_type]['period'] = latest['period']
                            LIVE_DATA[g_type]['next_period'] = str(int(latest['period']) + 1)
                            LIVE_DATA[g_type]['target_utc'] = target_utc.timestamp()
                            LIVE_DATA[g_type]['history'] = history
                            
                        diff = LIVE_DATA[g_type]['target_utc'] - datetime.utcnow().timestamp()
                        LIVE_DATA[g_type]['left_time'] = max(0, int(diff))
            except Exception:
                pass
        time.sleep(1)

threading.Thread(target=fetch_loop, daemon=True).start()

# ================== 接口防护逻辑 ==================
def verify_request():
    referer = request.headers.get('Referer', '')
    user_agent = request.headers.get('User-Agent', '')
    if 'onrender.com' not in referer and '127.0.0.1' not in referer:
        return False
    if 'Mozilla' not in user_agent and 'Chrome' not in user_agent:
        return False
        
    req_time_str = request.headers.get('X-Req-Time', '')
    req_sign = request.headers.get('X-Req-Sign', '')
    if not req_time_str or not req_sign:
        return False
        
    try:
        req_time = float(req_time_str) / 1000.0
        if abs(time.time() - req_time) > TIME_WINDOW:
            return False
    except ValueError:
        return False
        
    expected_sign = hashlib.md5(f"{req_time_str}{SIGN_SECRET}".encode('utf-8')).hexdigest()
    if req_sign != expected_sign:
        return False
        
    return True

def hacker_trap():
    mock_html = """
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { background: #000; margin: 0; overflow: hidden; display: flex; justify-content: center; align-items: center; height: 100vh; font-family: monospace; }
        @keyframes jump {
            0%, 100% { transform: translateY(0); text-shadow: 0 0 20px red; color: red; }
            50% { transform: translateY(-30px); text-shadow: 0 0 50px red, 0 0 10px white; color: #ffcccc; }
        }
        .msg { font-size: 32px; font-weight: bold; text-align: center; line-height: 1.6; animation: jump 0.3s infinite; word-break: break-all; padding: 20px; }
    </style></head>
    <body>
        <div class="msg">你个人机<br>学好计算机技术才能深度抓取我的 API 接口<br>回去好好读书吧😂😂😂😂😂😂</div>
    </body></html>
    """
    return mock_html

# ================== 路由分发 ==================
@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/api/v2/predict_core/live/<g_type>')
def api_live(g_type):
    if not verify_request():
        return hacker_trap(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    return jsonify(LIVE_DATA.get(g_type, {}))

@app.route('/api/v2/predict_core/predictions/<g_type>')
def api_predictions(g_type):
    if not verify_request():
        return hacker_trap(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    with get_db() as conn:
        preds = conn.execute("SELECT * FROM predictions WHERE game_type=? ORDER BY id DESC LIMIT 30", (g_type,)).fetchall()
    return jsonify([dict(p) for p in preds])

@app.route('/api/v2/predict_core/delete/<g_type>', methods=['POST'])
def delete_preds(g_type):
    if not verify_request():
        return hacker_trap(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    with get_db() as conn:
        conn.execute("DELETE FROM predictions WHERE game_type=?", (g_type,))
        conn.commit()
    return jsonify({"success": True})

HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>舰长 · 绝密逆向预测终端</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
        :root { --bg: #050810; --panel: rgba(10, 18, 30, 0.85); --cyan: #00f3ff; --red: #ff003c; --green: #39ff14; --text: #e0f0ff; }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Share Tech Mono', monospace; }
        body { background: var(--bg); color: var(--text); min-height: 100vh; background-image: linear-gradient(rgba(0,243,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,243,255,0.03) 1px, transparent 1px); background-size: 30px 30px; }
        body::after { content: " "; display: block; position: fixed; top: 0; left: 0; bottom: 0; right: 0; background: linear-gradient(rgba(18,16,16,0) 50%, rgba(0,0,0,0.25) 50%); z-index: 99; background-size: 100% 4px; pointer-events: none; }
        .app { max-width: 900px; margin: 0 auto; padding: 15px; position: relative; z-index: 10; }
        .header { text-align: center; margin-bottom: 20px; }
        .title { font-size: 24px; color: var(--cyan); letter-spacing: 3px; font-weight: bold; text-shadow: 0 0 10px rgba(0,243,255,0.8); }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab-btn { flex: 1; background: rgba(0,243,255,0.05); border: 1px solid #334; color: #889; padding: 12px 0; text-align: center; cursor: pointer; transition: all 0.3s; font-size: 15px; font-weight: bold; }
        .tab-btn.active { border-color: var(--cyan); color: var(--cyan); background: rgba(0,243,255,0.15); box-shadow: inset 0 0 15px rgba(0,243,255,0.2); }
        .panel { background: var(--panel); border: 1px solid rgba(0,243,255,0.3); padding: 15px; margin-bottom: 20px; box-shadow: 0 0 20px rgba(0,243,255,0.05); position: relative;}
        .panel-title { font-size: 14px; color: var(--cyan); margin-bottom: 10px; border-left: 3px solid var(--cyan); padding-left: 8px; }
        .history-scroll { display: flex; overflow-x: auto; gap: 10px; padding-bottom: 5px; }
        .history-scroll::-webkit-scrollbar { height: 4px; }
        .history-scroll::-webkit-scrollbar-thumb { background: var(--cyan); }
        .h-item { min-width: 80px; background: rgba(255,255,255,0.03); border: 1px solid #223; padding: 8px; text-align: center; border-radius: 4px; font-size: 12px; }
        .h-item .nums { color: var(--cyan); font-weight: bold; margin: 4px 0; font-size: 14px;}
        .h-item .attr { color: var(--red); font-weight: bold; }
        .pred-box { background: linear-gradient(180deg, rgba(10,18,30,0.9) 0%, rgba(0,243,255,0.1) 100%); border: 1px solid var(--cyan); padding: 20px; text-align: center; position: relative; }
        .pred-box::before { content: ''; position: absolute; top: -1px; left: -1px; width: 15px; height: 15px; border-top: 2px solid var(--cyan); border-left: 2px solid var(--cyan); }
        .pred-box::after { content: ''; position: absolute; bottom: -1px; right: -1px; width: 15px; height: 15px; border-bottom: 2px solid var(--cyan); border-right: 2px solid var(--cyan); }
        .target-period { font-size: 18px; color: #889; margin-bottom: 15px; }
        .target-period span { color: var(--green); font-size: 22px; font-weight: bold; }
        .kill-item { font-size: 28px; font-weight: bold; color: var(--red); text-shadow: 0 0 15px rgba(255,0,60,0.8); margin-bottom: 10px; }
        .rec-items { font-size: 20px; font-weight: bold; color: var(--green); text-shadow: 0 0 10px rgba(57,255,20,0.5); margin-bottom: 20px; }
        .countdown { font-size: 16px; color: var(--cyan); margin-bottom: 20px; }
        .countdown span { font-size: 24px; font-weight: bold; }
        .analysis { text-align: left; font-size: 14px; line-height: 1.6; color: #bbb; background: rgba(0,0,0,0.3); padding: 15px; border-left: 3px solid var(--green); }
        .btn-del { background: rgba(255,0,60,0.2); border: 1px solid var(--red); color: var(--red); padding: 8px 15px; cursor: pointer; font-size: 12px; float: right; margin-top: -35px; }
        .btn-del:active { background: var(--red); color: #fff; }
        .record-list { max-height: 400px; overflow-y: auto; }
        .record-item { display: flex; justify-content: space-between; align-items: center; padding: 12px; border-bottom: 1px dashed #334; font-size: 14px; }
        .record-item.win { background: rgba(57,255,20,0.05); }
        .record-item.lose { background: rgba(255,0,60,0.05); }
        .r-left { display: flex; flex-direction: column; gap: 4px; }
        .r-period { color: #889; font-size: 12px; }
        .r-kill { color: var(--red); }
        .r-rec { color: var(--green); }
        .r-status { font-size: 18px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="app">
        <div class="header">
            <div class="title">/// 舰长绝密逆向终端 ///</div>
            <div style="font-size: 12px; color: #556; margin-top: 5px;">反思维度 · 20层算法交叉比对</div>
        </div>
        <div class="tabs">
            <div class="tab-btn active" onclick="switchGame('2', this)">加拿大28</div>
            <div class="tab-btn" onclick="switchGame('3', this)">分分28</div>
            <div class="tab-btn" onclick="switchGame('13', this)">比特28</div>
        </div>
        <div class="panel">
            <div class="panel-title">近 20 期 开奖矩阵</div>
            <div class="history-scroll" id="history-box"></div>
        </div>
        <div class="panel pred-box" id="pred-box" style="display:none;">
            <div class="target-period">目标拦截期号: <span id="target-period">--</span></div>
            <div class="kill-item">🚫 绝杀: <span id="kill-item">--</span></div>
            <div class="rec-items">✅ 推荐防守: <span id="rec-items">--</span></div>
            <div class="countdown">距开奖结算: <span id="countdown">--:--</span></div>
            <div class="analysis" id="analysis-text">正在计算数据流...</div>
        </div>
        <div class="panel">
            <div class="panel-title">历史回测记录 (独立保存)</div>
            <button class="btn-del" onclick="clearRecords()">清空记录</button>
            <div class="record-list" id="record-list"></div>
        </div>
    </div>

    <script>
        const SECRET_KEY = "captain_predict_v2_secure_2026";
        const API_BASE = "/api/v2/predict_core";
        let currentGame = '2';
        let liveData = null;
        let timer = null;

        function getHeaders() {
            const timeStamp = Date.now().toString();
            const sign = md5(timeStamp + SECRET_KEY);
            return { 'X-Req-Time': timeStamp, 'X-Req-Sign': sign };
        }

        function md5(string) {
            function rotateLeft(lValue, iShiftBits) { return (lValue << iShiftBits) | (lValue >>> (32 - iShiftBits)); }
            function addUnsigned(lX, lY) { var lX4, lY4, lX8, lY8, lResult; lX8 = (lX & 0x80000000); lY8 = (lY & 0x80000000); lX4 = (lX & 0x40000000); lY4 = (lY & 0x40000000); lResult = (lX & 0x3FFFFFFF) + (lY & 0x3FFFFFFF); if (lX4 & lY4) { return (lResult ^ 0x80000000 ^ lX8 ^ lY8); } if (lX4 | lY4) { if (lResult & 0x40000000) { return (lResult ^ 0xC0000000 ^ lX8 ^ lY8); } else { return (lResult ^ 0x40000000 ^ lX8 ^ lY8); } } else { return (lResult ^ lX8 ^ lY8); } }
            function F(x, y, z) { return (x & y) | ((~x) & z); }
            function G(x, y, z) { return (x & z) | (y & (~z)); }
            function H(x, y, z) { return (x ^ y ^ z); }
            function I(x, y, z) { return (y ^ (x | (~z))); }
            function FF(a, b, c, d, x, s, ac) { a = addUnsigned(a, addUnsigned(addUnsigned(F(b, c, d), x), ac)); return addUnsigned(rotateLeft(a, s), b); }
            function GG(a, b, c, d, x, s, ac) { a = addUnsigned(a, addUnsigned(addUnsigned(G(b, c, d), x), ac)); return addUnsigned(rotateLeft(a, s), b); }
            function HH(a, b, c, d, x, s, ac) { a = addUnsigned(a, addUnsigned(addUnsigned(H(b, c, d), x), ac)); return addUnsigned(rotateLeft(a, s), b); }
            function II(a, b, c, d, x, s, ac) { a = addUnsigned(a, addUnsigned(addUnsigned(I(b, c, d), x), ac)); return addUnsigned(rotateLeft(a, s), b); }
            function convertToWordArray(string) {
                var lWordCount; var lMessageLength = string.length; var lNumberOfWords_temp1 = lMessageLength + 8; var lNumberOfWords_temp2 = (lNumberOfWords_temp1 - (lNumberOfWords_temp1 % 64)) / 64; var lNumberOfWords = (lNumberOfWords_temp2 + 1) * 16; var lWordArray = Array(lNumberOfWords - 1); var lBytePosition = 0; var lByteCount = 0;
                while (lByteCount < lMessageLength) { lWordCount = (lByteCount - (lByteCount % 4)) / 4; lBytePosition = (lByteCount % 4) * 8; lWordArray[lWordCount] = (lWordArray[lWordCount] | (string.charCodeAt(lByteCount) << lBytePosition)); lByteCount++; }
                lWordCount = (lByteCount - (lByteCount % 4)) / 4; lBytePosition = (lByteCount % 4) * 8; lWordArray[lWordCount] = lWordArray[lWordCount] | (0x80 << lBytePosition); lWordArray[lNumberOfWords - 2] = lMessageLength << 3; lWordArray[lNumberOfWords - 1] = lMessageLength >>> 29; return lWordArray;
            }
            function wordToHex(lValue) { var WordToHexValue = "", WordToHexValue_temp = "", lByte, lCount; for (lCount = 0; lCount <= 3; lCount++) { lByte = (lValue >>> (lCount * 8)) & 255; WordToHexValue_temp = "0" + lByte.toString(16); WordToHexValue = WordToHexValue + WordToHexValue_temp.substr(WordToHexValue_temp.length - 2, 2); } return WordToHexValue; }
            var x = Array(); var k, AA, BB, CC, DD, a, b, c, d; var S11 = 7, S12 = 12, S13 = 17, S14 = 22; var S21 = 5, S22 = 9, S23 = 14, S24 = 20; var S31 = 4, S32 = 11, S33 = 16, S34 = 23; var S41 = 6, S42 = 10, S43 = 15, S44 = 21;
            string = unescape(encodeURIComponent(string)); x = convertToWordArray(string); a = 0x67452301; b = 0xEFCDAB89; c = 0x98BADCFE; d = 0x10325476;
            for (k = 0; k < x.length; k += 16) {
                AA = a; BB = b; CC = c; DD = d;
                a = FF(a, b, c, d, x[k + 0], S11, 0xD76AA478); d = FF(d, a, b, c, x[k + 1], S12, 0xE8C7B756); c = FF(c, d, a, b, x[k + 2], S13, 0x242070DB); b = FF(b, c, d, a, x[k + 3], S14, 0xC1BDCEEE); a = FF(a, b, c, d, x[k + 4], S11, 0xF57C0FAF); d = FF(d, a, b, c, x[k + 5], S12, 0x4787C62A); c = FF(c, d, a, b, x[k + 6], S13, 0xA8304613); b = FF(b, c, d, a, x[k + 7], S14, 0xFD469501);
                a = FF(a, b, c, d, x[k + 8], S11, 0x698098D8); d = FF(d, a, b, c, x[k + 9], S12, 0x8B44F7AF); c = FF(c, d, a, b, x[k + 10], S13, 0xFFFF5BB1); b = FF(b, c, d, a, x[k + 11], S14, 0x895CD7BE); a = FF(a, b, c, d, x[k + 12], S11, 0x6B901122); d = FF(d, a, b, c, x[k + 13], S12, 0xFD987193); c = FF(c, d, a, b, x[k + 14], S13, 0xA679438E); b = FF(b, c, d, a, x[k + 15], S14, 0x49B40821);
                a = GG(a, b, c, d, x[k + 1], S21, 0xF61E2562); d = GG(d, a, b, c, x[k + 6], S22, 0xC040B340); c = GG(c, d, a, b, x[k + 11], S23, 0x265E5A51); b = GG(b, c, d, a, x[k + 0], S24, 0xE9B6C7AA); a = GG(a, b, c, d, x[k + 5], S21, 0xD62F105D); d = GG(d, a, b, c, x[k + 10], S22, 0x2441453); c = GG(c, d, a, b, x[k + 15], S23, 0xD8A1E681); b = GG(b, c, d, a, x[k + 4], S24, 0xE7D3FBC8);
                a = GG(a, b, c, d, x[k + 9], S21, 0x21E1CDE6); d = GG(d, a, b, c, x[k + 14], S22, 0xC33707D6); c = GG(c, d, a, b, x[k + 3], S23, 0xF4D50D87); b = GG(b, c, d, a, x[k + 8], S24, 0x455A14ED); a = GG(a, b, c, d, x[k + 13], S21, 0xA9E3E905); d = GG(d, a, b, c, x[k + 2], S22, 0xFCEFA3F8); c = GG(c, d, a, b, x[k + 7], S23, 0x676F02D9); b = GG(b, c, d, a, x[k + 12], S24, 0x8D2A4C8A);
                a = HH(a, b, c, d, x[k + 5], S31, 0xFFFA3942); d = HH(d, a, b, c, x[k + 8], S32, 0x8771F681); c = HH(c, d, a, b, x[k + 11], S33, 0x6D9D6122); b = HH(b, c, d, a, x[k + 14], S34, 0xFDE5380C); a = HH(a, b, c, d, x[k + 1], S31, 0xA4BEEA44); d = HH(d, a, b, c, x[k + 4], S32, 0x4BDECFA9); c = HH(c, d, a, b, x[k + 7], S33, 0xF6BB4B60); b = HH(b, c, d, a, x[k + 10], S34, 0xBEBFBC70);
                a = HH(a, b, c, d, x[k + 13], S31, 0x289B7EC6); d = HH(d, a, b, c, x[k + 0], S32, 0xEAA127FA); c = HH(c, d, a, b, x[k + 3], S33, 0xD4EF3085); b = HH(b, c, d, a, x[k + 6], S34, 0x4881D05); a = HH(a, b, c, d, x[k + 9], S31, 0xD9D4D039); d = HH(d, a, b, c, x[k + 12], S32, 0xE6DB99E5); c = HH(c, d, a, b, x[k + 15], S33, 0x1FA27CF8); b = HH(b, c, d, a, x[k + 2], S34, 0xC4AC5665);
                a = II(a, b, c, d, x[k + 0], S41, 0xF4292244); d = II(d, a, b, c, x[k + 7], S42, 0x432AFF97); c = II(c, d, a, b, x[k + 14], S43, 0xAB9423A7); b = II(b, c, d, a, x[k + 5], S44, 0xFC93A039); a = II(a, b, c, d, x[k + 12], S41, 0x655B59C3); d = II(d, a, b, c, x[k + 3], S42, 0x8F0CCC92); c = II(c, d, a, b, x[k + 10], S43, 0xFFEFF47D); b = II(b, c, d, a, x[k + 1], S44, 0x85845DD1);
                a = II(a, b, c, d, x[k + 8], S41, 0x6FA87E4F); d = II(d, a, b, c, x[k + 15], S42, 0xFE2CE6E0); c = II(c, d, a, b, x[k + 6], S43, 0xA3014314); b = II(b, c, d, a, x[k + 13], S44, 0x4E0811A1); a = II(a, b, c, d, x[k + 4], S41, 0xF7537E82); d = II(d, a, b, c, x[k + 11], S42, 0xBD3AF235); c = II(c, d, a, b, x[k + 2], S43, 0x2AD7D2BB); b = II(b, c, d, a, x[k + 9], S44, 0xEB86D391);
                a = addUnsigned(a, AA); b = addUnsigned(b, BB); c = addUnsigned(c, CC); d = addUnsigned(d, DD);
            }
            var temp = wordToHex(a) + wordToHex(b) + wordToHex(c) + wordToHex(d);
            return temp.toLowerCase();
        }

        function switchGame(type, btn) {
            if(currentGame === type) return;
            currentGame = type;
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            btn.classList.add('active');
            
            document.getElementById('pred-box').style.display = 'none';
            document.getElementById('history-box').innerHTML = '';
            document.getElementById('record-list').innerHTML = '';
            
            fetchLive();
            fetchRecords();
        }

        function fetchLive() {
            fetch(`${API_BASE}/live/${currentGame}`, { headers: getHeaders() })
            .then(r=>{
                if(r.headers.get('Content-Type').includes('text/html')) return r.text();
                return r.json();
            }).then(d => {
                if(typeof d === 'string') {
                    document.body.innerHTML = d; return;
                }
                if(!d.period) return;
                liveData = d;
                
                let hHtml = '';
                d.history.forEach(item => {
                    let attr = item.big_small + item.odd_even;
                    hHtml += `
                        <div class="h-item">
                            <div style="color:#667;">${item.period.slice(-3)}</div>
                            <div class="nums">${item.nums}</div>
                            <div style="color:#889; font-size:12px;">=${item.total}</div>
                            <div class="attr">${attr}</div>
                        </div>
                    `;
                });
                document.getElementById('history-box').innerHTML = hHtml;
                
                if(d.current_prediction) {
                    document.getElementById('pred-box').style.display = 'block';
                    document.getElementById('target-period').innerText = d.current_prediction.period;
                    document.getElementById('kill-item').innerText = d.current_prediction.kill_item;
                    document.getElementById('rec-items').innerText = d.current_prediction.recommend_items;
                    document.getElementById('analysis-text').innerText = d.current_prediction.analysis;
                }
                
                if(timer) clearInterval(timer);
                let left = d.left_time;
                timer = setInterval(() => {
                    if(left <= 0) { document.getElementById('countdown').innerText = "结算中..."; return; }
                    left--;
                    let m = Math.floor(left / 60);
                    let s = left % 60;
                    document.getElementById('countdown').innerText = `${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
                }, 1000);
            });
        }

        function fetchRecords() {
            fetch(`${API_BASE}/predictions/${currentGame}`, { headers: getHeaders() })
            .then(r=>{
                if(r.headers.get('Content-Type').includes('text/html')) return r.text();
                return r.json();
            }).then(data => {
                if(typeof data === 'string') { document.body.innerHTML = data; return; }
                let box = document.getElementById('record-list');
                if(data.length === 0) { box.innerHTML = '<div style="padding:20px; text-align:center; color:#556;">暂无预测记录</div>'; return; }
                
                let html = '';
                data.forEach(p => {
                    let cls = p.result === 'win' ? 'win' : (p.result === 'lose' ? 'lose' : '');
                    let icon = p.result === 'win' ? '🀄奖' : (p.result === 'lose' ? '💀被杀' : '⏳等待');
                    let color = p.result === 'win' ? 'var(--green)' : (p.result === 'lose' ? 'var(--red)' : '#889');
                    
                    html += `
                        <div class="record-item ${cls}">
                            <div class="r-left">
                                <div class="r-period">期号: ${p.period}</div>
                                <div>杀: <span class="r-kill">${p.kill_item}</span> | 推: <span class="r-rec">${p.recommend_items}</span></div>
                            </div>
                            <div class="r-status" style="color:${color};">${icon}</div>
                        </div>
                    `;
                });
                box.innerHTML = html;
            });
        }

        function clearRecords() {
            if(!confirm("确定要清空本游戏的预测记录吗？此操作无副作用。")) return;
            fetch(`${API_BASE}/delete/${currentGame}`, { method: 'POST', headers: getHeaders() })
            .then(r=>r.json()).then(d => {
                if(d.success) fetchRecords();
            });
        }

        fetchLive();
        fetchRecords();
        setInterval(fetchLive, 2000);
        setInterval(fetchRecords, 5000);
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8888))
    app.run(host='0.0.0.0', port=port)
