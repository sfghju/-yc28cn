import urllib.request
import ssl
import json
import time
import threading
import os
import re
import sqlite3
import random
from flask import Flask, request, jsonify, render_template_string, session, redirect, send_file
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'yc28_captain_platform_secret_2026'
app.permanent_session_lifetime = timedelta(days=30)

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
    "2": {"period": "", "next_period": "", "left_time": 0, "nums": [], "total": 0, "status": "loading", "history": [], "robot_count": 0},
    "3": {"period": "", "next_period": "", "left_time": 0, "nums": [], "total": 0, "status": "loading", "history": [], "robot_count": 0},
    "13": {"period": "", "next_period": "", "left_time": 0, "nums": [], "total": 0, "status": "loading", "history": [], "robot_count": 0}
}
REPORTED_PERIODS = {"2": "", "3": "", "13": ""}

def get_db():
    conn = sqlite3.connect('captain28.db', timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, nickname TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, balance REAL DEFAULT 0.0, role TEXT DEFAULT 'user', status TEXT DEFAULT 'normal',
            avatar TEXT DEFAULT ''
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
        conn.execute('''CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount REAL, 
            status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username='ADMIN888'")
        if not cursor.fetchone():
            conn.execute("INSERT INTO users (username, nickname, password, role, avatar) VALUES ('ADMIN888', '站长', '123456', 'admin', 'https://api.dicebear.com/7.x/bottts/svg?seed=admin')")
        
        # 生成5000机器人
        robot_count = conn.execute("SELECT COUNT(*) FROM users WHERE role='robot'").fetchone()[0]
        if robot_count < 5000:
            surnames = ["赵", "钱", "孙", "李", "周", "吴", "郑", "王", "冯", "陈", "褚", "卫", "蒋", "沈", "韩", "杨", "朱", "秦"]
            names = ["哥", "姐", "总", "少", "神", "王", "帝", "霸", "龙", "虎", "强", "帅", "美", "丽", "花", "爷", "董"]
            for i in range(5000 - robot_count):
                uname = f"R{random.randint(10000, 99999)}_{i}"
                nick = random.choice(surnames) + random.choice(names) + str(random.randint(1, 99))
                avatar = f"https://api.dicebear.com/7.x/adventurer/svg?seed={uname}"
                try:
                    conn.execute("INSERT INTO users (username, nickname, password, role, balance, avatar) VALUES (?, ?, '123456', 'robot', 9999999, ?)", (uname, nick, avatar))
                except:
                    pass
            conn.commit()

init_db()

# ================== 极速结算模块 ==================
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
        if not pending_bets: return
        
        updates = []
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
                updates.append((bet['id'], 'refund', 0.0, bet['user_id'], bet['amount']))
            elif win:
                updates.append((bet['id'], 'win', win_amt, bet['user_id'], win_amt))
            else:
                updates.append((bet['id'], 'lose', 0.0, bet['user_id'], 0.0))

        for u in updates:
            bet_id, status, win_amt, uid, add_bal = u
            conn.execute("UPDATE bets SET status=?, win_amount=? WHERE id=?", (status, win_amt, bet_id))
            if add_bal > 0:
                conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (add_bal, uid))
        conn.commit()

def broadcast_bill(game_type, period):
    with get_db() as conn:
        bets = conn.execute('''SELECT u.nickname, b.bet_value, b.amount FROM bets b JOIN users u ON b.user_id = u.id WHERE b.game_type=? AND b.period=? ''', (game_type, period)).fetchall()
        if not bets: return
        
        user_bets = {}
        for b in bets:
            name = b['nickname']
            if name not in user_bets: user_bets[name] = {'items': [], 'total': 0}
            user_bets[name]['items'].append(f"{b['bet_value']}:{b['amount']}")
            user_bets[name]['total'] += b['amount']
        
        bill_lines = [f"========= 封盘统计 ========="]
        bill_lines.append(f"第 {period} 期玩家投注账单 (部分展示)")
        
        display_items = list(user_bets.items())[:30] 
        for u, data in display_items:
            items_str = " ".join(data['items'])
            bill_lines.append(f"{u}-[{items_str}]_{data['total']}")
        
        bill_lines.append(f"... 本期共有 {len(user_bets)} 名玩家参与！")
        bill_lines.append(f"===========================")
            
        conn.execute("INSERT INTO messages (game_type, user_id, role, content) VALUES (?, 0, 'robot', ?)", (game_type, "\n".join(bill_lines)))
        conn.commit()

def robot_continuous_bet(game_type):
    if LIVE_DATA[game_type]['left_time'] <= GAMES[game_type]['close_sec']: return

    num_robots = random.randint(1, 3)
    with get_db() as conn:
        robots = conn.execute("SELECT id, nickname FROM users WHERE role='robot' ORDER BY RANDOM() LIMIT ?", (num_robots,)).fetchall()
        for r in robots:
            amt = random.choice([10, 20, 50, 100, 200, 500])
            b_type = random.choice(['bs', 'oe', 'num', 'combo', 'pattern'])
            
            if b_type == 'bs': b_val = random.choice(['大', '小']); odds = 2.8
            elif b_type == 'oe': b_val = random.choice(['单', '双']); odds = 2.8
            elif b_type == 'num': b_val = str(random.randint(0, 27)); odds = ODDS['nums'].get(int(b_val), 10)
            elif b_type == 'combo': b_val = random.choice(['大单', '小双', '大双', '小单']); odds = 6.3 if '大单' in b_val or '小双' in b_val else 6.7
            else: b_val = random.choice(['豹子', '顺子', '对子', '极大', '极小']); odds = 88 if b_val=='豹子' else (16 if b_val in ['极大','极小','顺子'] else 3.6)
            
            conn.execute('''INSERT INTO bets (user_id, game_type, period, bet_type, bet_value, amount, odds) VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                         (r['id'], game_type, LIVE_DATA[game_type]['next_period'], b_type, b_val, amt, odds))
            conn.execute("INSERT INTO messages (game_type, user_id, role, content) VALUES (?, ?, 'user', ?)", (game_type, r['id'], f"{b_val}:{amt}"))
        
        conn.commit()
        count = conn.execute("SELECT COUNT(DISTINCT user_id) FROM bets WHERE game_type=? AND period=?", (game_type, LIVE_DATA[game_type]['next_period'])).fetchone()[0]
        LIVE_DATA[game_type]['robot_count'] = count

# ================== 核心抓取与结算控制 ==================
def fetch_loop():
    ctx = ssl._create_unverified_context()
    last_tick_time = time.time()
    
    while True:
        now_ts = time.time()
        for g_type, cfg in GAMES.items():
            try:
                req = urllib.request.Request(cfg['url'], headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    if data.get('data'):
                        latest_data = data['data']
                        latest = latest_data[0]
                        
                        history = [{"period": item['period'][-3:], "total": item['total'], "attr": f"{item['big_small']}{item['odd_even']}"} for item in latest_data[:15]]
                        
                        if LIVE_DATA[g_type]['period'] != latest['period']:
                            # 1. 发现新期，先结算上一期（毫秒级）
                            if LIVE_DATA[g_type]['period'] != "":
                                settle_bets(g_type, LIVE_DATA[g_type]['period'], LIVE_DATA[g_type]['nums'], LIVE_DATA[g_type]['total'])
                            
                            LIVE_DATA[g_type] = {
                                "period": latest['period'], "next_period": str(int(latest['period']) + 1),
                                "left_time": cfg['interval'], "nums": [latest['num1'], latest['num2'], latest['num3']],
                                "total": latest['total'], "history": history, "robot_count": 0
                            }
                        
                        draw_dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                        target_utc = draw_dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])
                        diff = (target_utc - datetime.utcnow()).total_seconds()
                        LIVE_DATA[g_type]['left_time'] = max(0, int(diff))
                        
                        if LIVE_DATA[g_type]['left_time'] <= cfg['close_sec']:
                            LIVE_DATA[g_type]['status'] = "封盘中"
                            if REPORTED_PERIODS[g_type] != LIVE_DATA[g_type]['next_period']:
                                REPORTED_PERIODS[g_type] = LIVE_DATA[g_type]['next_period']
                                threading.Thread(target=broadcast_bill, args=(g_type, LIVE_DATA[g_type]['next_period'])).start()
                        else:
                            LIVE_DATA[g_type]['status'] = "下注中"
                            if now_ts - last_tick_time >= 1.0:
                                threading.Thread(target=robot_continuous_bet, args=(g_type,)).start()
            except Exception:
                pass
        if now_ts - last_tick_time >= 1.0: last_tick_time = now_ts
        time.sleep(1)

