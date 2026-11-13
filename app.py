import urllib.request
import ssl
import gzip
import re
import json
import time
import threading
import os
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta, timezone

PORT = int(os.environ.get("PORT", 8888))

# ================== 【电报机器人配置】 ==================
TELEGRAM_CONFIG = {
    "2": {"token": "9025598598:AAG8f9OiSxhHmdzephHub_OpPidk2_mq8ss", "chat_id": "8770794344", "name": "加拿大28"},
    "3": {"token": "9059984335:AAHDutIGL7RDXWIPpEJ5Opjhj_Q8fBn-eVI", "chat_id": "8770794344", "name": "分分28"}, 
    "13": {"token": "9013441843:AAHrZhx3yvgwOsHp8k7MrzASaNEcNSgUgK0", "chat_id": "8770794344", "name": "比特28"}
}

# 状态记录（每个类型独立）
BOT_STATE = {
    "2": {"last_period": "", "last_cd_sec": -1},
    "3": {"last_period": "", "last_cd_sec": -1},
    "13": {"last_period": "", "last_cd_sec": -1}
}

SECURE_API_PATH = "/api/v6/core/stream"
SIGN_SECRET = "yc28_cyber_salt_v6_2026"
TIME_WINDOW = 2.0 

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

TYPE_MAP = {
    "2": {"name": "加拿大28", "url": "https://kjsix28.com/", "interval": 210},        
    "3": {"name": "分分28",   "url": "https://kjsix28.com/portal/fenfen28", "interval": 60},  
    "13": {"name": "比特28",  "url": "https://kjsix28.com/portal/btc28", "interval": 60}      
}

CACHE_DATA = {
    "2": {"data": [], "next_draw_time": ""},
    "3": {"data": [], "next_draw_time": ""},
    "13": {"data": [], "next_draw_time": ""}
}

# ================== 电报发送函数 ==================
def send_telegram_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            pass
    except Exception as e:
        print(f"❌ 发送失败: {e}")

# ================== 独立抓取与播报线程（解决两个不播报的问题） ==================
def worker_for_type(t_type):
    cfg = TYPE_MAP[t_type]
    print(f"🚀 电报机器人 [{cfg['name']}] 独立监控线程已启动")
    
    while True:
        try:
            req = urllib.request.Request(cfg["url"], headers=HEADERS)
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                data = response.read()
                if response.info().get('Content-Encoding') == 'gzip':
                    data = gzip.decompress(data)
                html = data.decode('utf-8', errors='ignore')
                clean_pattern = re.compile(r'<[^>]+>')
                plain_text = clean_pattern.sub(' ', html)
                plain_text = re.sub(r'\s+', ' ', plain_text).strip()
                row_pattern = re.compile(r'(\d{7,}).*?(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}).*?(\d+)\s*\+\s*(\d+)\s*\+\s*(\d+)\s*=\s*(\d+)')

                records = []
                latest_draw_time = None
                for match in row_pattern.finditer(plain_text):
                    period = match.group(1)
                    draw_time = match.group(2)
                    n1, n2, n3, total = map(int, match.groups()[2:])
                    if n1 + n2 + n3 != total: continue
                    big_small = '小' if total <= 13 else '大'
                    odd_even = '双' if total % 2 == 0 else '单'
                    if not latest_draw_time: latest_draw_time = draw_time
                    records.append({
                        'period': period, 'draw_time': draw_time,
                        'num1': n1, 'num2': n2, 'num3': n3, 'total': total,
                        'big_small': big_small, 'odd_even': odd_even
                    })
                
                if records:
                    next_draw_time = ""
                    if latest_draw_time:
                        dt_next = datetime.strptime(latest_draw_time, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=cfg["interval"])
                        next_draw_time = dt_next.strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 更新缓存
                    CACHE_DATA[t_type] = {"data": records[:30], "next_draw_time": next_draw_time}
                    
                    latest_period = records[0]['period']
                    
                    # 1. 判定是否出了新开奖
                    if BOT_STATE[t_type]["last_period"] != latest_period:
                        BOT_STATE[t_type]["last_period"] = latest_period
                        BOT_STATE[t_type]["last_cd_sec"] = -1 # 重置倒计时状态
                        
                        # 组装近期30期
                        history_text = ""
                        for r in records[:30]: 
                            history_text += f"{r['period']}期: {r['num1']}+{r['num2']}+{r['num3']}={r['total']} ({r['big_small']}{r['odd_even']})\n"

                        top = records[0]
                        msg = (
                            f"🔥【{cfg['name']}】最新开奖结果 🔥\n\n"
                            f"期号：{top['period']}\n"
                            f"开奖：{top['num1']} + {top['num2']} + {top['num3']} = {top['total']}\n"
                            f"属性：{top['big_small']} {top['odd_even']}\n\n"
                            f"📊 近期30期记录：\n{history_text}"
                        )
                        send_telegram_message(TELEGRAM_CONFIG[t_type]["token"], TELEGRAM_CONFIG[t_type]["chat_id"], msg)
                    
                    # 2. 独立判定最后5秒倒计时跳动
                    else:
                        if next_draw_time:
                            # 严格按照北京时间校准
                            now_utc = datetime.now(timezone.utc)
                            dt_next = datetime.strptime(next_draw_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) - timedelta(hours=8)
                            diff = int((dt_next - now_utc).total_seconds())
                            
                            # 如果在 1~5 秒内，并且和上一次发的秒数不同，才发消息（防刷屏，每秒必达）
                            if 1 <= diff <= 5 and BOT_STATE[t_type]["last_cd_sec"] != diff:
                                BOT_STATE[t_type]["last_cd_sec"] = diff
                                cd_msg = f"⏳【{cfg['name']}】距离下一期开奖，还剩 {diff} 秒！"
                                send_telegram_message(TELEGRAM_CONFIG[t_type]["token"], TELEGRAM_CONFIG[t_type]["chat_id"], cd_msg)

        except Exception as e:
            pass
        
        time.sleep(1) # 每秒查一次

