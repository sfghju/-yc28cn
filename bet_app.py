import urllib.request
import ssl
import json
import time
import threading
import os
import re
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

ODDS = {
    'nums': {0: 960, 27: 960, 1: 320, 26: 320, 2: 160, 25: 160, 3: 97, 24: 97, 4: 64.5, 23: 64.5, 5: 46.5, 22: 46.5, 
             6: 35, 21: 35, 7: 27.2, 20: 27.2, 8: 22, 19: 22, 9: 18, 18: 18, 10: 15.8, 17: 15.8, 11: 14.4, 16: 14.4, 
             12: 13.6, 15: 13.6, 13: 13.3, 14: 13.3},
    'bs_oe': 2.8, 'combo1': 6.3, 'combo2': 6.7,
    'triple': 88.0, 'extreme': 16.0, 'straight': 16.0, 'pair': 3.6
}

LIVE_DATA = {
    "2": {"period": "", "next_period": "", "next_time": 0, "nums": [], "total": 0, "status": "loading"},
    "3": {"period": "", "next_period": "", "next_time": 0, "nums": [], "total": 0, "status": "loading"},
    "13": {"period": "", "next_period": "", "next_time": 0, "nums": [], "total": 0, "status": "loading"}
}

REPORTED_PERIODS = {"2": "", "3": "", "13": ""}

