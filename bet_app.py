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

# 内存状态
LIVE_DATA = {
    "2": {"period": "", "next_period": "", "left_time": 0, "nums": [], "total": 0, "status": "loading", "history": []},
    "3": {"period": "", "next_period": "", "left_time": 0, "nums": [], "total": 0, "status": "loading", "history": []},
    "13": {"period": "", "next_period": "", "left_time": 0, "nums": [], "total": 0, "status": "loading", "history": []}
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
        for g_type, cfg in GAMES.items():
            try:
                req = urllib.request.Request(cfg['url'], headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    if data.get('data'):
                        latest_data = data['data']
                        latest = latest_data[0]
                        
                        # 构建走势图历史
                        history = []
                        for item in latest_data[:15]:
                            history.append({"period": item['period'][-3:], "total": item['total'], "attr": f"{item['big_small']}{item['odd_even']}"})
                        
                        # 判断新期
                        if LIVE_DATA[g_type]['period'] != latest['period']:
                            # 结算上期
                            if LIVE_DATA[g_type]['period'] != "":
                                settle_bets(g_type, LIVE_DATA[g_type]['period'], LIVE_DATA[g_type]['nums'], LIVE_DATA[g_type]['total'])
                                
                            LIVE_DATA[g_type] = {
                                "period": latest['period'],
                                "next_period": str(int(latest['period']) + 1),
                                "left_time": cfg['interval'],
                                "nums": [latest['num1'], latest['num2'], latest['num3']],
                                "total": latest['total'],
                                "history": history
                            }
                        
                        # 核心：精准计算剩余秒数，按接口给出的时间对齐
                        # 因为接口有延迟，我们直接按抓取到的瞬间开始倒计时 interval 秒
                        draw_dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                        # 服务器可能是 UTC，但不管怎样，差值计算是相对的
                        now_utc = datetime.utcnow()
                        
                        # 如果接口刚好发了新的一期，重置倒计时
                        if LIVE_DATA[g_type]['period'] != latest['period']:
                             LIVE_DATA[g_type]['left_time'] = cfg['interval']
                        else:
                             # 根据时间差动态修正
                             # 接口时间是北京时间，减去8小时得到 UTC
                             target_utc = draw_dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])
                             diff = (target_utc - now_utc).total_seconds()
                             LIVE_DATA[g_type]['left_time'] = max(0, int(diff))
                        
                        # 封盘逻辑
                        if LIVE_DATA[g_type]['left_time'] <= cfg['close_sec']:
                            LIVE_DATA[g_type]['status'] = "封盘中"
                            if REPORTED_PERIODS[g_type] != LIVE_DATA[g_type]['next_period']:
                                REPORTED_PERIODS[g_type] = LIVE_DATA[g_type]['next_period']
                                threading.Thread(target=broadcast_bill, args=(g_type, LIVE_DATA[g_type]['next_period'])).start()
                        else:
                            LIVE_DATA[g_type]['status'] = "下注中"
                            
            except Exception as e:
                pass
        time.sleep(1.5)

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
    
    if LIVE_DATA[g_type]['left_time'] <= GAMES[g_type]['close_sec']:
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