# ================== Web 路由模块 ==================
class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            query = parse_qs(parsed_url.query)
            
            if path == '/' or path == '/index.html' or path == '/favicon.ico':
                self.send_response(200)
                if path != '/favicon.ico': self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                if path != '/favicon.ico': self.wfile.write(HTML_PAGE.encode('utf-8'))
                return

            # 站长明文专属接口
            if path in ["/vipQQWW9983/8626/0549CASWWW", "/vipQQWW9986/8626/0549CFKFGH", "/vipQQWW9983/8626/0549CCBDR"]:
                t_type = query.get('type', ['2'])[0]
                payload = CACHE_DATA.get(t_type, {})
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(payload, ensure_ascii=False, indent=4).encode('utf-8'))
                return

            # 网页防抓包通道
            if path == SECURE_API_PATH:
                referer = self.headers.get('Referer', '')
                user_agent = self.headers.get('User-Agent', '')
                req_time_str = self.headers.get('X-Req-Time', '')
                req_sign = self.headers.get('X-Req-Sign', '')
                
                is_hacker = False
                if 'yc28cn' not in referer and 'onrender.com' not in referer: is_hacker = True
                elif 'Mozilla' not in user_agent and 'Chrome' not in user_agent: is_hacker = True
                elif not req_time_str or not req_sign: is_hacker = True
                else:
                    try:
                        if abs(time.time() - float(req_time_str) / 1000.0) > TIME_WINDOW: is_hacker = True
                    except: is_hacker = True
                
                if is_hacker:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.end_headers()
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
                    self.wfile.write(mock_html.encode('utf-8'))
                    return
                
                if req_sign != hashlib.md5(f"{req_time_str}{SIGN_SECRET}".encode('utf-8')).hexdigest():
                    self.send_response(403)
                    self.end_headers()
                    return

                t_type = query.get('type', ['2'])[0]
                payload = CACHE_DATA.get(t_type, {})
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8').hex().encode('utf-8'))
                return

            self.send_response(404)
            self.end_headers()
        except Exception:
            pass

    def log_message(self, format, *args):
        pass

