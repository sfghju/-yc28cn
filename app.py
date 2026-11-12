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

PORT = int(os.environ.get("PORT", 8888))

# ================== 【安全层】 核心配置 ==================
ADMIN_PASSWORD = "captain888"         # 你的登录密码
SECRET_TOKEN = "yc28_secure_token_2026" # 免封神盾 Token
SECURE_API_PATH = "/api/v3/sys/kernel_check"

IP_TRACKER = {}

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
                CACHE_DATA[t_type] = {"data": records[:50], "next_draw_time": next_draw_time}
    except Exception:
        pass

def background_worker():
    while True:
        for t in TYPE_MAP.keys():
            fetch_single_type(t)
            time.sleep(0.5)
        time.sleep(3)

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            
            if path == '/' or path == '/index.html' or path == '/favicon.ico':
                self.send_response(200)
                if path != '/favicon.ico': self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                if path != '/favicon.ico': self.wfile.write(HTML_PAGE.encode('utf-8'))
                return

            if path == SECURE_API_PATH:
                client_ip = self.headers.get('X-Forwarded-For', self.client_address[0]).split(',')[0].strip()
                now = time.time()
                auth_token = self.headers.get('X-Auth-Token', '')

                # ================== 【核心特权】 ==================
                # 如果是站长（Token正确），完全跳过所有高频检测，随便刷！
                if auth_token == SECRET_TOKEN:
                    is_admin = True
                else:
                    is_admin = False

                # 外部人员的高频拦截
                if not is_admin:
                    if client_ip in IP_TRACKER:
                        last_req, ban_until = IP_TRACKER[client_ip]
                        if now < ban_until:
                            self.send_error(403, "IP Banned")
                            return
                        if now - last_req < 2.0: 
                            IP_TRACKER[client_ip] = [now, now + 600] 
                            self.send_response(429)
                            self.end_headers()
                            self.wfile.write(b"Rate limit exceeded. IP Banned.")
                            return
                    IP_TRACKER[client_ip] = [now, 0]

                # 防盗链
                referer = self.headers.get('Referer', '')
                if 'yc28cn' not in referer and 'onrender.com' not in referer:
                    self.send_error(403, "Direct access denied")
                    return

                # 非法 Token 拦截并喂假数据
                if not is_admin:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b"f0e1d2c3b4a5968778695a4b3c2d1e0f_error_access_denied")
                    return

                # 参数校验
                query = parse_qs(parsed_url.query)
                t_type = query.get('type', ['2'])[0]
                if t_type not in ["2", "3", "13"]:
                    self.send_error(400, "Invalid parameter")
                    return

                # ================== 16 进制加密传输 ==================
                payload = CACHE_DATA.get(t_type, {})
                json_str = json.dumps(payload, ensure_ascii=False)
                hex_data = json_str.encode('utf-8').hex()

                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(hex_data.encode('utf-8'))
                return

            self.send_response(404)
            self.end_headers()
        except Exception:
            pass

    def log_message(self, format, *args):
        pass