threading.Thread(target=fetch_loop, daemon=True).start()

# ================== API 路由 ==================
@app.route('/api/live/<g_type>')
def api_live(g_type): return jsonify(LIVE_DATA.get(g_type, {}))

@app.route('/api/check_win/<period>')
def api_check_win(period):
    if 'user_id' not in session: return jsonify({"success": False})
    with get_db() as conn:
        wins = conn.execute("SELECT SUM(win_amount - amount) as profit FROM bets WHERE user_id=? AND period=? AND status='win'", (session['user_id'], period)).fetchone()
        if wins and wins['profit'] and wins['profit'] > 0:
            return jsonify({"success": True, "profit": round(wins['profit'], 2)})
    return jsonify({"success": False})

@app.route('/api/bet', methods=['POST'])
def api_bet():
    if 'user_id' not in session: return jsonify({"success": False, "msg": "未登录"})
    data = request.json
    g_type = data['game_type']
    if LIVE_DATA[g_type]['left_time'] <= GAMES[g_type]['close_sec']: return jsonify({"success": False, "msg": "已封盘"})
    
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        if user['status'] == 'banned': return jsonify({"success": False, "msg": "账号被封禁"})
        if user['balance'] < float(data['amount']): return jsonify({"success": False, "msg": "余额不足"})
        
        conn.execute("UPDATE users SET balance = balance - ? WHERE id=?", (data['amount'], session['user_id']))
        conn.execute('''INSERT INTO bets (user_id, game_type, period, bet_type, bet_value, amount, odds) VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                     (session['user_id'], g_type, LIVE_DATA[g_type]['next_period'], data['bet_type'], data['bet_value'], data['amount'], data['odds']))
        conn.execute("INSERT INTO messages (game_type, user_id, role, content) VALUES (?, ?, 'user', ?)", 
                     (g_type, session['user_id'], f"{data['bet_value']}:{data['amount']}"))
        conn.commit()
    return jsonify({"success": True, "msg": "下注成功"})

@app.route('/api/cancel_bet', methods=['POST'])
def api_cancel_bet():
    if 'user_id' not in session: return jsonify({"success": False, "msg": "未登录"})
    bet_id = request.json.get('bet_id')
    with get_db() as conn:
        bet = conn.execute("SELECT * FROM bets WHERE id=? AND user_id=?", (bet_id, session['user_id'])).fetchone()
        if not bet: return jsonify({"success": False, "msg": "注单不存在"})
        if bet['status'] != 'pending': return jsonify({"success": False, "msg": "已开奖，无法取消"})
        if LIVE_DATA[bet['game_type']]['left_time'] <= GAMES[bet['game_type']]['close_sec']:
            return jsonify({"success": False, "msg": "已封盘，禁止取消"})
            
        conn.execute("UPDATE bets SET status='cancel' WHERE id=?", (bet_id,))
        conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (bet['amount'], session['user_id']))
        conn.commit()
    return jsonify({"success": True, "msg": "取消成功，金额已退回"})

@app.route('/api/chat/<g_type>')
def api_chat(g_type):
    if 'user_id' not in session: return jsonify([])
    with get_db() as conn:
        msgs = conn.execute('''SELECT m.*, u.nickname, u.avatar FROM messages m LEFT JOIN users u ON m.user_id = u.id WHERE m.game_type=? ORDER BY m.id DESC LIMIT 40''', (g_type,)).fetchall()
    return jsonify([dict(m) for m in msgs])

@app.route('/api/my_bets')
def api_my_bets():
    if 'user_id' not in session: return jsonify([])
    with get_db() as conn:
        bets = conn.execute("SELECT * FROM bets WHERE user_id=? ORDER BY id DESC LIMIT 50", (session['user_id'],)).fetchall()
    return jsonify([dict(b) for b in bets])

@app.route('/api/request_money', methods=['POST'])
def api_request_money():
    if 'user_id' not in session: return jsonify({"success": False, "msg": "未登录"})
    data = request.json
    amt = float(data['amount'])
    if amt <= 0: return jsonify({"success": False, "msg": "金额必须大于0"})
    with get_db() as conn:
        if data['type'] == 'withdraw':
            user = conn.execute("SELECT balance FROM users WHERE id=?", (session['user_id'],)).fetchone()
            if user['balance'] < amt: return jsonify({"success": False, "msg": "余额不足"})
        conn.execute("INSERT INTO transactions (user_id, type, amount) VALUES (?, ?, ?)", (session['user_id'], data['type'], amt))
        conn.commit()
    return jsonify({"success": True, "msg": "申请已提交"})

@app.route('/api/change_pwd', methods=['POST'])
def api_change_pwd():
    if 'user_id' not in session: return jsonify({"success": False, "msg": "未登录"})
    data = request.json
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
        if user['password'] != data.get('old'): return jsonify({"success": False, "msg": "原密码错误"})
        conn.execute("UPDATE users SET password=? WHERE id=?", (data.get('new'), session['user_id']))
        conn.commit()
    return jsonify({"success": True, "msg": "密码修改成功"})

@app.route('/api/update_avatar', methods=['POST'])
def api_update_avatar():
    if 'user_id' not in session: return jsonify({"success": False})
    avatar = request.json.get('avatar')
    with get_db() as conn:
        conn.execute("UPDATE users SET avatar=? WHERE id=?", (avatar, session['user_id']))
        conn.commit()
    return jsonify({"success": True})

@app.route('/api/cs', methods=['GET', 'POST'])
def api_cs():
    if 'user_id' not in session: return jsonify({"success": False})
    uid = session['user_id']
    if request.method == 'POST':
        with get_db() as conn:
            conn.execute("INSERT INTO messages (game_type, user_id, role, content) VALUES ('CS', ?, 'user', ?)", (uid, request.json.get('content')))
            conn.commit()
        return jsonify({"success": True})
    with get_db() as conn:
        msgs = conn.execute("SELECT * FROM messages WHERE game_type='CS' AND user_id=? ORDER BY id DESC LIMIT 20", (uid,)).fetchall()
    return jsonify([dict(m) for m in msgs])

@app.route('/api/admin/cs_list')
def api_admin_cs_list():
    if session.get('role') != 'admin': return jsonify([])
    with get_db() as conn:
        users = conn.execute('''SELECT DISTINCT u.id, u.nickname FROM messages m JOIN users u ON m.user_id = u.id WHERE m.game_type='CS' ''').fetchall()
    return jsonify([dict(u) for u in users])

@app.route('/api/admin/cs_chat/<int:uid>', methods=['GET', 'POST'])
def api_admin_cs_chat(uid):
    if session.get('role') != 'admin': return jsonify({"success": False})
    if request.method == 'POST':
        with get_db() as conn:
            conn.execute("INSERT INTO messages (game_type, user_id, role, content) VALUES ('CS', ?, 'admin', ?)", (uid, request.json.get('content')))
            conn.commit()
        return jsonify({"success": True})
    with get_db() as conn:
        msgs = conn.execute("SELECT * FROM messages WHERE game_type='CS' AND user_id=? ORDER BY id DESC LIMIT 20", (uid,)).fetchall()
    return jsonify([dict(m) for m in msgs])

@app.route('/admin/backup')
def backup():
    if session.get('role') != 'admin': return "无权限"
    return send_file('captain28.db', as_attachment=True)

# ================== 页面路由 ==================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('username'), request.form.get('password')
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p)).fetchone()
            if user:
                if user['status'] == 'banned': return "<script>alert('该账号已被封禁！');history.back();</script>"
                session.permanent = True
                session.update({'user_id': user['id'], 'role': user['role'], 'username': user['username'], 'nickname': user['nickname'], 'avatar': user['avatar']})
                return redirect('/admin' if user['role'] == 'admin' else '/')
        return "<script>alert('账号或密码错误');history.back();</script>"
    return render_template_string(HTML_LOGIN)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u, nickname, p1, p2 = request.form.get('username'), request.form.get('nickname'), request.form.get('pwd1'), request.form.get('pwd2')
        if not re.match(r'^[A-Z0-9]+$', u): return "<script>alert('账号必须大写+数字！');history.back();</script>"
        if not re.match(r'^[\u4e00-\u9fa5]{2,5}$', nickname): return "<script>alert('昵称必须为2~5个中文！');history.back();</script>"
        if p1 != p2: return "<script>alert('密码不一致！');history.back();</script>"
        try:
            with get_db() as conn:
                if conn.execute("SELECT id FROM users WHERE nickname=?", (nickname,)).fetchone():
                    return "<script>alert('中文名已被使用！');history.back();</script>"
                conn.execute("INSERT INTO users (username, nickname, password, avatar) VALUES (?, ?, ?, ?)", (u, nickname, p1, f"https://api.dicebear.com/7.x/adventurer/svg?seed={u}"))
                conn.commit()
            return "<script>alert('注册成功');location.href='/login';</script>"
        except sqlite3.IntegrityError:
            return "<script>alert('账号已存在');history.back();</script>"
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
    return render_template_string(HTML_HOME, user=user, session=session)

@app.route('/game/<g_type>')
def game_page(g_type):
    if 'user_id' not in session or g_type not in GAMES: return redirect('/login')
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    return render_template_string(HTML_GAME, g_type=g_type, game_name=GAMES[g_type]['name'], user=user, session=session)

@app.route('/cs')
def client_cs_page():
    if 'user_id' not in session: return redirect('/login')
    return render_template_string(HTML_CLIENT_CS)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('role') != 'admin': return render_template_string(HTML_ADMIN_LOGIN)

    with get_db() as conn:
        if request.method == 'POST':
            act = request.form.get('act')
            if act == 'manual_money':
                uid, amt, m_type = request.form.get('uid'), float(request.form.get('amount')), request.form.get('m_type')
                if m_type == 'add': conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amt, uid))
                else: conn.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amt, uid))
            elif act == 'ban':
                conn.execute("UPDATE users SET status='banned' WHERE id=?", (request.form.get('uid'),))
            elif act == 'unban':
                conn.execute("UPDATE users SET status='normal' WHERE id=?", (request.form.get('uid'),))
            elif act == 'approve_tx':
                tx_id, action = request.form.get('tx_id'), request.form.get('action')
                tx = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
                if tx and tx['status'] == 'pending':
                    if action == 'approve':
                        if tx['type'] == 'deposit': conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (tx['amount'], tx['user_id']))
                        else: conn.execute("UPDATE users SET balance = balance - ? WHERE id=?", (tx['amount'], tx['user_id']))
                        conn.execute("UPDATE transactions SET status='approved' WHERE id=?", (tx_id,))
                    else: conn.execute("UPDATE transactions SET status='rejected' WHERE id=?", (tx_id,))
            conn.commit()

        users = conn.execute("SELECT * FROM users WHERE role != 'robot' ORDER BY id DESC LIMIT 100").fetchall()
        txs = conn.execute('''SELECT t.*, u.nickname FROM transactions t JOIN users u ON t.user_id = u.id WHERE t.status='pending' ORDER BY t.id DESC''').fetchall()
        
        robot_total = conn.execute("SELECT COUNT(*) FROM users WHERE role='robot'").fetchone()[0]
        robot_stats = []
        for g_type in ['2', '3', '13']:
            cnt = LIVE_DATA[g_type]['robot_count']
            robot_stats.append((GAMES[g_type]['name'], cnt))
            
    return render_template_string(HTML_ADMIN, users=users, txs=txs, session=session, robot_total=robot_total, robot_stats=robot_stats)

@app.route('/admin/chat/<int:uid>')
def admin_chat_page(uid):
    if session.get('role') != 'admin': return redirect('/login')
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not user: return "用户不存在"
    return render_template_string(HTML_ADMIN_CS, target_uid=uid, target_name=user['nickname'])

# ================== UI 模板 ==================
BASE_CSS = """
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap');
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Noto Sans SC', sans-serif; }
    body { background: #f4f7f9; color: #333; min-height: 100vh; padding-bottom: 60px; }
    .header { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; font-size: 16px; font-weight: 500; position: sticky; top: 0; z-index: 100; box-shadow: 0 4px 12px rgba(0,0,0,0.1);}
    .header a { color: #fff; text-decoration: none; }
    .container { padding: 15px; max-width: 600px; margin: 0 auto; }
    .card { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); border: 1px solid #eef2f5; }
    .input-group { margin-bottom: 20px; }
    .input-group input { width: 100%; padding: 14px 16px; border: 1px solid #dce2e8; border-radius: 8px; font-size: 16px; outline: none; transition: all 0.3s; background: #fcfdfd;}
    .input-group input:focus { border-color: #2a5298; box-shadow: 0 0 0 3px rgba(42,82,152,0.1); }
    .btn { width: 100%; padding: 15px; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; border: none; border-radius: 8px; font-size: 16px; font-weight: 700; cursor: pointer; box-shadow: 0 4px 10px rgba(42,82,152,0.2); transition: 0.3s; }
    .btn:active { transform: scale(0.98); }
    .btn-green { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); box-shadow: 0 4px 10px rgba(17,153,142,0.2); }
    .btn-red { background: linear-gradient(135deg, #cb2d3e 0%, #ef473a 100%); box-shadow: 0 4px 10px rgba(203,45,62,0.2); }
    .text-center { text-align: center; }
    .text-red { color: #ef473a; }
    .text-green { color: #11998e; }
    .text-blue { color: #2a5298; }
    .text-gray { color: #8898aa; }
    .avatar { width: 40px; height: 40px; border-radius: 50%; background: #eee; object-fit: cover; border: 2px solid #fff; box-shadow: 0 2px 5px rgba(0,0,0,0.1);}
    
    .tab-bar { position: fixed; bottom: 0; left: 0; width: 100%; height: 60px; background: #fff; border-top: 1px solid #eef2f5; display: flex; z-index: 500; box-shadow: 0 -2px 10px rgba(0,0,0,0.02);}
    .tab-item { flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; font-size: 12px; color: #8898aa; cursor: pointer; text-decoration: none; font-weight: 500;}
    .tab-item.active { color: #1e3c72; }
    .tab-item i { font-size: 20px; margin-bottom: 4px; }
    
    .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 2000; justify-content: center; align-items: center; }
    .modal-content { background: #fff; width: 90%; max-width: 400px; max-height: 80vh; border-radius: 12px; padding: 25px; overflow-y: auto; position: relative; }
    .close-modal { position: absolute; top: 15px; right: 20px; font-size: 20px; cursor: pointer; color: #8898aa; }
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
"""

HTML_LOGIN = BASE_CSS + """
<div class="header" style="justify-content: center;">舰长2.8 · 商务终端</div>
<div class="container" style="margin-top: 50px;">
    <div class="card">
        <h3 class="text-center" style="margin-bottom: 25px; color: #1e3c72; font-weight: 700;">安全登录</h3>
        <form method="POST">
            <div class="input-group"><input type="text" name="username" placeholder="请输入会员账号" required></div>
            <div class="input-group"><input type="password" name="password" placeholder="请输入密码" required></div>
            <button type="submit" class="btn">立即登录</button>
        </form>
        <div class="text-center" style="margin-top: 20px; font-size: 14px;">
            <a href="/register" class="text-blue" style="text-decoration: none;">没有账号？申请注册</a>
        </div>
    </div>
</div>
"""

HTML_ADMIN_LOGIN = BASE_CSS + """
<div class="header" style="justify-content: center; background: #111;">舰长2.8 · 管理后台</div>
<div class="container" style="margin-top: 50px;">
    <div class="card">
        <h3 class="text-center" style="margin-bottom: 25px; color: #111;">管理员登录</h3>
        <form method="POST" action="/login">
            <div class="input-group"><input type="text" name="username" placeholder="管理员账号" required></div>
            <div class="input-group"><input type="password" name="password" placeholder="管理员密码" required></div>
            <button type="submit" class="btn" style="background: #111;">进入后台</button>
        </form>
    </div>
</div>
"""

HTML_REGISTER = BASE_CSS + """
<div class="header" style="justify-content: center;">舰长2.8 · 商务终端</div>
<div class="container" style="margin-top: 30px;">
    <div class="card">
        <h3 class="text-center" style="margin-bottom: 20px; color: #1e3c72; font-weight: 700;">会员注册</h3>
        <form method="POST" onsubmit="return validateReg()">
            <div class="input-group"><input type="text" id="u" name="username" placeholder="账号 (大写字母+数字)" required></div>
            <div class="input-group"><input type="text" id="nick" name="nickname" placeholder="游戏昵称 (2~5个纯中文名)" required></div>
            <div class="input-group"><input type="password" id="p1" name="pwd1" placeholder="设置密码" required></div>
            <div class="input-group"><input type="password" id="p2" name="pwd2" placeholder="确认密码" required></div>
            <div class="input-group" style="display:flex; align-items:center; justify-content:space-between;">
                <input type="text" id="captcha-input" placeholder="验证码" required style="width: 55%;">
                <div id="captcha-box" onclick="drawCaptcha()" style="width: 40%; height: 50px; background:#fcfdfd; border:1px solid #dce2e8; border-radius:8px; display:flex; justify-content:center; align-items:center; font-size:22px; font-weight:bold; letter-spacing:5px; cursor:pointer; color:#2a5298; user-select:none;"></div>
            </div>
            <button type="submit" class="btn">立即注册</button>
        </form>
        <div class="text-center" style="margin-top: 15px; font-size: 14px;">
            <a href="/login" class="text-blue" style="text-decoration: none;">已有账号？返回登录</a>
        </div>
    </div>
</div>
<script>
    let currentCaptcha = "";
    function drawCaptcha() {
        let chars = "ABCDEFGHIJKLMNPQRSTUVWXYZ23456789"; currentCaptcha = "";
        for(let i=0; i<4; i++) currentCaptcha += chars[Math.floor(Math.random() * chars.length)];
        document.getElementById('captcha-box').innerText = currentCaptcha;
    }
    drawCaptcha();
    function validateReg() {
        let u = document.getElementById('u').value;
        if(!/^[A-Z0-9]+$/.test(u)) { alert("账号必须为大写字母+数字！"); return false; }
        let nick = document.getElementById('nick').value;
        if(!/^[\u4e00-\u9fa5]{2,5}$/.test(nick)) { alert("昵称必须为2~5个中文！"); return false; }
        if(document.getElementById('p1').value !== document.getElementById('p2').value) { alert("密码不一致！"); return false; }
        if(document.getElementById('captcha-input').value.toUpperCase() !== currentCaptcha) { alert("验证码错误！"); drawCaptcha(); return false; }
        return true;
    }
</script>
"""

HTML_HOME = BASE_CSS + """
<div class="header">
    <div style="display:flex; align-items:center; gap:10px;">
        <img src="{{ user.avatar }}" class="avatar" onclick="changeAvatar()">
        <div>
            <div style="font-size: 14px;">{{ user.nickname }}</div>
            <div style="font-size: 12px; color: rgba(255,255,255,0.7);">ID: {{ user.id }}</div>
        </div>
    </div>
    <div style="text-align: right;">
        <div style="font-size: 12px; color: rgba(255,255,255,0.7);">账户余额 (元)</div>
        <div style="font-size: 20px; font-weight: bold; color: #ffd700;">{{ user.balance }}</div>
    </div>
</div>
<div class="container">
    <div style="display:flex; gap:10px; margin-bottom:15px;">
        <button class="btn btn-green" onclick="requestMoney('deposit')">充值上分</button>
        <button class="btn btn-red" onclick="requestMoney('withdraw')">提现下分</button>
    </div>

    <div class="card" style="padding: 0; overflow: hidden;">
        <a href="/game/2" style="text-decoration: none; color: inherit; display: flex; align-items: center; padding: 20px; border-bottom: 1px solid #f0f0f0;">
            <div style="width: 50px; height: 50px; background: #e3f2fd; border-radius: 12px; display: flex; justify-content: center; align-items: center; font-size: 24px; color: #1976d2; margin-right: 15px;">🇨🇦</div>
            <div style="flex: 1;">
                <div style="font-size: 16px; font-weight: 700; color: #1e3c72;">加拿大28</div>
                <div style="font-size: 12px; color: #8898aa; margin-top: 4px;">极速开奖 · 官方认证</div>
            </div>
            <i class="fas fa-chevron-right text-gray"></i>
        </a>
        <a href="/game/3" style="text-decoration: none; color: inherit; display: flex; align-items: center; padding: 20px; border-bottom: 1px solid #f0f0f0;">
            <div style="width: 50px; height: 50px; background: #fff3e0; border-radius: 12px; display: flex; justify-content: center; align-items: center; font-size: 24px; color: #f57c00; margin-right: 15px;">⏱️</div>
            <div style="flex: 1;">
                <div style="font-size: 16px; font-weight: 700; color: #1e3c72;">分分28</div>
                <div style="font-size: 12px; color: #8898aa; margin-top: 4px;">高频暴击 · 极速体验</div>
            </div>
            <i class="fas fa-chevron-right text-gray"></i>
        </a>
        <a href="/game/13" style="text-decoration: none; color: inherit; display: flex; align-items: center; padding: 20px;">
            <div style="width: 50px; height: 50px; background: #e8f5e9; border-radius: 12px; display: flex; justify-content: center; align-items: center; font-size: 24px; color: #388e3c; margin-right: 15px;">₿</div>
            <div style="flex: 1;">
                <div style="font-size: 16px; font-weight: 700; color: #1e3c72;">比特28</div>
                <div style="font-size: 12px; color: #8898aa; margin-top: 4px;">全球行情 · 公平公正</div>
            </div>
            <i class="fas fa-chevron-right text-gray"></i>
        </a>
    </div>
</div>

<div class="tab-bar">
    <a href="/" class="tab-item active"><i class="fas fa-home"></i>大厅</a>
    <a href="/cs" class="tab-item"><i class="fas fa-headset"></i>客服</a>
    <a href="javascript:void(0)" onclick="openModal('modal-pwd')" class="tab-item"><i class="fas fa-user-shield"></i>设置</a>
    <a href="/logout" class="tab-item"><i class="fas fa-sign-out-alt"></i>退出</a>
</div>

<div id="modal-pwd" class="modal">
    <div class="modal-content">
        <span class="close-modal" onclick="closeModal('modal-pwd')">✖</span>
        <h3 style="text-align:center; margin-bottom:20px; color: #1e3c72;">安全设置</h3>
        <div class="input-group"><input type="password" id="old-pwd" placeholder="原密码"></div>
        <div class="input-group"><input type="password" id="new-pwd" placeholder="新密码"></div>
        <button class="btn" onclick="changePwd()">确认修改</button>
    </div>
</div>

<script>
function requestMoney(type) {
    let amt = prompt(type === 'deposit' ? "请输入充值金额:" : "请输入提现金额:");
    if(!amt || isNaN(amt) || Number(amt) <= 0) return;
    fetch('/api/request_money', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({type: type, amount: amt}) })
    .then(r=>r.json()).then(d=>alert(d.msg));
}
function changeAvatar() {
    let url = prompt("请输入头像图片链接(URL)，或直接点击取消使用随机头像:");
    if(url === null) url = "https://api.dicebear.com/7.x/adventurer/svg?seed=" + Math.random();
    fetch('/api/update_avatar', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({avatar: url}) }).then(()=>location.reload());
}
function openModal(id) { document.getElementById(id).style.display = 'flex'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }
function changePwd() {
    let o = document.getElementById('old-pwd').value, n = document.getElementById('new-pwd').value;
    if(!o || !n) return alert("不能为空");
    fetch('/api/change_pwd', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({old: o, new: n}) })
    .then(r=>r.json()).then(d=>{ alert(d.msg); if(d.success) location.href='/logout'; });
}
</script>
"""

HTML_GAME = BASE_CSS + """
<style>
    .game-header { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 10;}
    .game-header a { color: #fff; text-decoration: none; font-size: 20px; }
    .info-bar { background: #fff; padding: 15px; display: flex; justify-content: space-between; border-bottom: 1px solid #eef2f5; }
    .trend-box { background: #fff; padding: 10px 15px; display: flex; gap: 10px; overflow-x: auto; border-bottom: 1px solid #eef2f5; white-space: nowrap; }
    .trend-item { display: flex; flex-direction: column; align-items: center; font-size: 11px; min-width: 40px; }
    .trend-ball { width: 28px; height: 28px; border-radius: 50%; background: #2a5298; color: #fff; line-height: 28px; text-align: center; font-size: 13px; font-weight: bold; margin: 4px 0; box-shadow: 0 2px 5px rgba(42,82,152,0.3);}
    .trend-ball.red { background: #ef473a; box-shadow: 0 2px 5px rgba(239,71,58,0.3);}
    .trend-ball.blue { background: #5ac8fa; box-shadow: 0 2px 5px rgba(90,200,250,0.3);}
    .trend-attr { color: #8898aa; }
    
    .chat-area { background: #f4f7f9; height: 35vh; overflow-y: auto; padding: 15px; display: flex; flex-direction: column; gap: 15px; }
    .msg { display: flex; gap: 10px; font-size: 14px; align-items: flex-start;}
    .msg-avatar { width: 40px; height: 40px; border-radius: 50%; background: #fff; flex-shrink: 0; box-shadow: 0 2px 5px rgba(0,0,0,0.05);}
    .msg-content { display: flex; flex-direction: column; max-width: 75%; }
    .msg-name { font-size: 12px; color: #8898aa; margin-bottom: 4px; margin-left: 5px;}
    .msg-bubble { padding: 10px 14px; border-radius: 8px; border-top-left-radius: 2px; background: #fff; color: #333; font-size: 14px; box-shadow: 0 2px 5px rgba(0,0,0,0.03); line-height: 1.4;}
    
    .msg.me { flex-direction: row-reverse; }
    .msg.me .msg-content { align-items: flex-end; }
    .msg.me .msg-name { margin-right: 5px; margin-left: 0;}
    .msg.me .msg-bubble { border-top-left-radius: 8px; border-top-right-radius: 2px; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; box-shadow: 0 4px 10px rgba(42,82,152,0.2);}
    
    .msg.system { justify-content: center; }
    .msg.system .msg-bubble { background: rgba(0,0,0,0.05); color: #8898aa; font-size: 12px; border-radius: 20px; padding: 5px 15px; box-shadow: none;}
    
    .action-btns { display: flex; justify-content: space-around; background: #fff; padding: 12px 0; border-bottom: 1px solid #eef2f5; }
    .act-btn { font-size: 14px; color: #2a5298; cursor: pointer; text-decoration: none; font-weight: 500;}
    
    .bet-panel { background: #fff; padding: 15px; border-top: 1px solid #eef2f5; transition: 0.3s; }
    .bet-panel.locked { pointer-events: none; opacity: 0.6; }
    .input-bar { display: flex; gap: 10px; margin-bottom: 15px; }
    .input-bar input { flex: 1; padding: 12px; border: 1px solid #dce2e8; border-radius: 8px; font-size: 16px; outline: none; background: #fcfdfd;}
    
    .sum-scroll { display: flex; overflow-x: auto; white-space: nowrap; gap: 8px; margin-bottom: 15px; padding-bottom: 5px; }
    .sum-scroll::-webkit-scrollbar { height: 0; }
    .sum-item { min-width: 65px; background: #fff; border: 1px solid #dce2e8; border-radius: 8px; padding: 10px 0; text-align: center; cursor: pointer; display: flex; flex-direction: column; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.02);}
    .sum-item:active { background: #e3f2fd; border-color: #2a5298; }
    .sum-t { font-size: 18px; font-weight: bold; color: #1e3c72; }
    .sum-o { font-size: 11px; color: #8898aa; margin-top: 2px;}
    
    .kbd { display: flex; flex-direction: column; gap: 6px; }
    .kbd-row { display: flex; gap: 6px; }
    .k-btn { flex: 1; background: #fff; border: 1px solid #dce2e8; border-radius: 8px; padding: 10px 0; text-align: center; cursor: pointer; user-select: none; display: flex; flex-direction: column; justify-content: center; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.02);}
    .k-btn:active { background: #e3f2fd; border-color: #2a5298; }
    .k-t { font-size: 16px; font-weight: bold; color: #1e3c72; }
    .k-t.num { color: #2a5298; font-size: 20px; }
    .k-o { font-size: 11px; color: #8898aa; margin-top: 2px;}
    
    .k-gray { background: #f4f7f9; color: #8898aa; border-color: #dce2e8; }
    .k-gray .k-t { color: #8898aa; }
    .k-blue { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); border: none; box-shadow: 0 4px 10px rgba(42,82,152,0.3);}
    .k-blue .k-t { color: #fff; font-size: 18px; }

    /* 账单卡片样式完全还原截图 */
    .bill-card { background: #fff; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); overflow: hidden; }
    .bill-header { display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #f0f0f0; background: #fafafa;}
    .bill-title { display: flex; align-items: center; font-size: 16px; font-weight: bold; color: #333; }
    .bill-title::before { content: ''; display: inline-block; width: 4px; height: 16px; background: #00a2ff; border-radius: 2px; margin-right: 8px; }
    .bill-total { font-size: 16px; font-weight: bold; }
    .bill-body { padding: 15px; }
    .bill-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; font-size: 15px; border-bottom: 1px dashed #f0f0f0; }
    .bill-item:last-child { border-bottom: none; }
    .bill-item-left { color: #333; }
    .bill-item-right { font-weight: bold; }
    .bill-footer { display: flex; justify-content: space-between; padding: 12px 15px; background: #fafafa; font-size: 12px; color: #8898aa; border-top: 1px solid #f0f0f0;}
</style>

<div class="game-header">
    <a href="/">〈</a>
    <span>{{ game_name }}-2.8</span>
    <span style="font-size:14px;">余额: <span style="color:#ffd700; font-weight:bold;" id="top-balance">{{ user.balance }}</span></span>
</div>

<div class="info-bar">
    <div>
        <div style="font-size: 12px; color: #8898aa;">第 <span id="next-period">--</span> 期开奖</div>
        <div style="font-size: 18px; font-weight: bold; color: #1e3c72; margin-top: 6px;" id="status-box"><span id="status-text" style="background:#eef2f5; color:#8898aa; padding:4px 8px; border-radius:6px; font-size:12px;">加载中</span> <span id="cd-text" class="text-red" style="font-weight:bold;"></span></div>
    </div>
    <div style="text-align: right;">
        <div style="font-size: 12px; color: #8898aa;">第 <span id="cur-period">--</span> 期开奖</div>
        <div style="font-size: 18px; font-weight: bold; margin-top: 6px;">
            <span id="cur-nums">-</span> = <span id="cur-total" style="color: #2a5298;">-</span> <span id="cur-attr" style="font-size:14px; margin-left:5px; color: #8898aa;">-</span>
        </div>
    </div>
</div>

<div class="trend-box" id="trend-box"></div>

<div class="action-btns">
    <a href="javascript:void(0)" class="act-btn" onclick="openModal('modal-odds')"><i class="fas fa-book-open"></i> 赔率说明</a>
    <a href="javascript:void(0)" class="act-btn" onclick="fetchMyBets()"><i class="fas fa-file-invoice"></i> 我的账单</a>
</div>

<div class="chat-area" id="chat-box"></div>

<div class="bet-panel" id="bet-panel">
    <div class="input-bar">
        <input type="text" id="bet-input" placeholder="可点击下方键盘，也可直接打字输入 (如: 大:100)">
    </div>
    
    <div style="font-size:12px; color:#8898aa; margin-bottom:8px;">购买和值 (左右滑动查看更多)</div>
    <div class="sum-scroll" id="sum-scroll"></div>

    <div class="kbd">
        <div class="kbd-row">
            <div class="k-btn k-gray" onclick="cancelInput()"><span class="k-t">取消输入</span></div>
            <div class="k-btn" onclick="addBet('豹子', 88)"><span class="k-t">豹子</span><span class="k-o">88.00</span></div>
            <div class="k-btn" onclick="addBet('顺子', 16)"><span class="k-t">顺子</span><span class="k-o">16.00</span></div>
            <div class="k-btn" onclick="addBet('对子', 3.6)"><span class="k-t">对子</span><span class="k-o">3.60</span></div>
            <div class="k-btn k-gray" onclick="backspace()"><i class="fas fa-backspace"></i></div>
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
        <div class="kbd-row" style="margin-top:6px;">
            <div class="k-btn k-blue" onclick="submitBet()" style="flex: 3;"><span class="k-t">确认下注</span></div>
        </div>
    </div>
</div>

<div id="modal-odds" class="modal">
    <div class="modal-content">
        <span class="close-modal" onclick="closeModal('modal-odds')">✖</span>
        <h3 style="text-align:center; margin-bottom:20px; color: #1e3c72;">赔率说明</h3>
        <div style="font-size:14px; line-height:2; color:#555;">
            <p>💵0/27=960倍 | 1/26=320倍</p>
            <p>💵2/25=160倍 | 3/24=97倍</p>
            <p>💵4/23=64.5倍 | 5/22=46.5倍</p>
            <p>💵6/21=35倍 | 7/20=27.2倍</p>
            <p>💵8/19=22倍 | 9/18=18倍</p>
            <p>💵10/17=15.8倍 | 11/16=14.4倍</p>
            <p>💵12/15=13.6倍 | 13/14=13.3倍</p>
            <p style="margin-top:15px;">🈵大小单双=2.8倍</p>
            <p>🈵大单/小双 6.30倍</p>
            <p>🈵大双/小单 6.70倍</p>
            <p>⚠️遇13/14 对子 顺子 豹子中奖回本金</p>
            <p>🔶豹子88倍 | 🔷极值16倍</p>
            <p>🔶顺子16倍 | 🔷对子3.60倍</p>
            <p style="margin-top:20px; font-weight:bold; color:#ef473a; text-align:center;">最终解释权归舰长平台所有</p>
        </div>
    </div>
</div>

<div id="modal-bets" class="modal">
    <div class="modal-content" style="padding: 15px; background: #f4f7f9;">
        <span class="close-modal" onclick="closeModal('modal-bets')">✖</span>
        <h3 style="text-align:center; margin-bottom:15px; color: #1e3c72;">投注记录</h3>
        <div id="bets-list-container">
            <!-- 动态生成卡片 -->
        </div>
    </div>
</div>

<script>
    const G_TYPE = "{{ g_type }}"; let liveData = null; let currentBet = {};
    let lastCheckedPeriod = "";
    let currentDisplayedPeriod = "";
    
    const ODDS_MAP = {'0':960, '27':960, '1':320, '26':320, '2':160, '25':160, '3':97, '24':97, '4':64.5, '23':64.5, '5':46.5, '22':46.5, '6':35, '21':35, '7':27.2, '20':27.2, '8':22, '19':22, '9':18, '18':18, '10':15.8, '17':15.8, '11':14.4, '16':14.4, '12':13.6, '15':13.6, '13':13.3, '14':13.3};
    let sumHtml = '';
    for(let i=0; i<=27; i++) { sumHtml += `<div class="sum-item" onclick="addBet('${i}', ${ODDS_MAP[i]})"><span class="sum-t">${i}</span><span class="sum-o">${ODDS_MAP[i]}</span></div>`; }
    document.getElementById('sum-scroll').innerHTML = sumHtml;

    function openModal(id) { document.getElementById(id).style.display = 'flex'; }
    function closeModal(id) { document.getElementById(id).style.display = 'none'; }

    // 核心重构：极速获取并渲染账单，完全还原截图
    function fetchMyBets() {
        fetch('/api/my_bets').then(r=>r.json()).then(data => {
            let container = document.getElementById('bets-list-container'); container.innerHTML = '';
            if(data.length === 0) { container.innerHTML = '<div style="text-align:center; padding:20px; color:#8898aa;">暂无记录</div>'; return; }
            
            // 按期号分组
            let grouped = {};
            data.forEach(b => {
                if(!grouped[b.period]) grouped[b.period] = { period: b.period, time: b.created_at, items: [], profit: 0, game_name: "{{ game_name }}" };
                grouped[b.period].items.push(b);
                
                // 计算盈亏 (赢的纯利润 = win_amount - amount, 输的 = -amount, 待开奖/取消 = 0)
                if(b.status === 'win') grouped[b.period].profit += (b.win_amount - b.amount);
                else if(b.status === 'lose') grouped[b.period].profit -= b.amount;
            });
            
            // 按时间倒序渲染卡片
            Object.values(grouped).forEach(g => {
                let profitClass = g.profit > 0 ? 'text-green' : (g.profit < 0 ? 'text-red' : 'text-gray');
                let profitStr = g.profit > 0 ? `+${g.profit.toFixed(2)}` : (g.profit < 0 ? `${g.profit.toFixed(2)}` : '0.00');
                
                let itemsHtml = '';
                g.items.forEach(item => {
                    let itemProfit = 0;
                    if(item.status === 'win') itemProfit = item.win_amount - item.amount;
                    else if(item.status === 'lose') itemProfit = -item.amount;
                    
                    let subClass = itemProfit > 0 ? 'text-green' : (itemProfit < 0 ? 'text-red' : 'text-gray');
                    let subStr = itemProfit > 0 ? `+${itemProfit.toFixed(2)}` : (itemProfit < 0 ? `${itemProfit.toFixed(2)}` : '0.00');
                    
                    // 如果是 pending，显示取消按钮
                    let extraBtn = item.status === 'pending' ? `<button onclick="cancelBet(${item.id})" style="background:#ef473a; color:#fff; border:none; padding:2px 6px; border-radius:4px; font-size:11px; margin-left:10px;">取消</button>` : '';
                    
                    itemsHtml += `
                        <div class="bill-item">
                            <div class="bill-item-left">${item.bet_value}: ${item.amount.toFixed(2)} ${extraBtn}</div>
                            <div class="bill-item-right ${subClass}">${subStr}</div>
                        </div>
                    `;
                });
                
                let cardHtml = `
                    <div class="bill-card">
                        <div class="bill-header">
                            <div class="bill-title">${g.game_name}-2.8</div>
                            <div class="bill-total ${profitClass}">${profitStr}</div>
                        </div>
                        <div class="bill-body">${itemsHtml}</div>
                        <div class="bill-footer">
                            <div>${g.time.substring(0,19)}</div>
                            <div>期号: ${g.period}</div>
                        </div>
                    </div>
                `;
                container.innerHTML += cardHtml;
            });
            
            openModal('modal-bets');
        });
    }

    function cancelBet(id) {
        if(!confirm("确定要取消该注单吗？")) return;
        fetch('/api/cancel_bet', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({bet_id: id})
        }).then(r=>r.json()).then(d=>{
            alert(d.msg);
            if(d.success) { fetchMyBets(); fetchLive(); }
        });
    }

    // 极速结算与中奖检测
    function fetchLive() {
        fetch('/api/live/' + G_TYPE).then(r => r.json()).then(d => {
            // 核心逻辑：如果前端发现期号变了，说明上一期开奖了
            if(currentDisplayedPeriod !== "" && currentDisplayedPeriod !== d.period) {
                // 2秒内检测上一期是否中奖
                fetch('/api/check_win/' + currentDisplayedPeriod)
                .then(res=>res.json()).then(winData => {
                    if(winData.success) {
                        alert(`🎉 恭喜您中奖了！\n\n本期纯盈利：${winData.profit} 元`);
                    }
                    // 无论中不中奖，立刻刷新页面，更新最新余额
                    location.reload();
                });
            }
            
            currentDisplayedPeriod = d.period;
            liveData = d; 
            
            document.getElementById('next-period').innerText = d.next_period;
            document.getElementById('cur-period').innerText = d.period;
            if(d.nums && d.nums.length === 3) {
                document.getElementById('cur-nums').innerHTML = d.nums.map(n => `<span style="display:inline-block; width:26px; height:26px; line-height:26px; border-radius:50%; background:#2a5298; color:#fff; text-align:center; font-size:14px; margin:0 2px; box-shadow:0 2px 5px rgba(42,82,152,0.3);">${n}</span>`).join(' <span style="color:#8898aa; margin:0 2px;">+</span> ');
                document.getElementById('cur-total').innerText = d.total;
                let attr = d.total >= 14 ? '大' : '小'; attr += d.total % 2 === 0 ? '双' : '单';
                document.getElementById('cur-attr').innerText = attr;
            }
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
    
    setInterval(() => {
        if(!liveData || liveData.left_time === undefined) return;
        liveData.left_time -= 1; if(liveData.left_time < 0) liveData.left_time = 0;
        let leftDraw = liveData.left_time; let closeLimit = G_TYPE === '2' ? 30 : 5; let leftClose = leftDraw - closeLimit;
        let cdEl = document.getElementById('cd-text'); let panel = document.getElementById('bet-panel');
        let inp = document.getElementById('bet-input');
        
        if(leftClose > 0) {
            cdEl.innerText = leftClose + "秒封盘"; cdEl.style.color = "#ef473a"; panel.classList.remove('locked');
            if(inp.value === "封盘中禁止下注") { inp.value = ""; }
        } else {
            cdEl.innerText = "已封盘"; cdEl.style.color = "#8898aa"; panel.classList.add('locked');
            inp.value = "封盘中禁止下注";
        }
    }, 1000);
    
    function fetchChat() {
        fetch('/api/chat/' + G_TYPE).then(r => r.json()).then(msgs => {
            let box = document.getElementById('chat-box'); box.innerHTML = '';
            msgs.reverse().forEach(m => {
                let d = document.createElement('div');
                if(m.role === 'robot') {
                    d.className = 'msg';
                    d.innerHTML = `
                        <div style="width: 40px; height: 40px; border-radius: 50%; background: #00a2ff; color: #fff; display:flex; justify-content:center; align-items:center; font-size:20px; flex-shrink:0;"><i class="fas fa-robot"></i></div>
                        <div class="msg-content">
                            <div class="msg-name" style="color:#2a5298;">舰长机器人</div>
                            <div class="msg-bubble" style="background:#e6f2ff; color:#1e3c72; border-top-left-radius: 2px;">${m.content}</div>
                        </div>
                    `;
                } else if (m.role === 'admin') {
                    d.className = 'msg system';
                    d.innerHTML = `<div class="msg-bubble">[客服] ${m.content}</div>`;
                } else {
                    let isMe = (m.user_id === {{ session.user_id }});
                    d.className = isMe ? 'msg me' : 'msg';
                    d.innerHTML = `
                        <img src="${m.avatar}" class="msg-avatar">
                        <div class="msg-content">
                            <div class="msg-name">${m.nickname}</div>
                            <div class="msg-bubble">${m.content}</div>
                        </div>
                    `;
                }
                box.appendChild(d);
            });
            box.scrollTop = box.scrollHeight;
        });
    }
    setInterval(fetchChat, 2000); fetchChat();
    
    function addBet(key, odds) {
        if(liveData && liveData.left_time <= (G_TYPE==='2'?30:5)) return alert("已封盘，停止下注");
        let amount = prompt(`请输入下注【${key}】的金额:`, "10");
        if(!amount || isNaN(amount) || Number(amount) <= 0) return;
        let input = document.getElementById('bet-input'); let currentVal = input.value;
        if(currentVal.includes(key + ":")) return alert("请不要多次下注同一项，可修改金额后确认。");
        if(currentVal) input.value += " " + key + ":" + amount; else input.value = key + ":" + amount;
    }
    function backspace() { let input = document.getElementById('bet-input'); input.value = input.value.slice(0, -1); }
    function cancelInput() { document.getElementById('bet-input').value = ""; }
    
    function submitBet() {
        let inputVal = document.getElementById('bet-input').value.trim(); if(!inputVal) return alert("请先输入下注内容");
        let parts = inputVal.split(/\s+/); let promises = [];
        for(let part of parts) {
            let match = part.match(/([a-zA-Z\u4e00-\u9fa5]+|\d+)[:：](\d+(\.\d+)?)/);
            if(match) {
                let key = match[1]; let amt = parseFloat(match[2]);
                let type = 'num'; let odds = 0;
                if(!isNaN(key)) odds = ODDS_MAP[key] || 10;
                else if(['大','小'].includes(key)) { type='bs'; odds=2.8; }
                else if(['单','双'].includes(key)) { type='oe'; odds=2.8; }
                else if(key.length===2) { type='combo'; odds=key==='大单'||key==='小双'?6.3:6.7; }
                else { type='pattern'; odds= key==='豹子'?88:(key==='顺子'||key==='极大'||key==='极小'?16:3.6); }
                promises.push(fetch('/api/bet', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({game_type: G_TYPE, bet_type: type, bet_value: key, amount: amt, odds: odds}) }).then(r=>r.json()));
            }
        }
        if(promises.length === 0) return alert("下注格式错误，请使用如：大:100");
        Promise.all(promises).then(results => {
            if(results.every(r => r.success)) { 
                alert("🎉 下注成功！"); 
                document.getElementById('bet-input').value = ""; 
                fetchLive(); fetchChat(); 
            }
            else alert("部分下注失败，可能余额不足或已封盘");
        });
    }
</script>
"""

HTML_ADMIN = BASE_CSS + """
<style>
    .admin-tab-content { display: none; padding: 15px; max-width: 600px; margin: 0 auto; }
    .admin-tab-content.active { display: block; }
    .list-group { background: #fff; border-radius: 12px; overflow: hidden; margin-bottom: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); border: 1px solid #eef2f5;}
    .list-item { display: flex; justify-content: space-between; align-items: center; padding: 18px 20px; border-bottom: 1px solid #f4f7f9; font-size: 14px; text-decoration: none; color: inherit;}
    .list-item:last-child { border-bottom: none; }
    .list-item .info { flex: 1; }
    .list-item .title { font-weight: 700; color: #1e3c72; font-size: 15px; margin-bottom: 6px; }
    .list-item .desc { color: #8898aa; font-size: 12px; }
    .list-item .action { text-align: right; }
</style>

<div class="header" style="background:#111;">
    <span>管理后台</span>
    <div><a href="/logout">退出</a></div>
</div>

<div id="tab-users" class="admin-tab-content active">
    <div class="list-group" style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; border: none;">
        <div class="list-item" style="border: none; padding: 20px;">
            <div class="info">
                <div class="title" style="color: #fff; font-size: 18px;">🤖 机器人活跃系统</div>
                <div class="desc" style="color: rgba(255,255,255,0.7); margin-top: 8px;">机器总数: {{ robot_total }} 个</div>
                <div class="desc" style="color: rgba(255,255,255,0.7); margin-top: 4px;">
                    实时下注人数: 
                    {% for name, cnt in robot_stats %}
                        [{{ name }}: {{ cnt }}人] 
                    {% endfor %}
                </div>
            </div>
        </div>
    </div>

    <div class="list-group">
        <div class="list-item" style="background:#f4f7f9; font-weight:bold; color: #1e3c72;">充值/提现审批</div>
        {% if not txs %}
        <div class="list-item" style="color:#8898aa; justify-content:center;">暂无待审批流水</div>
        {% endif %}
        {% for t in txs %}
        <div class="list-item">
            <div class="info">
                <div class="title">{{ t.nickname }}</div>
                <div class="desc">{{ '申请充值' if t.type=='deposit' else '申请提现' }}: <span class="{{ 'text-green' if t.type=='deposit' else 'text-red' }}" style="font-weight:bold;">{{ t.amount }}</span></div>
            </div>
            <div class="action">
                <form method="POST" style="display:flex; gap:8px;">
                    <input type="hidden" name="act" value="approve_tx">
                    <input type="hidden" name="tx_id" value="{{ t.id }}">
                    <button type="submit" name="action" value="approve" style="background:#11998e; color:#fff; border:none; padding:8px 12px; border-radius:6px; font-weight:bold;">同意</button>
                    <button type="submit" name="action" value="reject" style="background:#ef473a; color:#fff; border:none; padding:8px 12px; border-radius:6px; font-weight:bold;">拒绝</button>
                </form>
            </div>
        </div>
        {% endfor %}
    </div>

    <div class="list-group">
        <div class="list-item" style="background:#f4f7f9; font-weight:bold; color: #1e3c72;">手动上分/扣款</div>
        <div class="list-item">
            <form method="POST" style="display:flex; flex-wrap:wrap; gap:8px; width:100%;">
                <input type="hidden" name="act" value="manual_money">
                <input type="number" name="uid" placeholder="用户ID" required style="padding:10px; border:1px solid #dce2e8; border-radius:8px; width:25%;">
                <input type="number" step="0.01" name="amount" placeholder="金额" required style="padding:10px; border:1px solid #dce2e8; border-radius:8px; width:35%;">
                <button type="submit" name="m_type" value="add" style="background:#11998e; color:#fff; border:none; padding:10px; border-radius:8px; flex:1; font-weight:bold;">充值</button>
                <button type="submit" name="m_type" value="sub" style="background:#ef473a; color:#fff; border:none; padding:10px; border-radius:8px; flex:1; font-weight:bold;">扣款</button>
            </form>
        </div>
    </div>

    <div class="list-group">
        <div class="list-item" style="background:#f4f7f9; font-weight:bold; color: #1e3c72;">真实注册用户 (前100名)</div>
        {% for u in users %}
        <div class="list-item">
            <div class="info">
                <div class="title">{{ u.nickname }} <span style="font-size:12px; font-weight:normal; color:#8898aa;">({{ u.username }})</span></div>
                <div class="desc">ID: {{ u.id }} | 余额: <span class="text-blue" style="font-weight:bold;">{{ u.balance }}</span></div>
            </div>
            <div class="action">
                <form method="POST">
                    <input type="hidden" name="uid" value="{{ u.id }}">
                    {% if u.status == 'banned' %}
                    <button type="submit" name="act" value="unban" style="background:#f4f7f9; color:#333; border:none; padding:8px 12px; border-radius:6px;">解除拉黑</button>
                    {% else %}
                    <button type="submit" name="act" value="ban" style="background:#ef473a; color:#fff; border:none; padding:8px 12px; border-radius:6px;">拉黑</button>
                    {% endif %}
                </form>
            </div>
        </div>
        {% endfor %}
    </div>
    
    <div style="text-align:center; margin-top:20px;">
        <a href="/admin/backup" style="display:inline-block; padding: 12px 25px; background:#1e3c72; color:#fff; text-decoration:none; border-radius:8px; font-weight:bold;"><i class="fas fa-download"></i> 紧急备份下载数据库</a>
    </div>
</div>

<div id="tab-cs" class="admin-tab-content">
    <div class="list-group" id="cs-user-list"></div>
</div>

<div class="tab-bar">
    <div class="tab-item active" onclick="switchTab('users', this)"><i class="fas fa-users"></i> 用户管理</div>
    <div class="tab-item" onclick="switchTab('cs', this)"><i class="fas fa-comments"></i> 客服消息</div>
</div>

<script>
    function switchTab(tabId, el) {
        document.querySelectorAll('.admin-tab-content').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.tab-item').forEach(el => el.classList.remove('active'));
        document.getElementById('tab-' + tabId).classList.add('active');
        el.classList.add('active');
        if(tabId === 'cs') fetchCSList();
    }
    function fetchCSList() {
        fetch('/api/admin/cs_list').then(r=>r.json()).then(users => {
            let box = document.getElementById('cs-user-list');
            if(users.length === 0) { box.innerHTML = '<div class="list-item" style="color:#8898aa; justify-content:center;">暂无客户消息</div>'; return; }
            box.innerHTML = users.map(u => `
                <a href="/admin/chat/${u.id}" class="list-item">
                    <div class="info">
                        <div class="title">${u.nickname}</div>
                        <div class="desc">ID: ${u.id}</div>
                    </div>
                    <div class="action" style="color:#2a5298; font-weight:bold;">进入聊天 ></div>
                </a>
            `).join('');
        });
    }
</script>
"""

# === 客户端独立聊天页面 ===
HTML_CLIENT_CS = BASE_CSS + """
<style>
    .chat-container { display: flex; flex-direction: column; height: 100vh; background: #f4f7f9; }
    .chat-header { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; padding: 15px 20px; display: flex; align-items: center; justify-content: space-between; font-size: 16px; font-weight: bold; }
    .chat-header a { color: #fff; text-decoration: none; font-size: 20px; }
    .chat-body { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
    .chat-footer { padding: 15px 20px; background: #fff; display: flex; gap: 10px; align-items: center; border-top: 1px solid #eef2f5; }
    .chat-footer input[type="text"] { flex: 1; border: 1px solid #dce2e8; padding: 12px 15px; border-radius: 20px; outline: none; font-size: 15px; background:#fcfdfd;}
    .btn-send { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; border: none; padding: 12px 25px; border-radius: 20px; font-weight: bold; font-size: 15px; box-shadow: 0 4px 10px rgba(42,82,152,0.2);}
    .msg-bubble { max-width: 80%; padding: 12px 16px; border-radius: 12px; font-size: 15px; word-break: break-all; line-height: 1.5;}
    .msg-me { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; align-self: flex-end; border-bottom-right-radius: 2px; box-shadow: 0 4px 10px rgba(42,82,152,0.2);}
    .msg-other { background: #fff; color: #333; align-self: flex-start; border-bottom-left-radius: 2px; box-shadow: 0 4px 10px rgba(0,0,0,0.03);}
</style>

<div class="chat-container">
    <div class="chat-header">
        <a href="/">〈</a>
        <span>联系在线客服</span>
        <span style="width:20px;"></span>
    </div>
    <div class="chat-body" id="cs-body"></div>
    <div class="chat-footer">
        <input type="file" id="cs-img" accept="image/*" style="display:none;" onchange="sendCSImg()">
        <label for="cs-img" style="padding:12px; background:#f4f7f9; border-radius:50%; cursor:pointer; font-size:20px; color:#2a5298;"><i class="fas fa-camera"></i></label>
        <input type="text" id="cs-input" placeholder="请描述您的问题...">
        <button class="btn-send" onclick="sendCSMsg()">发送</button>
    </div>
</div>

<script>
    function fetchCS() {
        fetch('/api/cs').then(r => r.json()).then(msgs => {
            let box = document.getElementById('cs-body'); box.innerHTML = '';
            if(!Array.isArray(msgs)) return;
            msgs.reverse().forEach(m => {
                let d = document.createElement('div');
                if(m.role === 'admin') d.className = 'msg-bubble msg-other'; 
                else d.className = 'msg-bubble msg-me';
                
                if(m.content.startsWith('data:image')) d.innerHTML = `<img src="${m.content}" style="max-width:100%; border-radius:8px;">`;
                else d.innerText = m.content;
                box.appendChild(d);
            });
            box.scrollTop = box.scrollHeight;
        });
    }
    setInterval(fetchCS, 3000); fetchCS();

    function sendCSMsg() {
        let val = document.getElementById('cs-input').value; if(!val) return;
        fetch('/api/cs', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content: val}) })
        .then(r=>r.json()).then(d=>{
            if(d.success) { document.getElementById('cs-input').value=''; fetchCS(); }
            else alert("发送失败: " + d.msg);
        }).catch(e => alert("网络错误"));
    }
    function sendCSImg() {
        let file = document.getElementById('cs-img').files[0]; if(!file) return;
        let reader = new FileReader();
        reader.onload = function(e) { 
            fetch('/api/cs', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content: e.target.result}) })
            .then(r=>r.json()).then(d=>{ if(d.success) fetchCS(); });
        };
        reader.readAsDataURL(file);
    }
</script>
"""

# === 客服端独立聊天页面 ===
HTML_ADMIN_CS = BASE_CSS + """
<style>
    .chat-container { display: flex; flex-direction: column; height: 100vh; background: #f4f7f9; }
    .chat-header { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; padding: 15px 20px; display: flex; align-items: center; justify-content: space-between; font-size: 16px; font-weight: bold; }
    .chat-header a { color: #fff; text-decoration: none; font-size: 20px; }
    .chat-body { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
    .chat-footer { padding: 15px 20px; background: #fff; display: flex; gap: 10px; align-items: center; border-top: 1px solid #eef2f5; }
    .chat-footer input[type="text"] { flex: 1; border: 1px solid #dce2e8; padding: 12px 15px; border-radius: 20px; outline: none; font-size: 15px; background:#fcfdfd;}
    .btn-send { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; border: none; padding: 12px 25px; border-radius: 20px; font-weight: bold; font-size: 15px; box-shadow: 0 4px 10px rgba(42,82,152,0.2);}
    .msg-bubble { max-width: 80%; padding: 12px 16px; border-radius: 12px; font-size: 15px; word-break: break-all; line-height: 1.5;}
    .msg-me { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; align-self: flex-end; border-bottom-right-radius: 2px; box-shadow: 0 4px 10px rgba(42,82,152,0.2);}
    .msg-other { background: #fff; color: #333; align-self: flex-start; border-bottom-left-radius: 2px; box-shadow: 0 4px 10px rgba(0,0,0,0.03);}
</style>

<div class="chat-container">
    <div class="chat-header">
        <a href="/admin">〈</a>
        <span>正在与 {{ target_name }} 聊天</span>
        <span style="width:20px;"></span>
    </div>
    <div class="chat-body" id="cs-body"></div>
    <div class="chat-footer">
        <input type="text" id="cs-input" placeholder="输入回复内容...">
        <button class="btn-send" onclick="sendCSMsg()">发送</button>
    </div>
</div>

<script>
    const TARGET_UID = {{ target_uid }};
    
    function fetchCS() {
        fetch('/api/admin/cs_chat/' + TARGET_UID).then(r => r.json()).then(msgs => {
            let box = document.getElementById('cs-body'); box.innerHTML = '';
            if(!Array.isArray(msgs)) return;
            msgs.reverse().forEach(m => {
                let d = document.createElement('div');
                if(m.role === 'admin') d.className = 'msg-bubble msg-me'; 
                else d.className = 'msg-bubble msg-other';
                
                if(m.content.startsWith('data:image')) d.innerHTML = `<img src="${m.content}" style="max-width:100%; border-radius:8px;">`;
                else d.innerText = m.content;
                box.appendChild(d);
            });
            box.scrollTop = box.scrollHeight;
        });
    }
    setInterval(fetchCS, 3000); fetchCS();

    function sendCSMsg() {
        let val = document.getElementById('cs-input').value; if(!val) return;
        fetch('/api/admin/cs_chat/' + TARGET_UID, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content: val}) })
        .then(r=>r.json()).then(d=>{
            if(d.success) { document.getElementById('cs-input').value=''; fetchCS(); }
            else alert("发送失败: " + d.msg);
        }).catch(e => alert("网络错误"));
    }
</script>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8888))
    app.run(host='0.0.0.0', port=port)