# ================== 数据库 ==================
def get_db():
    conn = sqlite3.connect('captain28.db', timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, nickname TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, balance REAL DEFAULT 0.0, role TEXT DEFAULT 'user', status TEXT DEFAULT 'normal'
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, game_type TEXT, period TEXT,
            bet_type TEXT, bet_value TEXT, amount REAL, odds REAL, status TEXT DEFAULT 'pending',
            win_amount REAL DEFAULT 0.0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # 消息表 (game_type='CS' 代表客服私聊)
        conn.execute('''CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, game_type TEXT, user_id INTEGER, role TEXT, 
            content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username='ADMIN888'")
        if not cursor.fetchone():
            conn.execute("INSERT INTO users (username, nickname, password, role) VALUES ('ADMIN888', '站长', '123456', 'admin')")
        conn.commit()

init_db()

# ================== 机器人自动播报账单 ==================
def broadcast_bill(game_type, period):
    with get_db() as conn:
        bets = conn.execute('''
            SELECT u.nickname, b.bet_value, b.amount 
            FROM bets b JOIN users u ON b.user_id = u.id 
            WHERE b.game_type=? AND b.period=? AND b.status='pending'
        ''', (game_type, period)).fetchall()
        
        if not bets: return
        
        user_bets = {}
        for b in bets:
            name = b['nickname']
            if name not in user_bets:
                user_bets[name] = {'items': [], 'total': 0}
            user_bets[name]['items'].append(f"{b['bet_value']}:{b['amount']}")
            user_bets[name]['total'] += b['amount']
        
        bill_lines = [f"第 {period} 期玩家投注账单"]
        for u, data in user_bets.items():
            items_str = " ".join(data['items'])
            bill_lines.append(f"{u}-[{items_str}]_{data['total']}")
            
        bill_text = "\n".join(bill_lines)
        
        conn.execute("INSERT INTO messages (game_type, user_id, role, content) VALUES (?, 0, 'robot', ?)", (game_type, bill_text))
        conn.commit()

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
            win, refund, win_amt = False, False, 0.0
            
            if total in [13, 14] and (is_pair or is_straight or is_triple):
                if bet['bet_type'] in ['bs', 'oe']: refund = True
            
            if not refund:
                if bet['bet_type'] == 'num' and str(total) == bet['bet_value']: win, win_amt = True, bet['amount'] * bet['odds']
                elif bet['bet_type'] == 'bs' and big_small == bet['bet_value']: win, win_amt = True, bet['amount'] * bet['odds']
                elif bet['bet_type'] == 'oe' and odd_even == bet['bet_value']: win, win_amt = True, bet['amount'] * bet['odds']
                elif bet['bet_type'] == 'combo' and (big_small+odd_even) == bet['bet_value']: win, win_amt = True, bet['amount'] * bet['odds']
                elif bet['bet_type'] == 'pattern':
                    if bet['bet_value'] == '豹子' and is_triple: win, win_amt = True, bet['amount'] * bet['odds']
                    if bet['bet_value'] == '极大' and total in [0, 27]: win, win_amt = True, bet['amount'] * bet['odds']
                    if bet['bet_value'] == '极小' and total in [0, 27]: win, win_amt = True, bet['amount'] * bet['odds']
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
        now = time.time()
        for g_type, cfg in GAMES.items():
            try:
                req = urllib.request.Request(cfg['url'], headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    if data.get('data'):
                        latest = data['data'][0]
                        
                        if LIVE_DATA[g_type]['period'] != latest['period']:
                            draw_dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            next_dt = draw_dt + timedelta(seconds=cfg['interval'])
                            
                            if LIVE_DATA[g_type]['period'] != "":
                                settle_bets(g_type, latest['period'], [latest['num1'], latest['num2'], latest['num3']], latest['total'])
                                
                            LIVE_DATA[g_type] = {
                                "period": latest['period'],
                                "next_period": str(int(latest['period']) + 1),
                                "next_time": next_dt.timestamp(),
                                "nums": [latest['num1'], latest['num2'], latest['num3']],
                                "total": latest['total']
                            }
                        
                        close_time = LIVE_DATA[g_type]['next_time'] - cfg['close_sec']
                        if now >= close_time:
                            LIVE_DATA[g_type]['status'] = "封盘中"
                            if REPORTED_PERIODS[g_type] != LIVE_DATA[g_type]['next_period']:
                                REPORTED_PERIODS[g_type] = LIVE_DATA[g_type]['next_period']
                                threading.Thread(target=broadcast_bill, args=(g_type, LIVE_DATA[g_type]['next_period'])).start()
                        else:
                            LIVE_DATA[g_type]['status'] = "下注中"
                            
            except Exception:
                pass
        time.sleep(2)

threading.Thread(target=fetch_loop, daemon=True).start()

# ================== API 路由 ==================
@app.route('/api/live/<g_type>')
def api_live(g_type):
    if g_type not in LIVE_DATA: return jsonify({"error": "invalid"})
    return jsonify(LIVE_DATA[g_type])

@app.route('/api/bet', methods=['POST'])
def api_bet():
    if 'user_id' not in session: return jsonify({"success": False, "msg": "未登录"})
    data = request.json
    g_type = data['game_type']
    
    if time.time() > (LIVE_DATA[g_type]['next_time'] - GAMES[g_type]['close_sec']):
        return jsonify({"success": False, "msg": "已封盘，停止下注"})
    
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        if user['status'] == 'banned': return jsonify({"success": False, "msg": "账号已被拉黑"})
        if user['balance'] < float(data['amount']): return jsonify({"success": False, "msg": "余额不足"})
        
        conn.execute("UPDATE users SET balance = balance - ? WHERE id=?", (data['amount'], session['user_id']))
        conn.execute('''INSERT INTO bets (user_id, game_type, period, bet_type, bet_value, amount, odds) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                     (session['user_id'], g_type, LIVE_DATA[g_type]['next_period'], data['bet_type'], data['bet_value'], data['amount'], data['odds']))
        
        conn.execute("INSERT INTO messages (game_type, user_id, role, content) VALUES (?, ?, 'user', ?)", 
                     (g_type, session['user_id'], f"[{user['nickname']}] {data['bet_value']}:{data['amount']}"))
        conn.commit()
    return jsonify({"success": True, "msg": "下注成功"})

@app.route('/api/chat/<g_type>', methods=['GET'])
def api_chat(g_type):
    if 'user_id' not in session: return jsonify([])
    with get_db() as conn:
        msgs = conn.execute('''SELECT m.*, u.nickname FROM messages m LEFT JOIN users u ON m.user_id = u.id 
                               WHERE m.game_type=? ORDER BY m.id DESC LIMIT 30''', (g_type,)).fetchall()
    return jsonify([dict(m) for m in msgs])

@app.route('/api/cs', methods=['GET', 'POST'])
def api_cs():
    if 'user_id' not in session: return jsonify({"success": False})
    uid = session['user_id']
    
    if request.method == 'POST':
        content = request.json.get('content')
        with get_db() as conn:
            conn.execute("INSERT INTO messages (game_type, user_id, role, content) VALUES ('CS', ?, 'user', ?)", (uid, content))
            conn.commit()
        return jsonify({"success": True})
    
    with get_db() as conn:
        msgs = conn.execute("SELECT * FROM messages WHERE game_type='CS' AND user_id=? ORDER BY id DESC LIMIT 20", (uid,)).fetchall()
    return jsonify([dict(m) for m in msgs])

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
                session['nickname'] = user['nickname']
                # 如果是管理员，登录后直接跳后台
                return redirect('/admin' if user['role'] == 'admin' else '/')
        return "<script>alert('账号或密码错误');history.back();</script>"
    return render_template_string(HTML_LOGIN)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u, nickname, p1, p2 = request.form.get('username'), request.form.get('nickname'), request.form.get('pwd1'), request.form.get('pwd2')
        
        if not re.match(r'^[A-Z0-9]+$', u):
            return "<script>alert('登录账号必须为大写+数字！');history.back();</script>"
        if not re.match(r'^[\u4e00-\u9fa5]{2,5}$', nickname):
            return "<script>alert('游戏昵称必须为 2~5 个纯中文汉字！');history.back();</script>"
        if p1 != p2:
            return "<script>alert('两次密码不一致！');history.back();</script>"
        if p1 == u:
            return "<script>alert('密码不能与账号相同！');history.back();</script>"
            
        try:
            with get_db() as conn:
                exist_nick = conn.execute("SELECT id FROM users WHERE nickname=?", (nickname,)).fetchone()
                if exist_nick: return "<script>alert('该中文名已被其他玩家使用！');history.back();</script>"
                conn.execute("INSERT INTO users (username, nickname, password) VALUES (?, ?, ?)", (u, nickname, p1))
                conn.commit()
            return "<script>alert('注册成功，请登录');location.href='/login';</script>"
        except sqlite3.IntegrityError:
            return "<script>alert('登录账号已存在');history.back();</script>"
    return render_template_string(HTML_REGISTER)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
def index():
    if 'user_id' not in session: return redirect('/login')
    if session.get('role') == 'admin': return redirect('/admin')
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    return render_template_string(HTML_HOME, user=user, session=session)

@app.route('/game/<g_type>')
def game_page(g_type):
    if 'user_id' not in session or g_type not in GAMES: return redirect('/login')
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    return render_template_string(HTML_GAME, g_type=g_type, game_name=GAMES[g_type]['name'], user=user, session=session)

# 后台管理路由 (独立网址)
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
            elif act == 'reply_cs':
                uid, msg = request.form.get('uid'), request.form.get('msg')
                conn.execute("INSERT INTO messages (game_type, user_id, role, content) VALUES ('CS', ?, 'admin', ?)", (uid, msg))
            conn.commit()

        users = conn.execute("SELECT * FROM users").fetchall()
        cs_msgs = conn.execute('''SELECT m.*, u.nickname FROM messages m JOIN users u ON m.user_id = u.id 
                                  WHERE m.game_type='CS' ORDER BY m.id DESC LIMIT 50''').fetchall()
    return render_template_string(HTML_ADMIN, users=users, cs_msgs=cs_msgs, session=session)

# ================== 前端模板 ==================
BASE_CSS = """
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    body { background: #f0f2f5; color: #333; min-height: 100vh; }
    .header { background: #00a2ff; color: #fff; padding: 15px; display: flex; justify-content: space-between; align-items: center; font-size: 16px; font-weight: bold; }
    .container { padding: 10px; max-width: 500px; margin: 0 auto; }
    .card { background: #fff; border-radius: 8px; padding: 15px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .input-group { margin-bottom: 15px; }
    .input-group input { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 16px; outline: none; }
    .btn { width: 100%; padding: 12px; background: #00a2ff; color: #fff; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; font-weight: bold; }
    .btn:active { opacity: 0.8; }
    .text-center { text-align: center; }
    .text-red { color: #ff3b30; }
    .text-green { color: #34c759; }
    .text-blue { color: #00a2ff; }
    .text-gray { color: #888; }
</style>
"""

HTML_LOGIN = BASE_CSS + """
<div class="header" style="justify-content: center;">舰长2.8平台</div>
<div class="container" style="margin-top: 50px;">
    <div class="card">
        <h3 class="text-center" style="margin-bottom: 20px;">登录</h3>
        <form method="POST">
            <div class="input-group"><input type="text" name="username" placeholder="请输入账号" required></div>
            <div class="input-group"><input type="password" name="password" placeholder="请输入密码" required></div>
            <button type="submit" class="btn">登录</button>
        </form>
        <div class="text-center" style="margin-top: 15px; font-size: 14px;">
            <a href="/register" class="text-blue" style="text-decoration: none;">没有账号？点击注册</a>
        </div>
    </div>
</div>
"""

HTML_REGISTER = BASE_CSS + """
<div class="header" style="justify-content: center;">舰长2.8平台</div>
<div class="container" style="margin-top: 30px;">
    <div class="card">
        <h3 class="text-center" style="margin-bottom: 20px;">注册</h3>
        <form method="POST">
            <div class="input-group"><input type="text" name="username" placeholder="登录账号 (大写字母+数字)" required></div>
            <div class="input-group"><input type="text" name="nickname" placeholder="游戏昵称 (2~5个纯中文名)" required></div>
            <div class="input-group"><input type="password" name="pwd1" placeholder="设置密码" required></div>
            <div class="input-group"><input type="password" name="pwd2" placeholder="再次确认密码" required></div>
            <button type="submit" class="btn">立即注册</button>
        </form>
        <div class="text-center" style="margin-top: 15px; font-size: 14px;">
            <a href="/login" class="text-blue" style="text-decoration: none;">已有账号？去登录</a>
        </div>
    </div>
</div>
"""

HTML_HOME = BASE_CSS + """
<div class="header">
    <span>舰长2.8平台</span>
    <span>余额: <span style="color:#ffd700;">{{ user.balance }}</span> | <a href="/logout" style="color:#fff; text-decoration:none;">退出</a></span>
</div>
<div class="container">
    <div style="text-align: center; margin: 15px 0; color: #555;">
        欢迎回来，<b>{{ user.nickname }}</b>
    </div>
    <div class="card" style="padding: 0; overflow: hidden;">
        <a href="/game/2" style="text-decoration: none; color: inherit; display: flex; align-items: center; padding: 20px; border-bottom: 1px solid #f0f0f0;">
            <div style="width: 60px; height: 60px; background: #e6f2ff; border-radius: 8px; display: flex; justify-content: center; align-items: center; font-size: 24px; color: #00a2ff; margin-right: 15px;">🇨🇦</div>
            <div>
                <div style="font-size: 18px; font-weight: bold;">加拿大28 <span style="font-size: 10px; background: #00a2ff; color: #fff; padding: 2px 4px; border-radius: 2px;">官方</span></div>
                <div style="font-size: 12px; color: #888; margin-top: 5px;">有 13231 人在玩</div>
            </div>
        </a>
        <a href="/game/3" style="text-decoration: none; color: inherit; display: flex; align-items: center; padding: 20px; border-bottom: 1px solid #f0f0f0;">
            <div style="width: 60px; height: 60px; background: #fff2e6; border-radius: 8px; display: flex; justify-content: center; align-items: center; font-size: 24px; color: #ff9500; margin-right: 15px;">⏱️</div>
            <div>
                <div style="font-size: 18px; font-weight: bold;">分分28 <span style="font-size: 10px; background: #ff9500; color: #fff; padding: 2px 4px; border-radius: 2px;">推荐</span></div>
                <div style="font-size: 12px; color: #888; margin-top: 5px;">有 11081 人在玩</div>
            </div>
        </a>
        <a href="/game/13" style="text-decoration: none; color: inherit; display: flex; align-items: center; padding: 20px;">
            <div style="width: 60px; height: 60px; background: #e6ffe6; border-radius: 8px; display: flex; justify-content: center; align-items: center; font-size: 24px; color: #34c759; margin-right: 15px;">₿</div>
            <div>
                <div style="font-size: 18px; font-weight: bold;">比特28 <span style="font-size: 10px; background: #34c759; color: #fff; padding: 2px 4px; border-radius: 2px;">官方</span></div>
                <div style="font-size: 12px; color: #888; margin-top: 5px;">有 11983 人在玩</div>
            </div>
        </a>
    </div>
</div>
"""

HTML_GAME = BASE_CSS + """
<style>
    .game-header { background: #00a2ff; color: #fff; padding: 10px 15px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 10;}
    .game-header a { color: #fff; text-decoration: none; font-size: 20px; }
    .info-bar { background: #fff; padding: 10px; display: flex; justify-content: space-between; border-bottom: 1px solid #eee; }
    .chat-area { background: #f9f9f9; height: 35vh; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 10px; }
    .msg { display: flex; gap: 8px; font-size: 14px; }
    .msg.robot { background: #fff; padding: 10px; border-radius: 8px; border: 1px solid #e0e0e0; font-family: monospace; white-space: pre-wrap; color: #333; }
    .msg.user { justify-content: flex-end; }
    .msg.user .bubble { background: #00a2ff; color: #fff; padding: 8px 12px; border-radius: 15px; max-width: 80%; }
    .msg.admin .bubble { background: #fff; color: #ff9500; border: 1px solid #ff9500; padding: 8px 12px; border-radius: 15px; }
    
    .bet-panel { background: #fff; padding: 10px; border-top: 1px solid #ddd; }
    .input-bar { display: flex; gap: 10px; margin-bottom: 10px; }
    .input-bar input { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 16px; outline: none; }
    .input-bar button { width: 80px; background: #ddd; border: none; border-radius: 4px; color: #666; font-weight: bold; cursor: pointer; }
    
    .keyboard { display: grid; grid-template-columns: repeat(5, 1fr); gap: 5px; }
    .key { background: #fff; border: 1px solid #ddd; border-radius: 4px; padding: 10px 0; text-align: center; cursor: pointer; display: flex; flex-direction: column; justify-content: center; align-items: center; user-select: none; }
    .key:active { background: #e6f2ff; border-color: #00a2ff; }
    .key-title { font-size: 16px; font-weight: bold; color: #333; }
    .key-odds { font-size: 11px; color: #888; margin-top: 2px; }
    .key-special { background: #f0f0f0; }
    .key-confirm { background: #00a2ff; color: #fff; grid-column: span 2; border-color: #00a2ff; }
    .key-confirm .key-title { color: #fff; font-size: 18px; }
    .key-cancel { background: #ff3b30; color: #fff; border-color: #ff3b30; }
    .key-cancel .key-title { color: #fff; }

    /* 客服悬浮窗 */
    #cs-btn { position: fixed; bottom: 80px; right: 20px; width: 50px; height: 50px; background: #00a2ff; color: #fff; border-radius: 50%; box-shadow: 0 4px 10px rgba(0,0,0,0.2); display: flex; justify-content: center; align-items: center; font-size: 24px; cursor: pointer; z-index: 999; }
    #cs-panel { display: none; position: fixed; bottom: 0; right: 0; width: 100%; max-width: 400px; height: 60vh; background: #f0f2f5; z-index: 1000; border-top-left-radius: 12px; border-top-right-radius: 12px; box-shadow: 0 -2px 10px rgba(0,0,0,0.1); flex-direction: column; }
    .cs-header { padding: 12px; background: #00a2ff; color: #fff; border-top-left-radius: 12px; border-top-right-radius: 12px; display: flex; justify-content: space-between; font-weight: bold; }
    .cs-body { flex: 1; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 10px; }
    .cs-footer { padding: 10px; background: #fff; display: flex; gap: 5px; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }
    .cs-msg { max-width: 80%; padding: 8px 12px; border-radius: 8px; font-size: 14px; }
    .cs-msg.me { background: #00a2ff; color: #fff; align-self: flex-end; border-bottom-right-radius: 0; }
    .cs-msg.other { background: #fff; color: #333; align-self: flex-start; border-bottom-left-radius: 0; }
    .cs-msg img { max-width: 100%; border-radius: 4px; }
</style>

<div class="game-header">
    <a href="/">〈</a>
    <span>{{ game_name }}-2.8</span>
    <span style="font-size:14px;">余额: {{ user.balance }}</span>
</div>

<div class="info-bar">
    <div>
        <div style="font-size: 12px; color: #888;">第 <span id="next-period">--</span> 期开奖</div>
        <div style="font-size: 18px; font-weight: bold; color: #333; margin-top: 4px;" id="status-box"><span id="status-text" style="background:#ddd; color:#666; padding:2px 6px; border-radius:4px; font-size:12px;">加载中</span> <span id="cd-text" class="text-red"></span></div>
    </div>
    <div style="text-align: right;">
        <div style="font-size: 12px; color: #888;">第 <span id="cur-period">--</span> 期开奖</div>
        <div style="font-size: 18px; font-weight: bold; margin-top: 4px;">
            <span id="cur-nums">-</span> = <span id="cur-total" class="text-blue">-</span> <span id="cur-attr" style="font-size:14px; margin-left:5px;">-</span>
        </div>
    </div>
</div>

<div class="chat-area" id="chat-box"></div>

<div class="bet-panel">
    <div class="input-bar">
        <input type="text" id="bet-input" placeholder="请编辑下注内容..." readonly>
        <button onclick="cancelInput()">取消</button>
    </div>
    
    <div class="keyboard">
        <div class="key key-special" onclick="addBet('豹子', 88)"><span class="key-title">豹子</span><span class="key-odds">88.00</span></div>
        <div class="key key-special" onclick="addBet('顺子', 16)"><span class="key-title">顺子</span><span class="key-odds">16.00</span></div>
        <div class="key key-special" onclick="addBet('对子', 3.6)"><span class="key-title">对子</span><span class="key-odds">3.60</span></div>
        <div class="key" onclick="addBet('0', 960)"><span class="key-title">0</span><span class="key-odds">960</span></div>
        <div class="key" onclick="addBet('1', 320)"><span class="key-title">1</span><span class="key-odds">320</span></div>
        
        <div class="key" onclick="addBet('大', 2.8)"><span class="key-title">大</span><span class="key-odds">2.80</span></div>
        <div class="key" onclick="addBet('2', 160)"><span class="key-title">2</span><span class="key-odds">160</span></div>
        <div class="key" onclick="addBet('3', 97)"><span class="key-title">3</span><span class="key-odds">97</span></div>
        <div class="key" onclick="addBet('4', 64.5)"><span class="key-title">4</span><span class="key-odds">64.5</span></div>
        <div class="key" onclick="addBet('大单', 6.3)"><span class="key-title">大单</span><span class="key-odds">6.30</span></div>
        
        <div class="key" onclick="addBet('小', 2.8)"><span class="key-title">小</span><span class="key-odds">2.80</span></div>
        <div class="key" onclick="addBet('5', 46.5)"><span class="key-title">5</span><span class="key-odds">46.5</span></div>
        <div class="key" onclick="addBet('6', 35)"><span class="key-title">6</span><span class="key-odds">35</span></div>
        <div class="key" onclick="addBet('7', 27.2)"><span class="key-title">7</span><span class="key-odds">27.2</span></div>
        <div class="key" onclick="addBet('大双', 6.7)"><span class="key-title">大双</span><span class="key-odds">6.70</span></div>
        
        <div class="key" onclick="addBet('单', 2.8)"><span class="key-title">单</span><span class="key-odds">2.80</span></div>
        <div class="key" onclick="addBet('8', 22)"><span class="key-title">8</span><span class="key-odds">22</span></div>
        <div class="key" onclick="addBet('9', 18)"><span class="key-title">9</span><span class="key-odds">18</span></div>
        <div class="key" onclick="addBet('10', 15.8)"><span class="key-title">10</span><span class="key-odds">15.8</span></div>
        <div class="key" onclick="addBet('小单', 6.3)"><span class="key-title">小单</span><span class="key-odds">6.30</span></div>
        
        <div class="key" onclick="addBet('双', 2.8)"><span class="key-title">双</span><span class="key-odds">2.80</span></div>
        <div class="key" onclick="addBet('11', 14.4)"><span class="key-title">11</span><span class="key-odds">14.4</span></div>
        <div class="key" onclick="addBet('12', 13.6)"><span class="key-title">12</span><span class="key-odds">13.6</span></div>
        <div class="key" onclick="addBet('13', 13.3)"><span class="key-title">13</span><span class="key-odds">13.3</span></div>
        <div class="key" onclick="addBet('小双', 6.7)"><span class="key-title">小双</span><span class="key-odds">6.70</span></div>
        
        <div class="key" onclick="addBet('极大', 16)"><span class="key-title">极大</span><span class="key-odds">16.0</span></div>
        <div class="key key-confirm" onclick="submitBet()"><span class="key-title">确认下注</span></div>
        <div class="key key-cancel" onclick="cancelAllBet()"><span class="key-title">取消全部</span></div>
        <div class="key" onclick="addBet('极小', 16)"><span class="key-title">极小</span><span class="key-odds">16.0</span></div>
        <div class="key" style="visibility: hidden;"></div>
    </div>
</div>

<!-- 客服悬浮按钮与面板 -->
<div id="cs-btn" onclick="toggleCS()">💬</div>
<div id="cs-panel">
    <div class="cs-header">
        <span>联系在线客服</span>
        <span onclick="toggleCS()" style="cursor:pointer;">✖</span>
    </div>
    <div class="cs-body" id="cs-body"></div>
    <div class="cs-footer">
        <input type="file" id="cs-img" accept="image/*" style="display:none;" onchange="sendCSImg()">
        <label for="cs-img" style="padding:10px; background:#f0f2f5; border-radius:4px; cursor:pointer; font-size:18px;">📷</label>
        <input type="text" id="cs-input" style="flex:1; border:1px solid #ddd; padding:8px; border-radius:4px; outline:none;" placeholder="请描述您的问题...">
        <button onclick="sendCSMsg()" style="background:#00a2ff; color:#fff; border:none; padding:0 15px; border-radius:4px; font-weight:bold;">发送</button>
    </div>
</div>

<script>
    const G_TYPE = "{{ g_type }}";
    let liveData = null;
    let currentBet = {};
    let csOpened = false;
    
    function fetchLive() {
        fetch('/api/live/' + G_TYPE).then(r => r.json()).then(d => {
            liveData = d;
            document.getElementById('next-period').innerText = d.next_period;
            document.getElementById('cur-period').innerText = d.period;
            if(d.nums.length === 3) {
                document.getElementById('cur-nums').innerHTML = d.nums.map(n => `<span style="display:inline-block; width:24px; height:24px; line-height:24px; border-radius:50%; background:#00a2ff; color:#fff; text-align:center; font-size:14px; margin:0 2px;">${n}</span>`).join(' + ');
                document.getElementById('cur-total').innerText = d.total;
                let attr = d.total >= 14 ? '大' : '小';
                attr += d.total % 2 === 0 ? '双' : '单';
                document.getElementById('cur-attr').innerText = attr;
            }
            document.getElementById('status-text').innerText = d.status;
        });
    }
    setInterval(fetchLive, 2000); fetchLive();
    
    setInterval(() => {
        if(!liveData || !liveData.next_time) return;
        let now = Date.now() / 1000;
        let leftDraw = Math.max(0, Math.floor(liveData.next_time - now));
        let closeLimit = G_TYPE === '2' ? 30 : 5;
        let leftClose = leftDraw - closeLimit;
        
        let cdEl = document.getElementById('cd-text');
        if(leftClose > 0) { cdEl.innerText = leftClose + "秒封盘"; }
        else { cdEl.innerText = "已封盘"; document.getElementById('bet-input').value = "封盘中禁止下注"; }
    }, 1000);

    function fetchChat() {
        fetch('/api/chat/' + G_TYPE).then(r => r.json()).then(msgs => {
            let box = document.getElementById('chat-box');
            box.innerHTML = '';
            msgs.reverse().forEach(m => {
                let d = document.createElement('div');
                if(m.role === 'robot') { d.className = 'msg robot'; d.innerText = m.content; }
                else if (m.role === 'admin') { d.className = 'msg admin'; d.innerHTML = `<div class="bubble">[客服] ${m.content}</div>`; }
                else { d.className = 'msg user'; d.innerHTML = `<div class="bubble">${m.content}</div>`; }
                box.appendChild(d);
            });
            box.scrollTop = box.scrollHeight;
        });
    }
    setInterval(fetchChat, 3000); fetchChat();

    function toggleCS() {
        let p = document.getElementById('cs-panel');
        if(p.style.display === 'flex') { p.style.display = 'none'; csOpened = false; }
        else { p.style.display = 'flex'; csOpened = true; fetchCS(); }
    }
    function fetchCS() {
        if(!csOpened) return;
        fetch('/api/cs').then(r => r.json()).then(msgs => {
            let box = document.getElementById('cs-body');
            box.innerHTML = '';
            msgs.reverse().forEach(m => {
                let d = document.createElement('div');
                if(m.role === 'admin') { d.className = 'cs-msg other'; }
                else { d.className = 'cs-msg me'; }
                if(m.content.startsWith('data:image')) { d.innerHTML = `<img src="${m.content}">`; }
                else { d.innerText = m.content; }
                box.appendChild(d);
            });
            box.scrollTop = box.scrollHeight;
        });
    }
    setInterval(fetchCS, 3000);
    function sendCSMsg() {
        let val = document.getElementById('cs-input').value;
        if(!val) return;
        fetch('/api/cs', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content: val}) })
        .then(()=>{ document.getElementById('cs-input').value=''; fetchCS(); });
    }
    function sendCSImg() {
        let file = document.getElementById('cs-img').files[0];
        if(!file) return;
        let reader = new FileReader();
        reader.onload = function(e) {
            fetch('/api/cs', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content: e.target.result}) })
            .then(()=>{ fetchCS(); });
        };
        reader.readAsDataURL(file);
    }

    function addBet(key, odds) {
        if(liveData && Date.now()/1000 > liveData.next_time - (G_TYPE==='2'?30:5)) { return alert("已封盘，停止下注"); }
        let amount = prompt(`请输入下注【${key}】的金额:`, "10");
        if(!amount || isNaN(amount) || Number(amount) <= 0) return;
        if(!currentBet[key]) currentBet[key] = 0;
        currentBet[key] += Number(amount);
        updateInputDisplay();
    }
    function updateInputDisplay() {
        let strArr = [];
        for(let k in currentBet) { strArr.push(`${k}:${currentBet[k]}`); }
        document.getElementById('bet-input').value = strArr.join(" ");
    }
    function cancelInput() { currentBet = {}; document.getElementById('bet-input').value = ""; }
    function cancelAllBet() { if(confirm("确定要取消所有尚未开奖的下注吗？")) { alert("请联系客服取消已提交的注单。"); } }
    
    function submitBet() {
        if(Object.keys(currentBet).length === 0) return alert("请先选择下注内容");
        let promises = [];
        for(let key in currentBet) {
            let amt = currentBet[key];
            let type = 'num'; let odds = 0;
            if(!isNaN(key)) { odds = ODDS_MAP[key] || 10; }
            else if(['大','小'].includes(key)) { type='bs'; odds=2.8; }
            else if(['单','双'].includes(key)) { type='oe'; odds=2.8; }
            else if(key.length===2) { type='combo'; odds=key==='大单'||key==='小双'?6.3:6.7; }
            else { type='pattern'; odds= key==='豹子'?88:(key==='顺子'||key==='极大'||key==='极小'?16:3.6); }
            
            promises.push(fetch('/api/bet', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({game_type: G_TYPE, bet_type: type, bet_value: key, amount: amt, odds: odds}) }).then(r=>r.json()));
        }
        Promise.all(promises).then(results => {
            if(results.every(r => r.success)) {
                alert("下注成功！"); currentBet = {}; document.getElementById('bet-input').value = ""; fetchLive(); fetchChat();
            } else { alert("部分下注失败，可能余额不足或已封盘"); }
        });
    }
    
    const ODDS_MAP = {
        '0':960, '27':960, '1':320, '26':320, '2':160, '25':160, '3':97, '24':97, '4':64.5, '23':64.5, '5':46.5, '22':46.5,
        '6':35, '21':35, '7':27.2, '20':27.2, '8':22, '19':22, '9':18, '18':18, '10':15.8, '17':15.8, '11':14.4, '16':14.4,
        '12':13.6, '15':13.6, '13':13.3, '14':13.3
    };
</script>
"""

HTML_ADMIN = BASE_CSS + """
<div class="header">
    <span>舰长2.8后台</span>
    <div><a href="/logout" style="color:#fff; text-decoration:none;">退出</a></div>
</div>
<div class="container">
    <div class="card">
        <h4 style="margin-bottom:10px;">手动上下分</h4>
        <form method="POST" style="display:flex; gap:10px;">
            <input type="hidden" name="act" value="manual_money">
            <input type="number" name="uid" placeholder="用户ID" required style="width:80px; padding:8px;">
            <input type="number" step="0.01" name="amount" placeholder="金额" required style="flex:1; padding:8px;">
            <button type="submit" name="m_type" value="add" style="background:#34c759; color:#fff; border:none; padding:8px 15px; border-radius:4px;">充值</button>
            <button type="submit" name="m_type" value="sub" style="background:#ff3b30; color:#fff; border:none; padding:8px 15px; border-radius:4px;">扣款</button>
        </form>
    </div>
    
    <div class="card">
        <h4 style="margin-bottom:10px;">用户列表/拉黑</h4>
        <table style="width:100%; border-collapse:collapse; font-size:12px; text-align:center;">
            <tr style="background:#f5f5f5;"><th style="padding:8px;">ID</th><th>账号</th><th>中文名</th><th>余额</th><th>操作</th></tr>
            {% for u in users %}
            <tr style="border-bottom:1px solid #eee;">
                <td style="padding:8px;">{{ u.id }}</td><td>{{ u.username }}</td><td class="text-blue">{{ u.nickname }}</td><td class="text-green">{{ u.balance }}</td>
                <td>
                    <form method="POST">
                        <input type="hidden" name="uid" value="{{ u.id }}">
                        {% if u.status == 'banned' %}
                        <button type="submit" name="act" value="unban" style="color:#34c759; background:none; border:none; font-size:12px;">恢复</button>
                        {% else %}
                        <button type="submit" name="act" value="ban" style="color:#ff3b30; background:none; border:none; font-size:12px;">拉黑</button>
                        {% endif %}
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div class="card">
        <h4 style="margin-bottom:10px;">📩 客服消息处理</h4>
        <div style="max-height: 300px; overflow-y: auto; margin-bottom: 10px; font-size:12px;">
            {% for c in cs_msgs %}
            <div style="border-bottom:1px dashed #eee; padding:5px; display:flex; justify-content:space-between;">
                <div>
                    <span style="color:#00a2ff; font-weight:bold;">[{{ c.nickname }} (ID:{{ c.user_id }})]</span> 
                    {% if c.content.startswith('data:image') %}
                    <br><img src="{{ c.content }}" style="max-height:60px; border-radius:4px;">
                    {% else %}
                    : {{ c.content }}
                    {% endif %}
                </div>
                <span style="color:#999; font-size:10px;">{{ c.created_at[11:16] }}</span>
            </div>
            {% endfor %}
        </div>
        <form method="POST" style="display:flex; flex-direction:column; gap:10px;">
            <input type="hidden" name="act" value="reply_cs">
            <input type="number" name="uid" placeholder="回复给客户ID" required style="padding:8px; border:1px solid #ddd; border-radius:4px;">
            <input type="text" name="msg" placeholder="输入回复内容..." required style="padding:8px; border:1px solid #ddd; border-radius:4px;">
            <button type="submit" class="btn">发送回复</button>
        </form>
    </div>
</div>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8888))
    app.run(host='0.0.0.0', port=port)