@app.route('/api/my_bets')
def api_my_bets():
    if 'user_id' not in session: return jsonify([])
    with get_db() as conn:
        bets = conn.execute("SELECT * FROM bets WHERE user_id=? ORDER BY id DESC LIMIT 20", (session['user_id'],)).fetchall()
    return jsonify([dict(b) for b in bets])

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
    
    /* 走势图 */
    .trend-box { background: #fff; padding: 8px 10px; display: flex; gap: 10px; overflow-x: auto; border-bottom: 1px solid #eee; white-space: nowrap; }
    .trend-item { display: flex; flex-direction: column; align-items: center; font-size: 11px; min-width: 35px; }
    .trend-ball { width: 24px; height: 24px; border-radius: 50%; background: #00a2ff; color: #fff; line-height: 24px; text-align: center; font-size: 12px; font-weight: bold; margin: 2px 0; }
    .trend-ball.red { background: #ff3b30; }
    .trend-ball.blue { background: #5ac8fa; }
    .trend-attr { color: #888; }

    .chat-area { background: #f9f9f9; height: 35vh; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 10px; }
    .msg { display: flex; gap: 8px; font-size: 14px; }
    .msg.robot { background: #fff; padding: 10px; border-radius: 8px; border: 1px solid #e0e0e0; font-family: monospace; white-space: pre-wrap; color: #333; }
    .msg.user { justify-content: flex-end; }
    .msg.user .bubble { background: #00a2ff; color: #fff; padding: 8px 12px; border-radius: 15px; max-width: 80%; }
    .msg.admin .bubble { background: #fff; color: #ff9500; border: 1px solid #ff9500; padding: 8px 12px; border-radius: 15px; }
    
    .bet-panel { background: #fff; padding: 10px; border-top: 1px solid #ddd; }
    .input-bar { display: flex; gap: 10px; margin-bottom: 10px; }
    .input-bar input { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 16px; outline: none; }
    
    /* 还原图6键盘 */
    .kbd { display: flex; flex-direction: column; gap: 4px; }
    .kbd-row { display: flex; gap: 4px; }
    .k-btn { flex: 1; background: #fff; border: 1px solid #ddd; border-radius: 4px; padding: 8px 0; text-align: center; cursor: pointer; user-select: none; display: flex; flex-direction: column; justify-content: center; align-items: center; }
    .k-btn:active { background: #e6f2ff; border-color: #00a2ff; }
    .k-t { font-size: 16px; font-weight: bold; color: #333; }
    .k-t.num { color: #00a2ff; font-size: 20px; }
    .k-o { font-size: 11px; color: #888; }
    
    .k-gray { background: #aeb9c5; color: #fff; border-color: #aeb9c5; }
    .k-gray .k-t { color: #fff; }
    .k-blue { background: #00a2ff; border-color: #00a2ff; }
    .k-blue .k-t { color: #fff; font-size: 18px; }
    .k-red { background: #ff3b30; border-color: #ff3b30; }
    .k-red .k-t { color: #fff; }
    
    /* 客服与功能按钮 */
    .action-btns { display: flex; justify-content: space-around; background: #fff; padding: 10px 0; border-bottom: 1px solid #eee; }
    .act-btn { font-size: 14px; color: #00a2ff; cursor: pointer; text-decoration: none; }
    
    #cs-btn { position: fixed; bottom: 80px; right: 20px; width: 50px; height: 50px; background: #00a2ff; color: #fff; border-radius: 50%; box-shadow: 0 4px 10px rgba(0,0,0,0.2); display: flex; justify-content: center; align-items: center; font-size: 24px; cursor: pointer; z-index: 999; }
    #cs-panel { display: none; position: fixed; bottom: 0; right: 0; width: 100%; max-width: 400px; height: 60vh; background: #f0f2f5; z-index: 1000; border-top-left-radius: 12px; border-top-right-radius: 12px; box-shadow: 0 -2px 10px rgba(0,0,0,0.1); flex-direction: column; }
    .cs-header { padding: 12px; background: #00a2ff; color: #fff; border-top-left-radius: 12px; border-top-right-radius: 12px; display: flex; justify-content: space-between; font-weight: bold; }
    .cs-body { flex: 1; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 10px; }
    .cs-footer { padding: 10px; background: #fff; display: flex; gap: 5px; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }
    .cs-msg { max-width: 80%; padding: 8px 12px; border-radius: 8px; font-size: 14px; }
    .cs-msg.me { background: #00a2ff; color: #fff; align-self: flex-end; border-bottom-right-radius: 0; }
    .cs-msg.other { background: #fff; color: #333; align-self: flex-start; border-bottom-left-radius: 0; }

    /* 弹窗遮罩 */
    .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 2000; justify-content: center; align-items: center; }
    .modal-content { background: #fff; width: 90%; max-width: 400px; max-height: 80vh; border-radius: 8px; padding: 20px; overflow-y: auto; position: relative; }
    .close-modal { position: absolute; top: 10px; right: 15px; font-size: 20px; cursor: pointer; color: #888; }
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

<!-- 近期走势 -->
<div class="trend-box" id="trend-box"></div>

<!-- 功能按钮 -->
<div class="action-btns">
    <a href="javascript:void(0)" class="act-btn" onclick="openModal('modal-odds')">📖 赔率说明</a>
    <a href="javascript:void(0)" class="act-btn" onclick="fetchMyBets()">📋 我的账单</a>
</div>

<div class="chat-area" id="chat-box"></div>

<div class="bet-panel">
    <div class="input-bar">
        <input type="text" id="bet-input" placeholder="可点击下方键盘，也可直接打字输入 (如: 大:100)">
    </div>
    
    <!-- 高仿图6键盘 -->
    <div class="kbd">
        <div class="kbd-row">
            <div class="k-btn k-gray" onclick="cancelInput()"><span class="k-t">取消下注</span></div>
            <div class="k-btn" onclick="addBet('豹子', 88)"><span class="k-t">豹子</span><span class="k-o">88.00</span></div>
            <div class="k-btn" onclick="addBet('顺子', 16)"><span class="k-t">顺子</span><span class="k-o">16.00</span></div>
            <div class="k-btn" onclick="addBet('对子', 3.6)"><span class="k-t">对子</span><span class="k-o">3.60</span></div>
            <div class="k-btn k-gray" onclick="backspace()"><span class="k-t">⌫</span></div>
        </div>
        <div class="kbd-row">
            <div class="k-btn" onclick="addBet('大', 2.8)"><span class="k-t">大</span><span class="k-o">2.80</span></div>
            <div class="k-btn" onclick="addBet('1', 320)"><span class="k-t num">1</span><span class="k-o">320</span></div>
            <div class="k-btn" onclick="addBet('2', 160)"><span class="k-t num">2</span><span class="k-o">160</span></div>
            <div class="k-btn" onclick="addBet('3', 97)"><span class="k-t num">3</span><span class="k-o">97</span></div>
            <div class="k-btn" onclick="addBet('大单', 6.3)"><span class="k-t">大单</span><span class="k-o">6.30</span></div>
        </div>
        <div class="kbd-row">
            <div class="k-btn" onclick="addBet('小', 2.8)"><span class="k-t">小</span><span class="k-o">2.80</span></div>
            <div class="k-btn" onclick="addBet('4', 64.5)"><span class="k-t num">4</span><span class="k-o">64.5</span></div>
            <div class="k-btn" onclick="addBet('5', 46.5)"><span class="k-t num">5</span><span class="k-o">46.5</span></div>
            <div class="k-btn" onclick="addBet('6', 35)"><span class="k-t num">6</span><span class="k-o">35</span></div>
            <div class="k-btn" onclick="addBet('大双', 6.7)"><span class="k-t">大双</span><span class="k-o">6.70</span></div>
        </div>
        <div class="kbd-row">
            <div class="k-btn" onclick="addBet('单', 2.8)"><span class="k-t">单</span><span class="k-o">2.80</span></div>
            <div class="k-btn" onclick="addBet('7', 27.2)"><span class="k-t num">7</span><span class="k-o">27.2</span></div>
            <div class="k-btn" onclick="addBet('8', 22)"><span class="k-t num">8</span><span class="k-o">22</span></div>
            <div class="k-btn" onclick="addBet('9', 18)"><span class="k-t num">9</span><span class="k-o">18</span></div>
            <div class="k-btn" onclick="addBet('小单', 6.3)"><span class="k-t">小单</span><span class="k-o">6.30</span></div>
        </div>
        <div class="kbd-row">
            <div class="k-btn" onclick="addBet('双', 2.8)"><span class="k-t">双</span><span class="k-o">2.80</span></div>
            <div class="k-btn" onclick="addBet('极大', 16)"><span class="k-t">极大</span><span class="k-o">16.0</span></div>
            <div class="k-btn" onclick="addBet('0', 960)"><span class="k-t num">0</span><span class="k-o">960</span></div>
            <div class="k-btn" onclick="addBet('极小', 16)"><span class="k-t">极小</span><span class="k-o">16.0</span></div>
            <div class="k-btn" onclick="addBet('小双', 6.7)"><span class="k-t">小双</span><span class="k-o">6.70</span></div>
        </div>
        <div class="kbd-row" style="margin-top:4px;">
            <div class="k-btn k-blue" onclick="submitBet()" style="flex: 3;"><span class="k-t">确认下注</span></div>
        </div>
    </div>
</div>

<!-- 客服悬浮 -->
<div id="cs-btn" onclick="toggleCS()">💬</div>
<div id="cs-panel">
    <div class="cs-header"><span>联系在线客服</span><span onclick="toggleCS()" style="cursor:pointer;">✖</span></div>
    <div class="cs-body" id="cs-body"></div>
    <div class="cs-footer">
        <input type="file" id="cs-img" accept="image/*" style="display:none;" onchange="sendCSImg()">
        <label for="cs-img" style="padding:10px; background:#f0f2f5; border-radius:4px; cursor:pointer; font-size:18px;">📷</label>
        <input type="text" id="cs-input" style="flex:1; border:1px solid #ddd; padding:8px; border-radius:4px; outline:none;" placeholder="请描述您的问题...">
        <button onclick="sendCSMsg()" style="background:#00a2ff; color:#fff; border:none; padding:0 15px; border-radius:4px; font-weight:bold;">发送</button>
    </div>
</div>

<!-- 弹窗：赔率说明 -->
<div id="modal-odds" class="modal">
    <div class="modal-content">
        <span class="close-modal" onclick="closeModal('modal-odds')">✖</span>
        <h3 style="text-align:center; margin-bottom:15px;">赔率说明</h3>
        <div style="font-size:13px; line-height:1.8; color:#555;">
            <p>💵0/27=960倍 | 1/26=320倍</p>
            <p>💵2/25=160倍 | 3/24=97倍</p>
            <p>💵4/23=64.5倍 | 5/22=46.5倍</p>
            <p>💵6/21=35倍 | 7/20=27.2倍</p>
            <p>💵8/19=22倍 | 9/18=18倍</p>
            <p>💵10/17=15.8倍 | 11/16=14.4倍</p>
            <p>💵12/15=13.6倍 | 13/14=13.3倍</p>
            <p style="margin-top:10px;">🈵大小单双=2.8倍</p>
            <p>🈵大单/小双 6.30倍</p>
            <p>🈵大双/小单 6.70倍</p>
            <p>⚠️遇13/14 对子 顺子 豹子中奖回本金</p>
            <p>🔶豹子88倍 | 🔷极值16倍</p>
            <p>🔶顺子16倍 | 🔷对子3.60倍</p>
            <p style="margin-top:15px; font-weight:bold; color:#ff3b30; text-align:center;">最终解释权归舰长平台所有</p>
        </div>
    </div>
</div>

<!-- 弹窗：我的账单 -->
<div id="modal-bets" class="modal">
    <div class="modal-content">
        <span class="close-modal" onclick="closeModal('modal-bets')">✖</span>
        <h3 style="text-align:center; margin-bottom:15px;">近期账单</h3>
        <table style="width:100%; border-collapse:collapse; font-size:12px; text-align:center;">
            <tr style="background:#f5f5f5;"><th>期号</th><th>内容</th><th>金额</th><th>状态</th></tr>
            <tbody id="bets-table-body"></tbody>
        </table>
    </div>
</div>

<script>
    const G_TYPE = "{{ g_type }}";
    let liveData = null;
    let currentBet = {};
    let csOpened = false;

    // 弹窗逻辑
    function openModal(id) { document.getElementById(id).style.display = 'flex'; }
    function closeModal(id) { document.getElementById(id).style.display = 'none'; }
    function fetchMyBets() {
        fetch('/api/my_bets').then(r=>r.json()).then(data => {
            let tbody = document.getElementById('bets-table-body');
            tbody.innerHTML = '';
            if(data.length === 0) { tbody.innerHTML = '<tr><td colspan="4">暂无记录</td></tr>'; }
            data.forEach(b => {
                let cls = b.status === 'win' ? 'green' : (b.status === 'lose' ? 'red' : '');
                let win_amt = b.status === 'win' ? b.win_amount : '-';
                tbody.innerHTML += `<tr style="border-bottom:1px solid #eee;"><td>${b.period}</td><td>${b.bet_value}</td><td>${b.amount}</td><td class="${cls}">${win_amt}</td></tr>`;
            });
            openModal('modal-bets');
        });
    }

    // 获取走势与实时数据
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
            
            // 渲染走势图
            if(d.history && d.history.length > 0) {
                let trendHtml = '';
                d.history.forEach(item => {
                    let color = item.attr.includes('大') ? 'red' : 'blue';
                    trendHtml += `<div class="trend-item"><span class="trend-attr">${item.period}</span><div class="trend-ball ${color}">${item.total}</div><span class="trend-attr">${item.attr}</span></div>`;
                });
                document.getElementById('trend-box').innerHTML = trendHtml;
            }
            
            document.getElementById('status-text').innerText = d.status;
        });
    }
    setInterval(fetchLive, 2000); fetchLive();

    // 精准倒计时（本地递减）
    setInterval(() => {
        if(!liveData || liveData.left_time === undefined) return;
        
        // 本地时间流逝
        liveData.left_time -= 1;
        if(liveData.left_time < 0) liveData.left_time = 0;
        
        let leftDraw = liveData.left_time;
        let closeLimit = G_TYPE === '2' ? 30 : 5;
        let leftClose = leftDraw - closeLimit;
        
        let cdEl = document.getElementById('cd-text');
        if(leftClose > 0) {
            cdEl.innerText = leftClose + "秒封盘";
            cdEl.style.color = "#ff3b30";
            document.getElementById('bet-input').disabled = false;
        } else {
            cdEl.innerText = "已封盘";
            cdEl.style.color = "#888";
            document.getElementById('bet-input').disabled = true;
            document.getElementById('bet-input').value = "封盘中禁止下注";
        }
    }, 1000);

    // 聊天公屏
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

    // 客服功能
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
                if(m.content.startsWith('data:image')) { d.innerHTML = `<img src="${m.content}" style="max-width:100%; border-radius:4px;">`; }
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

    // ==== 下注逻辑 ====
    function addBet(key, odds) {
        if(liveData && liveData.left_time <= (G_TYPE==='2'?30:5)) { return alert("已封盘，停止下注"); }
        let amount = prompt(`请输入下注【${key}】的金额:`, "10");
        if(!amount || isNaN(amount) || Number(amount) <= 0) return;
        
        // 直接追加到输入框
        let input = document.getElementById('bet-input');
        let currentVal = input.value;
        if(currentVal.includes(key + ":")) {
             alert("请不要多次下注同一项，可修改金额后确认。");
             return;
        }
        
        if(currentVal) { input.value += " " + key + ":" + amount; }
        else { input.value = key + ":" + amount; }
    }
    
    function backspace() {
        let input = document.getElementById('bet-input');
        input.value = input.value.slice(0, -1);
    }
    
    function cancelInput() {
        document.getElementById('bet-input').value = "";
    }
    
    // 解析用户输入的下注内容并提交
    function submitBet() {
        let inputVal = document.getElementById('bet-input').value.trim();
        if(!inputVal) return alert("请先输入下注内容");
        
        // 拆分格式: "大:100 2:50"
        let parts = inputVal.split(/\s+/);
        let promises = [];
        
        for(let part of parts) {
            let match = part.match(/([a-zA-Z\u4e00-\u9fa5]+|\d+)[:：](\d+(\.\d+)?)/);
            if(match) {
                let key = match[1];
                let amt = parseFloat(match[2]);
                
                let type = 'num'; let odds = 0;
                if(!isNaN(key)) { odds = ODDS_MAP[key] || 10; }
                else if(['大','小'].includes(key)) { type='bs'; odds=2.8; }
                else if(['单','双'].includes(key)) { type='oe'; odds=2.8; }
                else if(key.length===2) { type='combo'; odds=key==='大单'||key==='小双'?6.3:6.7; }
                else { type='pattern'; odds= key==='豹子'?88:(key==='顺子'||key==='极大'||key==='极小'?16:3.6); }
                
                promises.push(fetch('/api/bet', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({game_type: G_TYPE, bet_type: type, bet_value: key, amount: amt, odds: odds})
                }).then(r=>r.json()));
            }
        }
        
        if(promises.length === 0) return alert("下注格式错误，请使用如：大:100");
        
        Promise.all(promises).then(results => {
            if(results.every(r => r.success)) {
                alert("下注成功！");
                document.getElementById('bet-input').value = "";
                fetchLive(); fetchChat();
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