# ================== 赛博朋克级前端 ==================
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
            --bg: #02040a;
            --panel: rgba(6, 12, 24, 0.85);
            --cyan: #00f3ff;
            --red: #ff003c;
            --green: #39ff14;
            --text: #e0f0ff;
            --muted: #5a759e;
            --glitch: #ff00ea;
        }
        
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body { 
            font-family: 'Share Tech Mono', monospace; 
            background: var(--bg); 
            color: var(--text); 
            min-height: 100vh;
            overflow-x: hidden;
            position: relative;
        }

        /* 矩阵网格与扫描线 */
        .cyber-grid {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1;
            background-image: 
                linear-gradient(rgba(0, 243, 255, 0.04) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 243, 255, 0.04) 1px, transparent 1px);
            background-size: 30px 30px;
            perspective: 500px;
        }
        .scanlines {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 100; pointer-events: none;
            background: linear-gradient(to bottom, rgba(255,255,255,0), rgba(255,255,255,0) 50%, rgba(0,0,0,0.3) 50%, rgba(0,0,0,0.3));
            background-size: 100% 4px;
            opacity: 0.6;
        }

        /* 登录遮罩层 */
        #auth-overlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.9); z-index: 9999;
            display: flex; flex-direction: column; justify-content: center; align-items: center;
            backdrop-filter: blur(5px);
        }
        .auth-box {
            border: 1px solid var(--cyan); background: var(--panel); padding: 30px;
            box-shadow: 0 0 20px rgba(0, 243, 255, 0.2), inset 0 0 20px rgba(0, 243, 255, 0.1);
            position: relative; text-align: center;
        }
        .auth-box::before, .auth-box::after {
            content: ''; position: absolute; width: 10px; height: 10px; border: 2px solid var(--cyan);
        }
        .auth-box::before { top: -2px; left: -2px; border-right: none; border-bottom: none; }
        .auth-box::after { bottom: -2px; right: -2px; border-left: none; border-top: none; }
        .auth-title { color: var(--cyan); font-size: 18px; letter-spacing: 2px; margin-bottom: 20px; text-shadow: 0 0 10px rgba(0,243,255,0.5); }
        .auth-input {
            background: transparent; border: 1px solid var(--muted); color: var(--green);
            padding: 10px; font-family: inherit; font-size: 16px; width: 100%; margin-bottom: 20px;
            text-align: center; outline: none; transition: border 0.3s;
        }
        .auth-input:focus { border-color: var(--cyan); box-shadow: 0 0 10px rgba(0,243,255,0.3); }
        .auth-btn {
            background: rgba(0,243,255,0.1); border: 1px solid var(--cyan); color: var(--cyan);
            padding: 10px 20px; font-family: inherit; font-size: 16px; cursor: pointer;
            width: 100%; transition: all 0.3s; font-weight: bold;
        }
        .auth-btn:hover { background: var(--cyan); color: #000; box-shadow: 0 0 15px var(--cyan); }

        /* 主界面 */
        .app { max-width: 800px; margin: 0 auto; padding: 15px; position: relative; z-index: 10; display: none; }
        
        .header { text-align: center; margin-bottom: 25px; padding-top: 10px; }
        .title {
            font-size: 26px; color: var(--cyan); letter-spacing: 4px; font-weight: bold;
            text-shadow: 0 0 10px rgba(0,243,255,0.8), 0 0 20px rgba(0,243,255,0.4);
            position: relative; display: inline-block;
        }
        
        /* 全息面板 */
        .panel {
            background: var(--panel); border: 1px solid rgba(0,243,255,0.3); border-radius: 2px;
            padding: 20px; margin-bottom: 20px; position: relative;
            box-shadow: 0 0 15px rgba(0,243,255,0.05);
        }
        .panel::before {
            content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%;
            background: var(--cyan); box-shadow: 0 0 10px var(--cyan);
        }

        /* 科技选项卡 */
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab-btn {
            flex: 1; background: transparent; border: 1px solid var(--muted); color: var(--muted);
            padding: 12px 0; text-align: center; font-size: 14px; cursor: pointer;
            transition: all 0.3s; font-weight: bold; position: relative; overflow: hidden;
            user-select: none;
        }
        .tab-btn:hover { background: rgba(0,243,255,0.05); color: var(--text); }
        .tab-btn.active {
            border-color: var(--cyan); color: var(--cyan); background: rgba(0,243,255,0.1);
            box-shadow: inset 0 0 15px rgba(0,243,255,0.2);
        }
        .tab-btn.active::after {
            content: ''; position: absolute; bottom: 0; left: 0; width: 100%; height: 2px;
            background: var(--cyan); box-shadow: 0 0 10px var(--cyan);
        }

        /* 最新数据区 */
        .latest-box {
            display: flex; justify-content: space-between; align-items: center;
            background: linear-gradient(90deg, rgba(255,0,60,0.1) 0%, transparent 100%);
            border-left: 3px solid var(--red); padding: 15px;
        }
        .latest-label { font-size: 12px; color: var(--red); letter-spacing: 1px; margin-bottom: 5px;}
        .latest-data { 
            font-size: 24px; font-weight: bold; color: var(--cyan); 
            text-shadow: 0 0 8px rgba(0,243,255,0.5); 
        }
        .latest-data span { color: var(--text); font-size: 18px; margin: 0 5px; }

        /* 倒计时 */
        .countdown-box { text-align: right; }
        .cd-title { font-size: 12px; color: var(--muted); margin-bottom: 5px; }
        .cd-time {
            font-size: 26px; font-weight: bold; color: var(--green);
            text-shadow: 0 0 10px rgba(57,255,20,0.6);
            font-variant-numeric: tabular-nums;
        }
        .cd-time.urgent { color: var(--red); text-shadow: 0 0 15px rgba(255,0,60,0.8); animation: pulse 0.5s infinite alternate; }
        @keyframes pulse { 0% { opacity: 0.8; } 100% { opacity: 1; transform: scale(1.02); } }

        /* 数据表格 */
        .table-container { border: 1px solid rgba(0,243,255,0.2); background: var(--panel); }
        .thead {
            display: flex; background: rgba(0,243,255,0.05); padding: 12px 10px;
            font-size: 13px; color: var(--muted); border-bottom: 1px solid rgba(0,243,255,0.2);
        }
        .trow {
            display: flex; padding: 15px 10px; font-size: 15px; border-bottom: 1px solid rgba(255,255,255,0.03);
            align-items: center; transition: background 0.2s;
        }
        .trow:hover { background: rgba(0,243,255,0.05); }
        .trow.new-row { animation: scanAnim 3s ease-out; }
        @keyframes scanAnim {
            0% { background: rgba(57,255,20,0.4); color: #fff; }
            100% { background: transparent; }
        }
        
        .c1 { flex: 1.2; color: var(--muted); } 
        .c2 { flex: 1; color: var(--muted); font-size: 12px; } 
        .c3 { flex: 2; text-align: center; font-weight: bold; letter-spacing: 1px;} 
        .c4 { flex: 0.8; text-align: center; font-weight: bold; font-size: 18px; } 
        .c5 { flex: 0.8; text-align: center; font-weight: bold;} 
        .c6 { flex: 0.8; text-align: center; font-weight: bold;}
        
        .red { color: var(--red); text-shadow: 0 0 5px rgba(255,0,60,0.4); } 
        .cyan { color: var(--cyan); text-shadow: 0 0 5px rgba(0,243,255,0.4); } 
        .green { color: var(--green); text-shadow: 0 0 5px rgba(57,255,20,0.4); }

    </style>
</head>
<body>
    <div class="cyber-grid"></div>
    <div class="scanlines"></div>

    <!-- 登录面板 -->
    <div id="auth-overlay">
        <div class="auth-box">
            <div class="auth-title">/// 智算中枢安全认证 ///</div>
            <input type="password" id="pwd-input" class="auth-input" placeholder="请输入站长密钥">
            <button class="auth-btn" onclick="checkPwd()">接 入 系 统</button>
        </div>
    </div>

    <!-- 主应用 -->
    <div class="app" id="main-app">
        <div class="header">
            <div class="title">/// 舰长智算中枢 ///</div>
        </div>

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
            <div class="thead">
                <div class="c1">期号</div><div class="c2">时间</div><div class="c3">开奖号码</div>
                <div class="c4">总和</div><div class="c5">大小</div><div class="c6">单双</div>
            </div>
            <div id="list"></div>
        </div>
    </div>

    <script>
        const SECURE_API = "/api/v3/sys/kernel_check";
        const SECRET_TOKEN = "yc28_secure_token_2026";
        let MY_TOKEN = localStorage.getItem('yc28_token');
        
        let currentType = '2'; 
        let prevPeriod = ""; 
        let targetTime = null;
        let timerInterval = null;
        let lastFetchedPeriod = "";

        // 密码校验
        function checkPwd() {
            const pwd = document.getElementById('pwd-input').value;
            if (pwd === "captain888") {
                localStorage.setItem('yc28_token', SECRET_TOKEN);
                MY_TOKEN = SECRET_TOKEN;
                showApp();
            } else {
                alert("密钥错误，拒绝访问！");
            }
        }

        // 显示应用
        function showApp() {
            document.getElementById('auth-overlay').style.display = 'none';
            document.getElementById('main-app').style.display = 'block';
            update();
        }

        // 如果已保存密码，直接进入
        if (MY_TOKEN === SECRET_TOKEN) {
            showApp();
        }

        function switchType(type, btnEl) {
            if (currentType === type) return;
            currentType = type;
            prevPeriod = ""; 
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            btnEl.classList.add('active');
            document.getElementById('top-data').innerHTML = "-- <span>+</span> -- <span>+</span> -- <span>=</span> --";
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
                    cdEl.innerText = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
                    if (diff < 10000) { cdEl.classList.add('urgent'); } else { cdEl.classList.remove('urgent'); }
                }
            }, 100);
        }

        async function update() {
            if (!MY_TOKEN) return;
            try {
                const r = await fetch(`${SECURE_API}?type=${currentType}`, {
                    headers: { 'X-Auth-Token': MY_TOKEN }
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
                    let cTopO = top.odd_even === '单' ? 'red' : 'cyan';
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
                            <div class="c3">
                                <span class="${cB}">${row.num1}</span>+
                                <span class="${cB}">${row.num2}</span>+
                                <span class="${cB}">${row.num3}</span>
                            </div>
                            <div class="c4 green">${row.total}</div>
                            <div class="c5 ${cB}">${row.big_small}</div>
                            <div class="c6 ${cO}">${row.odd_even}</div>
                        </div>`;
                    });
                    document.getElementById('list').innerHTML = html;
                }
            } catch (e) {}
        }
        
        // 站长特权，前端 1 秒拉一次也毫无压力，不会被封 IP
        setInterval(update, 1000); 
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    threading.Thread(target=background_worker, daemon=True).start()
    print(f"🚀 终端启动...")
    
    server = HTTPServer(('0.0.0.0', PORT), RequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