# ================== 网页前端代码 ==================
HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>舰长 · 智算中枢</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
        :root {
            --bg: #02040a; --panel: rgba(6, 12, 24, 0.85); --cyan: #00f3ff;
            --red: #ff003c; --green: #39ff14; --text: #e0f0ff; --muted: #5a759e;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Share Tech Mono', monospace; background: var(--bg); color: var(--text); min-height: 100vh; overflow-x: hidden; position: relative; }
        .cyber-grid {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1;
            background-image: linear-gradient(rgba(0, 243, 255, 0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 243, 255, 0.04) 1px, transparent 1px);
            background-size: 30px 30px; perspective: 500px;
        }
        .scanlines {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 100; pointer-events: none;
            background: linear-gradient(to bottom, rgba(255,255,255,0), rgba(255,255,255,0) 50%, rgba(0,0,0,0.3) 50%, rgba(0,0,0,0.3));
            background-size: 100% 4px; opacity: 0.6;
        }
        .app { max-width: 800px; margin: 0 auto; padding: 15px; position: relative; z-index: 10; }
        .header { text-align: center; margin-bottom: 25px; padding-top: 10px; }
        .title { font-size: 26px; color: var(--cyan); letter-spacing: 4px; font-weight: bold; text-shadow: 0 0 10px rgba(0,243,255,0.8), 0 0 20px rgba(0,243,255,0.4); }
        .panel { background: var(--panel); border: 1px solid rgba(0,243,255,0.3); border-radius: 2px; padding: 20px; margin-bottom: 20px; position: relative; box-shadow: 0 0 15px rgba(0,243,255,0.05); }
        .panel::before { content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--cyan); box-shadow: 0 0 10px var(--cyan); }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab-btn { flex: 1; background: transparent; border: 1px solid var(--muted); color: var(--muted); padding: 12px 0; text-align: center; font-size: 14px; cursor: pointer; transition: all 0.3s; font-weight: bold; user-select: none; }
        .tab-btn.active { border-color: var(--cyan); color: var(--cyan); background: rgba(0,243,255,0.1); box-shadow: inset 0 0 15px rgba(0,243,255,0.2); }
        .latest-box { display: flex; justify-content: space-between; align-items: center; background: linear-gradient(90deg, rgba(255,0,60,0.1) 0%, transparent 100%); border-left: 3px solid var(--red); padding: 15px; }
        .latest-label { font-size: 12px; color: var(--red); letter-spacing: 1px; margin-bottom: 5px;}
        .latest-data { font-size: 24px; font-weight: bold; color: var(--cyan); text-shadow: 0 0 8px rgba(0,243,255,0.5); }
        .latest-data span { color: var(--text); font-size: 18px; margin: 0 5px; }
        .countdown-box { text-align: right; }
        .cd-title { font-size: 12px; color: var(--muted); margin-bottom: 5px; }
        .cd-time { font-size: 26px; font-weight: bold; color: var(--green); text-shadow: 0 0 10px rgba(57,255,20,0.6); font-variant-numeric: tabular-nums; }
        .cd-time.urgent { color: var(--red); text-shadow: 0 0 15px rgba(255,0,60,0.8); animation: pulse 0.5s infinite alternate; }
        @keyframes pulse { 0% { opacity: 0.8; } 100% { opacity: 1; } }
        .table-container { border: 1px solid rgba(0,243,255,0.2); background: var(--panel); }
        .thead { display: flex; background: rgba(0,243,255,0.05); padding: 12px 10px; font-size: 13px; color: var(--muted); border-bottom: 1px solid rgba(0,243,255,0.2); }
        .trow { display: flex; padding: 15px 10px; font-size: 15px; border-bottom: 1px solid rgba(255,255,255,0.03); align-items: center; }
        .trow.new-row { animation: scanAnim 3s ease-out; }
        @keyframes scanAnim { 0% { background: rgba(57,255,20,0.4); } 100% { background: transparent; } }
        .c1 { flex: 1.2; color: var(--muted); } .c2 { flex: 1; color: var(--muted); font-size: 12px; } .c3 { flex: 2; text-align: center; font-weight: bold; } .c4 { flex: 0.8; text-align: center; font-weight: bold; font-size: 18px; } .c5 { flex: 0.8; text-align: center; font-weight: bold;} .c6 { flex: 0.8; text-align: center; font-weight: bold;}
        .red { color: var(--red); } .cyan { color: var(--cyan); } .green { color: var(--green); }
    </style>
