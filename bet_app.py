import urllib.request
import ssl
import json
import time
import threading
import os
import re
import base64
import sqlite3
from flask import Flask, request, jsonify, render_template_string, session, redirect
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'yc28_captain_platform_secret_2026'

# ================== 游戏配置 ==================
GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210, "close_sec": 30},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60, "close_sec": 5},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60, "close_sec": 5}
}

# 赔率配置
ODDS = {
    'nums': {0: 960, 27: 960, 1: 320, 26: 320, 2: 160, 25: 160, 3: 97, 24: 97, 4: 64.5, 23: 64.5, 5: 46.5, 22: 46.5, 
             6: 35, 21: 35, 7: 27.2, 20: 27.2, 8: 22, 19: 22, 9: 18, 18: 18, 10: 15.8, 17: 15.8, 11: 14.4, 16: 14.4, 
             12: 13.6, 15: 13.6, 13: 13.3, 14: 13.3},
    'bs_oe': 2.8, 'combo1': 6.3, 'combo2': 6.7,
    'triple': 88.0, 'extreme': 16.0, 'straight': 16.0, 'pair': 3.6
}

# 实时数据内存缓存
LIVE_DATA = {
    "2": {"period": "", "next_time": 0, "nums": [], "total": 0},
    "3": {"period": "", "next_time": 0, "nums": [], "total": 0},
    "13": {"period": "", "next_time": 0, "nums": [], "total": 0}
}

# ================== 数据库 ==================
def get_db():
    conn = sqlite3.connect('captain28.db', timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # 用户表 (增加 status 控制拉黑)
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, balance REAL DEFAULT 0.0, role TEXT DEFAULT 'user', status TEXT DEFAULT 'normal'
        )''')
        # 订单表 (增加下注期号、赔率、状态)
        conn.execute('''CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, game_type TEXT, period TEXT,
            bet_type TEXT, bet_value TEXT, amount REAL, odds REAL, status TEXT DEFAULT 'pending',
            win_amount REAL DEFAULT 0.0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # 上下分审批表
        conn.execute('''CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount REAL, 
            status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # 聊天记录表
        conn.execute('''CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, role TEXT, content TEXT, 
            is_image INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # 生成默认站长账号
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username='ADMIN888'")
        if not cursor.fetchone():
            conn.execute("INSERT INTO users (username, password, role) VALUES ('ADMIN888', '123456', 'admin')")
        conn.commit()

init_db()

# ================== 抓取与结算核心引擎 ==================
def settle_bets(game_type, period, nums, total):
    n1, n2, n3 = nums
    is_triple = (n1 == n2 == n3)
    is_pair = (n1 == n2 or n2 == n3 or n1 == n3)
    s_nums = sorted(nums)
    is_straight = (s_nums[1]-s_nums[0]==1 and s_nums[2]-s_nums[1]==1) or (s_nums in [[0,8,9], [0,1,9]])
    big_small = '大' if total >= 14 else '小'
    odd_even = '单' if total % 2 != 0 else '双'
    
    with get_db() as conn:
        pending_bets = conn.execute("SELECT * FROM bets WHERE game_type=? AND period=? AND status='pending'", (game_type, period)).fetchall()
        for bet in pending_bets:
            win = False
            refund = False
            win_amt = 0.0
            
            # 规则：13/14 遇特殊牌型，买大小单双回本金
            if total in [13, 14] and (is_pair or is_straight or is_triple):
                if bet['bet_type'] in ['bs', 'oe']:
                    refund = True
            
            if not refund:
                if bet['bet_type'] == 'num' and str(total) == bet['bet_value']:
                    win, win_amt = True, bet['amount'] * bet['odds']
                elif bet['bet_type'] == 'bs' and big_small == bet['bet_value']:
                    win, win_amt = True, bet['amount'] * bet['odds']
                elif bet['bet_type'] == 'oe' and odd_even == bet['bet_value']:
                    win, win_amt = True, bet['amount'] * bet['odds']
                elif bet['bet_type'] == 'combo':
                    if (big_small+odd_even == bet['bet_value']) or (big_small+odd_even == bet['bet_value']):
                        win, win_amt = True, bet['amount'] * bet['odds']
                elif bet['bet_type'] == 'pattern':
                    if bet['bet_value'] == '豹子' and is_triple: win, win_amt = True, bet['amount'] * bet['odds']
                    if bet['bet_value'] == '极值' and total in [0, 27]: win, win_amt = True, bet['amount'] * bet['odds']
                    if bet['bet_value'] == '顺子' and is_straight and not is_triple: win, win_amt = True, bet['amount'] * bet['odds']
                    if bet['bet_value'] == '对子' and is_pair and not is_triple: win, win_amt = True, bet['amount'] * bet['odds']

            if refund:
                conn.execute("UPDATE bets SET status='refund' WHERE id=?", (bet['id'],))
                conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (bet['amount'], bet['user_id']))
            elif win:
                conn.execute("UPDATE bets SET status='win', win_amount=? WHERE id=?", (win_amt, bet['id']))
                conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (win_amt, bet['user_id']))
            else:
                conn.execute("UPDATE bets SET status='lose' WHERE id=?", (bet['id'],))
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
                        latest = data['data'][0]
                        
                        # 计算下一期服务器基准时间
                        if LIVE_DATA[g_type]['period'] != latest['period']:
                            draw_dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            next_dt = draw_dt + timedelta(seconds=cfg['interval'])
                            if LIVE_DATA[g_type]['period'] != "":
                                # 触发结算 (用上一期期号)
                                settle_bets(g_type, latest['period'], [latest['num1'], latest['num2'], latest['num3']], latest['total'])
                                
                            LIVE_DATA[g_type] = {
                                "period": latest['period'],
                                "next_period": str(int(latest['period']) + 1),
                                "next_time": next_dt.timestamp(), # 记录绝对时间戳
                                "nums": [latest['num1'], latest['num2'], latest['num3']],
                                "total": latest['total']
                            }
            except Exception:
                pass
        time.sleep(2)

