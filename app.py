import urllib.request
import ssl
import gzip
import re
import json
import time
import threading
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

# ================== 云端适配核心 ==================
PORT = int(os.environ.get("PORT", 8888))

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

def fetch_single_type(t_type):
    cfg = TYPE_MAP[t_type]
    url = cfg["url"]
    interval_sec = cfg["interval"]
    
    try:
        req = urllib.request.Request(url, headers=HEADERS)
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

                if n1 + n2 + n3 != total:
                    continue

                big_small = '小' if total <= 13 else '大'
                odd_even = '双' if total % 2 == 0 else '单'

                if not latest_draw_time:
                    latest_draw_time = draw_time

                records.append({
                    'period': period, 'draw_time': draw_time,
                    'num1': n1, 'num2': n2, 'num3': n3, 'total': total,
                    'big_small': big_small, 'odd_even': odd_even
                })
            
            if records:
                next_draw_time = ""
                if latest_draw_time:
                    dt_latest = datetime.strptime(latest_draw_time, "%Y-%m-%d %H:%M:%S")
                    dt_next = dt_latest + timedelta(seconds=interval_sec)
                    next_draw_time = dt_next.strftime("%Y-%m-%d %H:%M:%S")

                CACHE_DATA[t_type] = {
                    "data": records[:50],
                    "next_draw_time": next_draw_time
                }
    except Exception:
        pass

def background_worker():
    for t in TYPE_MAP.keys():
        fetch_single_type(t)
        time.sleep(0.5)
        
    while True:
        for t in TYPE_MAP.keys():
            fetch_single_type(t)
            time.sleep(0.5)
        time.sleep(5)

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            
            if path == '/' or path == '/index.html':
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(HTML_PAGE.encode('utf-8'))
                
            elif path == '/api/draws':
                query = parse_qs(parsed_url.query)
                t_type = query.get('type', ['2'])[0]
                
                payload = CACHE_DATA.get(t_type, {"data": [], "next_draw_time": ""})
                resp = json.dumps({
                    "code": 200, 
                    "data": payload["data"], 
                    "next_draw_time": payload["next_draw_time"],
                    "name": TYPE_MAP.get(t_type, {}).get("name", "未知")
                }, ensure_ascii=False).encode('utf-8')
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(resp)
                
            elif path == '/favicon.ico':
                self.send_response(200)
                self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()
        except Exception:
            pass

    def log_message(self, format, *args):
        pass

HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>舰长 · 云端终端</title>
    <style>
        :root { --bg: #03050a; --panel: rgba(8,12,22,0.85); --cyan: #00f3ff; --red: #ff003c; --green: #39ff14; --text: #d0def0; --muted: #576b8a; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: monospace; background: var(--bg); color: var(--text); background-image: linear-gradient(rgba(0,243,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,243,255,0.03) 1px, transparent 1px); background-size: 25px 25px; min-height: 100vh; }
        body::after { content: " "; display: block; position: fixed; top: 0; left: 0; bottom: 0; right: 0; background: linear-gradient(rgba(18,16,16,0) 50%, rgba(0,0,0,0.2) 50%); z-index: 99; background-size: 100% 4px; pointer-events: none; }
        .app { max-width: 800px; margin: 0 auto; padding: 15px; position: relative; z-index: 10; }
        .panel { background: var(--panel); border: 1px solid var(--cyan); border-radius: 4px; padding: 20px; margin-bottom: 20px; position: relative; }
        .corner { position: absolute; width: 8px; height: 8px; border: 2px solid var(--cyan); }
        .tl { top: -2px; left: -2px; border-right: none; border-bottom: none; }
        .tr { top: -2px; right: -2px; border-left: none; border-bottom: none; }
        .bl { bottom: -2px; left: -2px; border-right: none; border-top: none; }
        .br { bottom: -2px; right: -2px; border-left: none; border-top: none; }
        .title { text-align: center; font-size: 20px; color: var(--cyan); text-shadow: 0 0 10px rgba(0,243,255,0.4); letter-spacing: 2px; margin-bottom: 15px; }
        .tabs { display: flex; gap: 8px; margin-bottom: 15px; }
        .tab-btn { flex: 1; background: rgba(0,243,255,0.05); border: 1px solid var(--muted); color: var(--muted); padding: 12px 0; text-align: center; border-radius: 4px; cursor: pointer; font-size: 14px; transition: all 0.2s; font-weight: bold; user-select: none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .tab-btn.active { background: rgba(0,243,255,0.15); border-color: var(--cyan); color: var(--cyan); box-shadow: 0 0 10px rgba(0,243,255,0.2) inset; }
        .latest { display: flex; justify-content: space-between; align-items: center; background: rgba(255,0,60,0.05); border-left: 3px solid var(--red); padding: 12px; }
        .data { font-size: 20px; font-weight: bold; color: var(--cyan); margin-top: 4px; }
        .countdown-box { text-align: right; }
        .cd-title { font-size: 12px; color: var(--muted); margin-bottom: 2px; }
        .cd-time { font-size: 22px; font-weight: bold; color: var(--green); text-shadow: 0 0 8px rgba(57,255,20,0.4); }
        .cd-time.urgent { color: var(--red); text-shadow: 0 0 8px rgba(255,0,60,0.6); animation: blink 0.5s infinite alternate; }
        @keyframes blink { 0% { opacity: 0.4; } 100% { opacity: 1; } }
        .table { border: 1px solid rgba(255,255,255,0.1); background: var(--panel); }
        .thead { display: flex; background: rgba(0,243,255,0.1); padding: 10px; font-size: 12px; color: var(--cyan); font-weight: bold; }
        .trow { display: flex; padding: 12px 10px; font-size: 14px; border-bottom: 1px solid rgba(255,255,255,0.05); align-items: center; }
        .trow.new { animation: high 2s ease-out; }
        @keyframes high { 0% { background: rgba(57,255,20,0.3); } 100% { background: transparent; } }
        .c1 { flex: 1.2; color: var(--muted); } .c2 { flex: 1; color: var(--muted); font-size: 12px; } .c3 { flex: 2; text-align: center; font-weight: bold; } .c4 { flex: 0.8; text-align: center; font-weight: bold; } .c5 { flex: 0.8; text-align: center; } .c6 { flex: 0.8; text-align: center; }
        .red { color: var(--red); } .cyan { color: var(--cyan); } .green { color: var(--green); }
    </style>
</head>
<body>
    <div class="app">
        <div class="panel">
            <div class="corner tl"></div><div class="corner tr"></div><div class="corner bl"></div><div class="corner br"></div>
            <div class="title">/// 舰长云端终端 ///</div>
            <div class="tabs">
                <div class="tab-btn active" onclick="switchType('2', this)">加拿大28</div>
                <div class="tab-btn" onclick="switchType('3', this)">分分28</div>
                <div class="tab-btn" onclick="switchType('13', this)">比特28</div>
            </div>
            <div class="latest">
                <div>
                    <div style="font-size:12px; color:var(--muted)" id="type-name">加载中...</div>
                    <div class="data" id="top-data">--</div>
                </div>
                <div class="countdown-box">
                    <div class="cd-title">距离下一期</div>
                    <div class="cd-time" id="countdown">--:--</div>
                </div>
            </div>
        </div>
        <div class="table">
            <div class="thead"><div class="c1">期号</div><div class="c2">时间</div><div class="c3">开奖号码</div><div class="c4">总和</div><div class="c5">大小</div><div class="c6">单双</div></div>
            <div id="list"></div>
        </div>
    </div>
    <script>
        let currentType = '2'; 
        let prevPeriod = ""; 
        let targetTime = null;
        let timerInterval = null;
        let lastFetchedPeriod = "";

        function switchType(type, btnEl) {
            if (currentType === type) return;
            currentType = type;
            prevPeriod = ""; 
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            btnEl.classList.add('active');
            document.getElementById('top-data').innerText = "加载中...";
            document.getElementById('list').innerHTML = "";
            document.getElementById('countdown').innerText = "--:--";
            targetTime = null;
            update();
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
                    cdEl.innerText = `${m.toString().padStart(2, '0')}分 ${s.toString().padStart(2, '0')}秒`;
                    if (diff < 10000) { cdEl.classList.add('urgent'); } else { cdEl.classList.remove('urgent'); }
                }
            }, 100);
        }

        async function update() {
            try {
                const r = await fetch(`/api/draws?type=${currentType}`);
                const j = await r.json();
                if (j.code === 200 && j.data.length > 0) {
                    const top = j.data[0];
                    document.getElementById('type-name').innerText = j.name + " · 最新一期";
                    document.getElementById('top-data').innerText = `${top.period}期 : ${top.num1} + ${top.num2} + ${top.num3} = ${top.total}`;
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
                        let cls = (isNew && idx === 0) ? 'new' : '';
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
        update(); 
        setInterval(update, 2000); 
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    threading.Thread(target=background_worker, daemon=True).start()
    print(f"🚀 云端服务启动，监听端口: {PORT}")
    
    server = HTTPServer(('0.0.0.0', PORT), RequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