</head>
<body oncontextmenu="return false;">
    <div class="cyber-grid"></div>
    <div class="scanlines"></div>
    <div class="app">
        <div class="header"><div class="title">/// 舰长智算中枢 ///</div></div>
        <div class="panel">
            <div class="tabs">
                <div class="tab-btn active" onclick="switchType('2', this)">加拿大28</div>
                <div class="tab-btn" onclick="switchType('3', this)">分分28</div>
                <div class="tab-btn" onclick="switchType('13', this)">比特28</div>
            </div>
            <div class="latest-box">
                <div>
                    <div class="latest-label" id="type-name">[系统加载中...]</div>
                    <div class="latest-data" id="top-data">-- <span>+</span> -- <span>+</span> -- <span>=</span> --</div>
                </div>
                <div class="countdown-box">
                    <div class="cd-title">距离下一期</div>
                    <div class="cd-time" id="countdown">--:--</div>
                </div>
            </div>
        </div>
        <div class="table-container">
            <div class="thead"><div class="c1">期号</div><div class="c2">时间</div><div class="c3">开奖号码</div><div class="c4">总和</div><div class="c5">大小</div><div class="c6">单双</div></div>
            <div id="list"></div>
        </div>
    </div>
    <script>
        document.onkeydown = function(e) {
            if (e.keyCode === 123 || (e.ctrlKey && e.shiftKey && (e.keyCode === 73 || e.keyCode === 74)) || (e.ctrlKey && e.keyCode === 85)) {
                return false;
            }
        };
        const SECURE_API = "/api/v6/core/stream";
        const SIGN_SECRET = "yc28_cyber_salt_v6_2026";
        let currentType = '2'; let prevPeriod = ""; let targetTime = null; let timerInterval = null; let lastFetchedPeriod = "";
        
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
        
        function switchType(type, btnEl) {
            if (currentType === type) return;
            currentType = type; prevPeriod = ""; 
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            btnEl.classList.add('active');
            document.getElementById('top-data').innerHTML = "-- <span>+</span> -- <span>+</span> -- <span>=</span> --";
            document.getElementById('list').innerHTML = "";
            document.getElementById('countdown').innerText = "--:--";
            targetTime = null; update();
        }
        
        function startCountdown(targetTimeStr) {
            if (!targetTimeStr) return;
            const t = targetTimeStr.replace(/-/g, '/');
            targetTime = new Date(t).getTime();
            if (timerInterval) clearInterval(timerInterval);
            timerInterval = setInterval(() => {
                const now = new Date().getTime();
                const diff = targetTime - now;
                const cdEl = document.getElementById('countdown');
                if (diff <= 0) {
                    cdEl.innerText = "开奖中...";
                    cdEl.classList.add('urgent');
                    if (diff > -2000) update(); 
                } else {
                    const m = Math.floor(diff / 60000);
                    const s = Math.floor((diff % 60000) / 1000);
                    cdEl.innerText = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
                    if (diff < 10000) { cdEl.classList.add('urgent'); } else { cdEl.classList.remove('urgent'); }
                }
            }, 100);
        }
        
        async function update() {
            try {
                const timeStamp = Date.now().toString();
                const sign = md5(timeStamp + SIGN_SECRET);
                const r = await fetch(`${SECURE_API}?type=${currentType}`, {
                    headers: { 'X-Req-Time': timeStamp, 'X-Req-Sign': sign }
                });
                const text = await r.text();
                let j;
                try {
                    if (/^[0-9a-fA-F]+$/.test(text)) {
                        const jsonStr = decodeURIComponent(text.replace(/../g, '%$&'));
                        j = JSON.parse(jsonStr);
                    } else { return; }
                } catch(e) { return; }
                if (j && j.data && j.data.length > 0) {
                    const top = j.data[0];
                    document.getElementById('type-name').innerText = `[ ${j.name} · 实时接入 ]`;
                    let cTopB = top.big_small === '大' ? 'red' : 'cyan';
                    document.getElementById('top-data').innerHTML = `${top.period}期 : <span class="${cTopB}">${top.num1}</span> <span>+</span> <span class="${cTopB}">${top.num2}</span> <span>+</span> <span class="${cTopB}">${top.num3}</span> <span>=</span> <span class="green">${top.total}</span>`;
                    let isNew = (prevPeriod !== "" && prevPeriod !== top.period);
                    prevPeriod = top.period;
                    if (lastFetchedPeriod !== top.period) {
                        lastFetchedPeriod = top.period;
                        startCountdown(j.next_draw_time);
                    }
                    let html = "";
                    j.data.forEach((row, idx) => {
                        let cB = row.big_small === '大' ? 'red' : 'cyan';
                        let cO = row.odd_even === '单' ? 'red' : 'cyan';
                        let cls = (isNew && idx === 0) ? 'new-row' : '';
                        let t = row.draw_time ? row.draw_time.substring(11,19) : "--:--";
                        html += `<div class="trow ${cls}">
                            <div class="c1">${row.period}</div>
                            <div class="c2">${t}</div>
                            <div class="c3"><span class="${cB}">${row.num1}</span>+<span class="${cB}">${row.num2}</span>+<span class="${cB}">${row.num3}</span></div>
                            <div class="c4 green">${row.total}</div>
                            <div class="c5 ${cB}">${row.big_small}</div>
                            <div class="c6 ${cO}">${row.odd_even}</div>
                        </div>`;
                    });
                    document.getElementById('list').innerHTML = html;
                }
            } catch (e) {}
        }
        setInterval(update, 1000); update();
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    # 启动三个独立的监控线程（解决加拿大和比特无响应的问题）
    for t in TYPE_MAP.keys():
        threading.Thread(target=worker_for_type, args=(t,), daemon=True).start()
        time.sleep(0.5)

    server = HTTPServer(('0.0.0.0', PORT), RequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