threading.Thread(target=fetch_loop, daemon=True).start()

# ================== 路由与 API ==================
@app.route('/api/live/<g_type>')
def api_live(g_type):
    if g_type not in LIVE_DATA: return jsonify({"error": "invalid"})
    return jsonify(LIVE_DATA[g_type])

@app.route('/api/bet', methods=['POST'])
def api_bet():
    if 'user_id' not in session: return jsonify({"success": False, "msg": "未登录"})
    data = request.json
    g_type = data['game_type']
    now = time.time()
    
    # 封盘检测
    if now > (LIVE_DATA[g_type]['next_time'] - GAMES[g_type]['close_sec']):
        return jsonify({"success": False, "msg": f"已封盘，停止下注"})
    
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        if user['status'] == 'banned': return jsonify({"success": False, "msg": "账号已被拉黑"})
        if user['balance'] < float(data['amount']): return jsonify({"success": False, "msg": "余额不足"})
        
        conn.execute("UPDATE users SET balance = balance - ? WHERE id=?", (data['amount'], session['user_id']))
        conn.execute('''INSERT INTO bets (user_id, game_type, period, bet_type, bet_value, amount, odds) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                     (session['user_id'], g_type, LIVE_DATA[g_type]['next_period'], data['bet_type'], data['bet_value'], data['amount'], data['odds']))
        conn.commit()
    return jsonify({"success": True, "msg": "下注成功"})

@app.route('/api/cancel_bet', methods=['POST'])
def api_cancel_bet():
    bet_id = request.json.get('bet_id')
    with get_db() as conn:
        bet = conn.execute("SELECT * FROM bets WHERE id=?", (bet_id,)).fetchone()
        if not bet or bet['status'] != 'pending': return jsonify({"success": False, "msg": "该注单无法取消"})
        
        # 封盘检测
        if time.time() > (LIVE_DATA[bet['game_type']]['next_time'] - GAMES[bet['game_type']]['close_sec']):
            return jsonify({"success": False, "msg": "已封盘，禁止取消"})
            
        conn.execute("UPDATE bets SET status='cancel' WHERE id=?", (bet_id,))
        conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (bet['amount'], bet['user_id']))
        conn.commit()
    return jsonify({"success": True, "msg": "取消成功，金额已退回"})

@app.route('/api/chat', methods=['GET', 'POST'])
def api_chat():
    if 'user_id' not in session: return jsonify({"success": False})
    
    # 客户发信息
    if request.method == 'POST':
        data = request.json
        with get_db() as conn:
            conn.execute("INSERT INTO messages (user_id, role, content, is_image) VALUES (?, 'user', ?, ?)", 
                         (session['user_id'], data['content'], 1 if data.get('is_image') else 0))
            conn.commit()
        return jsonify({"success": True})
    
    # 拉取聊天记录
    with get_db() as conn:
        msgs = conn.execute("SELECT * FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 20", (session['user_id'],)).fetchall()
    return jsonify([dict(m) for m in msgs])

@app.route('/api/req_money', methods=['POST'])
def api_req_money():
    data = request.json
    with get_db() as conn:
        conn.execute("INSERT INTO transactions (user_id, type, amount) VALUES (?, ?, ?)", 
                     (session['user_id'], data['type'], data['amount']))
        conn.commit()
    return jsonify({"success": True, "msg": "申请已提交，等待客服审核"})

# ================== 页面路由 ==================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('username'), request.form.get('password')
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p)).fetchone()
            if user:
                if user['status'] == 'banned': return "<script>alert('该账号已被拉黑封禁！');history.back();</script>"
                session['user_id'] = user['id']
                session['role'] = user['role']
                session['username'] = user['username']
                return redirect('/')
        return "<script>alert('账号或密码错误');history.back();</script>"
    return render_template_string(HTML_LOGIN)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u, p1, p2 = request.form.get('username'), request.form.get('pwd1'), request.form.get('pwd2')
        if not re.match(r'^[A-Z0-9]+$', u):
            return "<script>alert('用户名必须为大写+数字！');history.back();</script>"
        if p1 != p2:
            return "<script>alert('两次密码不一致！');history.back();</script>"
        try:
            with get_db() as conn:
                conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (u, p1))
                conn.commit()
            return "<script>alert('注册成功');location.href='/login';</script>"
        except sqlite3.IntegrityError:
            return "<script>alert('用户名已存在');history.back();</script>"
    return render_template_string(HTML_REGISTER)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
def index():
    if 'user_id' not in session: return redirect('/login')
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        bets = conn.execute("SELECT * FROM bets WHERE user_id=? ORDER BY id DESC LIMIT 30", (session['user_id'],)).fetchall()
        stats = conn.execute("SELECT SUM(amount) as outlay, SUM(win_amount) as income FROM bets WHERE user_id=?", (session['user_id'],)).fetchone()
    return render_template_string(HTML_USER, user=user, bets=bets, stats=stats, session=session)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('role') != 'admin': return "拒绝访问"
    with get_db() as conn:
        if request.method == 'POST':
            act = request.form.get('act')
            if act == 'manual_money':
                uid, amt, m_type = request.form.get('uid'), float(request.form.get('amount')), request.form.get('m_type')
                if m_type == 'add': conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amt, uid))
                else: conn.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amt, uid))
            elif act == 'ban':
                uid = request.form.get('uid')
                conn.execute("UPDATE users SET status='banned' WHERE id=?", (uid,))
            elif act == 'unban':
                uid = request.form.get('uid')
                conn.execute("UPDATE users SET status='normal' WHERE id=?", (uid,))
            elif act == 'approve_tx':
                tx_id = request.form.get('tx_id')
                tx = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
                if tx and tx['status'] == 'pending':
                    if tx['type'] == 'deposit': conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (tx['amount'], tx['user_id']))
                    conn.execute("UPDATE transactions SET status='approved' WHERE id=?", (tx_id,))
            elif act == 'chat_reply':
                uid, msg = request.form.get('uid'), request.form.get('msg')
                conn.execute("INSERT INTO messages (user_id, role, content) VALUES (?, 'admin', ?)", (uid, msg))
            conn.commit()

        users = conn.execute("SELECT * FROM users").fetchall()
        txs = conn.execute("SELECT t.*, u.username FROM transactions t JOIN users u ON t.user_id=u.id WHERE t.status='pending'").fetchall()
        chats = conn.execute("SELECT m.*, u.username FROM messages m JOIN users u ON m.user_id=u.id ORDER BY m.id DESC LIMIT 20").fetchall()
    return render_template_string(HTML_ADMIN, users=users, txs=txs, chats=chats, session=session)

# ================== HTML / CSS / JS 前端模板 ==================
BASE_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
    :root { --bg: #02040a; --panel: #0a101f; --cyan: #00f3ff; --red: #ff003c; --green: #39ff14; --text: #d0def0; }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Share Tech Mono', monospace; }
    body { background: var(--bg); color: var(--text); min-height: 100vh; padding: 10px; background-image: linear-gradient(rgba(0,243,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,243,255,0.03) 1px, transparent 1px); background-size: 20px 20px; }
    .panel { background: var(--panel); border: 1px solid rgba(0,243,255,0.4); border-radius: 4px; padding: 15px; margin-bottom: 15px; box-shadow: 0 0 10px rgba(0,243,255,0.1); }
    .title { font-size: 18px; color: var(--cyan); text-shadow: 0 0 8px var(--cyan); margin-bottom: 10px; text-align: center;}
    input, button, select { width: 100%; padding: 10px; margin-bottom: 10px; background: #000; border: 1px solid var(--cyan); color: var(--green); font-size: 16px; outline: none; border-radius: 3px; }
    button { background: rgba(0,243,255,0.1); cursor: pointer; font-weight: bold; transition: 0.2s; color: var(--cyan); }
    button:hover { background: var(--cyan); color: #000; }
    .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
    .btn-bet { padding: 6px; font-size: 12px; margin: 0; text-align: center; }
    .table { width: 100%; border-collapse: collapse; font-size: 12px; text-align: center; }
    .table th, .table td { border: 1px solid rgba(0,243,255,0.2); padding: 6px; }
    .table th { background: rgba(0,243,255,0.1); color: var(--cyan); }
    .red { color: var(--red); text-shadow: 0 0 5px var(--red); } 
    .green { color: var(--green); }
    .top-bar { display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 15px; border-bottom: 1px solid var(--cyan); padding-bottom: 10px; }
</style>
"""

HTML_LOGIN = BASE_CSS + """
<div class="panel" style="max-width: 400px; margin: 50px auto;">
    <div class="title">/// 舰长2.8平台 · 登录 ///</div>
    <form method="POST">
        <input type="text" name="username" placeholder="账号" required>
        <input type="password" name="password" placeholder="密码" required>
        <button type="submit">接 入 系 统</button>
    </form>
    <a href="/register" style="color:var(--cyan); font-size:12px; display:block; text-align:center; margin-top:10px;">前往注册</a>
</div>
"""

HTML_REGISTER = BASE_CSS + """
<div class="panel" style="max-width: 400px; margin: 50px auto;">
    <div class="title">/// 舰长2.8平台 · 注册 ///</div>
    <form method="POST" onsubmit="return validate()">
        <input type="text" id="u" name="username" placeholder="大写字母+数字 (如: VIP888)" required>
        <input type="password" id="p1" name="pwd1" placeholder="设置密码" required>
        <input type="password" id="p2" name="pwd2" placeholder="再次确认密码" required>
        <div style="display:flex; align-items:center; margin-bottom:10px;">
            <canvas id="captcha" width="100" height="36" style="background:#111; border:1px solid var(--cyan);"></canvas>
            <input type="text" id="c_input" placeholder="验证码" style="margin:0 0 0 10px;" required>
        </div>
        <button type="submit">注 册 账 号</button>
    </form>
</div>
<script>
    let code = "";
    function drawCaptcha() {
        let canvas = document.getElementById('captcha'), ctx = canvas.getContext('2d');
        ctx.clearRect(0,0,100,36); code = "";
        let chars = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789";
        for(let i=0; i<4; i++) {
            let char = chars[Math.floor(Math.random() * chars.length)]; code += char;
            ctx.font = "24px monospace"; ctx.fillStyle = Math.random()>0.5 ? "#00f3ff" : "#39ff14";
            ctx.save(); ctx.translate(15 + i*20, 26); ctx.rotate((Math.random()-0.5)*0.5); ctx.fillText(char, 0, 0); ctx.restore();
        }
    }
    drawCaptcha();
    document.getElementById('captcha').onclick = drawCaptcha;
    function validate() {
        let u = document.getElementById('u').value;
        if(!/^[A-Z0-9]+$/.test(u)) { alert("用户名必须由大写字母和数字组成！"); return false; }
        if(document.getElementById('p1').value !== document.getElementById('p2').value) { alert("两次密码不一致！"); return false; }
        if(document.getElementById('c_input').value.toUpperCase() !== code) { alert("验证码错误！"); drawCaptcha(); return false; }
        return true;
    }
</script>
"""

HTML_USER = BASE_CSS + """
<div class="top-bar">
    <div>账户: <span class="green">{{ session.username }}</span></div>
    <div>余额: <span class="green" id="user-bal">{{ user.balance }}</span></div>
    <div><a href="/logout" style="color:var(--red); text-decoration:none;">退出</a></div>
</div>

<div class="panel">
    <div class="title">/// 舰长2.8平台 · 智算终端 ///</div>
    
    <!-- 实时数据 -->
    <div class="grid-3" style="margin-bottom:15px;">
        <button onclick="switchGame('2')">加拿大28</button>
        <button onclick="switchGame('3')">分分28</button>
        <button onclick="switchGame('13')">比特28</button>
    </div>
    <div style="text-align:center; margin-bottom:15px;">
        <div>最新期号: <span id="cur-period" class="green">加载中</span></div>
        <div style="font-size:24px; font-weight:bold; color:var(--cyan); margin:5px 0;">
            <span id="cur-nums">-- + -- + --</span> = <span id="cur-total" class="red">--</span>
        </div>
        <div>距封盘: <span id="cd-close" class="red">--</span> | 距开奖: <span id="cd-draw" class="green">--</span></div>
    </div>

    <div style="background:rgba(0,0,0,0.5); padding:10px; border-radius:4px;">
        <div class="grid-4" style="margin-bottom:10px;">
            <button onclick="setAmt(10)">10</button><button onclick="setAmt(50)">50</button>
            <button onclick="setAmt(100)">100</button><button onclick="setAmt(500)">500</button>
        </div>
        <input type="number" id="bet-amount" placeholder="下注金额" style="font-size:20px; text-align:center;">
        <div id="bet-msg" style="color:var(--red); text-align:center; height:20px; font-size:14px;"></div>
        
        <div style="color:var(--cyan); font-size:12px; margin:10px 0 5px;">数字组合 (买入下期和值)</div>
        <div class="grid-4" id="bet-nums"></div>

        <div style="color:var(--cyan); font-size:12px; margin:10px 0 5px;">大小单双 / 连码</div>
        <div class="grid-3" id="bet-combos"></div>

        <div style="color:var(--cyan); font-size:12px; margin:10px 0 5px;">特殊牌型</div>
        <div class="grid-4" id="bet-patterns"></div>
    </div>
</div>

<div class="panel">
    <div class="title">📊 账务流水 (盈亏: <span class="{{ 'green' if (stats.income or 0) >= (stats.outlay or 0) else 'red' }}">{{ (stats.income or 0) - (stats.outlay or 0) }}</span>)</div>
    <table class="table">
        <tr><th>期号/时间</th><th>玩法</th><th>金额</th><th>盈亏</th><th>操作</th></tr>
        {% for b in bets %}
        <tr>
            <td>{{ b.period[-4:] }}</td>
            <td>{{ b.bet_value }}</td>
            <td>{{ b.amount }}</td>
            <td class="{{ 'green' if b.status=='win' else 'red' if b.status=='lose' else '' }}">
                {{ b.win_amount if b.status=='win' else ('已退' if b.status=='cancel' or b.status=='refund' else '-') }}
            </td>
            <td>
                {% if b.status == 'pending' %}
                <button onclick="cancelBet({{ b.id }})" style="padding:4px; font-size:12px; margin:0; border-color:var(--red); color:var(--red);">取消</button>
                {% else %} -- {% endif %}
            </td>
        </tr>
        {% endfor %}
    </table>
</div>

<!-- 客服悬浮窗 -->
<div id="chat-box" style="position:fixed; bottom:20px; right:20px; width:300px; display:none; z-index:999; background:var(--panel); border:1px solid var(--cyan); border-radius:8px;">
    <div style="background:rgba(0,243,255,0.2); padding:10px; display:flex; justify-content:space-between; cursor:pointer;" onclick="toggleChat()">
        <span>💬 联系客服</span><span>❌</span>
    </div>
    <div id="chat-history" style="height:250px; overflow-y:auto; padding:10px; font-size:12px; display:flex; flex-direction:column; gap:8px;"></div>
    <div style="padding:10px; border-top:1px solid rgba(0,243,255,0.2);">
        <input type="text" id="chat-input" placeholder="输入消息..." style="margin-bottom:5px; padding:5px;">
        <div style="display:flex; gap:5px;">
            <label style="flex:1; background:rgba(0,243,255,0.1); border:1px solid var(--cyan); color:var(--cyan); text-align:center; padding:8px; border-radius:3px; cursor:pointer; font-size:12px;">
                传图片<input type="file" id="chat-img" accept="image/*" style="display:none;" onchange="sendChatImg()">
            </label>
            <button onclick="sendChatText()" style="flex:1; padding:8px; margin:0; font-size:12px;">发送</button>
        </div>
    </div>
</div>
<button onclick="toggleChat()" style="position:fixed; bottom:20px; right:20px; width:60px; height:60px; border-radius:50%; padding:0; font-size:24px; box-shadow:0 0 15px var(--cyan); z-index:998;">💬</button>

<script>
    const ODDS = {{ odds_dict | safe }};
    let cGame = '2';
    let cData = null;
    
    // 生成下注键盘
    const numGrid = document.getElementById('bet-nums');
    for(let i=0; i<=27; i++) { let b = document.createElement('button'); b.className='btn-bet'; b.innerHTML = `${i}<br>${ODDS.nums[i]}x`; b.onclick=()=>bet('num', i, ODDS.nums[i]); numGrid.appendChild(b); }
    const comboGrid = document.getElementById('bet-combos');
    [['大',2.8],['小',2.8],['单',2.8],['双',2.8],['大单',6.3],['小双',6.3],['大双',6.7],['小单',6.7]].forEach(c=>{
        let b = document.createElement('button'); b.className='btn-bet'; b.innerHTML = `${c[0]}<br>${c[1]}x`; 
        b.onclick=()=>bet((c[0].length===1)?(c[0]==='大'||c[0]==='小'?'bs':'oe'):'combo', c[0], c[1]); comboGrid.appendChild(b);
    });
    const patGrid = document.getElementById('bet-patterns');
    [['豹子',88],['极值',16],['顺子',16],['对子',3.6]].forEach(p=>{
        let b = document.createElement('button'); b.className='btn-bet'; b.innerHTML = `${p[0]}<br>${p[1]}x`; b.onclick=()=>bet('pattern', p[0], p[1]); patGrid.appendChild(b);
    });

    function setAmt(v) { document.getElementById('bet-amount').value = v; }
    function switchGame(g) { cGame = g; fetchLive(); }
    
    function fetchLive() {
        fetch('/api/live/' + cGame).then(r=>r.json()).then(d=>{
            cData = d;
            document.getElementById('cur-period').innerText = d.period;
            document.getElementById('cur-nums').innerText = d.nums.join(' + ');
            document.getElementById('cur-total').innerText = d.total;
        });
    }
    setInterval(fetchLive, 1500);
    fetchLive();
    
    // 倒计时器
    setInterval(() => {
        if(!cData || !cData.next_time) return;
        let now = Date.now() / 1000;
        let leftDraw = Math.max(0, Math.floor(cData.next_time - now));
        // 封盘时间
        let closeLimit = cGame === '2' ? 30 : 5;
        let leftClose = leftDraw - closeLimit;
        
        let cdCloseEl = document.getElementById('cd-close');
        let cdDrawEl = document.getElementById('cd-draw');
        cdDrawEl.innerText = leftDraw + " 秒";
        
        if(leftClose > 0) {
            cdCloseEl.innerText = leftClose + " 秒";
            cdCloseEl.className = 'green';
        } else {
            cdCloseEl.innerText = "已封盘";
            cdCloseEl.className = 'red';
        }
    }, 1000);

    function bet(type, val, odds) {
        let amt = document.getElementById('bet-amount').value;
        if(!amt || amt <= 0) return alert("请输入正确金额");
        fetch('/api/bet', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({game_type: cGame, bet_type: type, bet_value: val, amount: amt, odds: odds})
        }).then(r=>r.json()).then(d=>{
            document.getElementById('bet-msg').innerText = d.msg;
            if(d.success) setTimeout(()=>location.reload(), 1000);
        });
    }

    function cancelBet(id) {
        fetch('/api/cancel_bet', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({bet_id: id})
        }).then(r=>r.json()).then(d=>{
            alert(d.msg);
            if(d.success) location.reload();
        });
    }

    // 客服系统
    function toggleChat() {
        let box = document.getElementById('chat-box');
        let btn = document.querySelector('button[onclick="toggleChat()"]');
        if(box.style.display === 'none' || box.style.display === '') {
            box.style.display = 'block'; btn.style.display = 'none'; loadChat();
        } else { box.style.display = 'none'; btn.style.display = 'block'; }
    }
    function loadChat() {
        fetch('/api/chat').then(r=>r.json()).then(msgs=>{
            let h = document.getElementById('chat-history'); h.innerHTML = '';
            msgs.reverse().forEach(m=>{
                let d = document.createElement('div');
                d.style.padding = '6px'; d.style.borderRadius = '4px'; d.style.maxWidth = '80%';
                if(m.role === 'admin') { d.style.background = 'rgba(57,255,20,0.2)'; d.style.alignSelf = 'flex-start'; }
                else { d.style.background = 'rgba(0,243,255,0.2)'; d.style.alignSelf = 'flex-end'; }
                if(m.is_image) { d.innerHTML = `<img src="${m.content}" style="max-width:100%; border-radius:4px;">`; }
                else { d.innerText = m.content; }
                h.appendChild(d);
            });
            h.scrollTop = h.scrollHeight;
        });
    }
    function sendChatText() {
        let val = document.getElementById('chat-input').value;
        if(!val) return;
        fetch('/api/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content: val}) })
        .then(()=>{ document.getElementById('chat-input').value=''; loadChat(); });
    }
    function sendChatImg() {
        let file = document.getElementById('chat-img').files[0];
        if(!file) return;
        let reader = new FileReader();
        reader.onload = function(e) {
            fetch('/api/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content: e.target.result, is_image: true}) })
            .then(()=>{ loadChat(); });
        };
        reader.readAsDataURL(file);
    }
</script>
"""

HTML_ADMIN = BASE_CSS + """
<div class="top-bar">
    <div>超级管理后台</div>
    <div><a href="/" style="color:var(--cyan); text-decoration:none;">回前台</a> | <a href="/logout" style="color:var(--red); text-decoration:none;">退出</a></div>
</div>

<div class="panel">
    <div class="title">手动上下分 / 拉黑管理</div>
    <form method="POST" class="grid-4">
        <input type="hidden" name="act" value="manual_money">
        <input type="number" name="uid" placeholder="用户ID" required>
        <input type="number" step="0.01" name="amount" placeholder="金额(负数为扣款)" required>
        <button type="submit" name="m_type" value="add" class="green">上分/充值</button>
        <button type="submit" name="m_type" value="sub" class="red">下分/提现</button>
    </form>
</div>

<div class="panel">
    <div class="title">待审批上下分申请</div>
    <table class="table">
        <tr><th>用户</th><th>类型</th><th>金额</th><th>操作</th></tr>
        {% for t in txs %}
        <tr>
            <td>{{ t.username }} (ID:{{ t.user_id }})</td>
            <td>{{ '充值' if t.type=='deposit' else '提现' }}</td>
            <td>{{ t.amount }}</td>
            <td>
                <form method="POST" style="display:flex; gap:5px;">
                    <input type="hidden" name="act" value="approve_tx">
                    <input type="hidden" name="tx_id" value="{{ t.id }}">
                    <button type="submit" style="padding:4px; font-size:12px; margin:0; border-color:var(--green); color:var(--green);">同意</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
</div>

<div class="panel">
    <div class="title">用户列表及拉黑控制</div>
    <table class="table">
        <tr><th>ID</th><th>账户</th><th>余额</th><th>状态</th><th>操作</th></tr>
        {% for u in users %}
        <tr>
            <td>{{ u.id }}</td>
            <td>{{ u.username }}</td>
            <td class="green">{{ u.balance }}</td>
            <td class="{{ 'red' if u.status=='banned' else '' }}">{{ u.status }}</td>
            <td>
                <form method="POST">
                    <input type="hidden" name="uid" value="{{ u.id }}">
                    {% if u.status == 'banned' %}
                    <button type="submit" name="act" value="unban" style="padding:4px; font-size:12px; margin:0; border-color:var(--green); color:var(--green);">恢复</button>
                    {% else %}
                    <button type="submit" name="act" value="ban" style="padding:4px; font-size:12px; margin:0; border-color:var(--red); color:var(--red);">拉黑</button>
                    {% endif %}
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
</div>

<div class="panel">
    <div class="title">客服消息回复 (按客户ID)</div>
    <div style="max-height: 300px; overflow-y: auto; margin-bottom: 10px; font-size:12px;">
        {% for c in chats %}
        <div style="border-bottom:1px solid #333; padding:5px;">
            <span style="color:var(--cyan);">[{{ c.username }}]</span>
            {% if c.is_image %}<br><img src="{{ c.content }}" style="max-height:80px;">{% else %}{{ c.content }}{% endif %}
        </div>
        {% endfor %}
    </div>
    <form method="POST" class="grid-3">
        <input type="hidden" name="act" value="chat_reply">
        <input type="number" name="uid" placeholder="接收者用户ID" required>
        <input type="text" name="msg" placeholder="回复文字" required style="grid-column: span 2;">
        <button type="submit" style="grid-column: span 3;">发送消息</button>
    </form>
</div>
"""

@app.context_processor
def inject_odds():
    return dict(odds_dict=json.dumps(ODDS))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8888))
    app.run(host='0.0.0.0', port=port)
