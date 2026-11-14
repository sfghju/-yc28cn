import urllib.request
import ssl
import json
import time
import threading
import os
import re
import sqlite3
import hashlib
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime, timedelta

app = Flask(__name__)

# ================== 核心配置 ==================
SECRET_KEY = "deepseek_ai_v6"
DEEPSEEK_API_KEY = "sk-43c18b39aeb346fc841937b30cade25b"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

# 全局状态
AI_STATUS = {"online": False, "msg": "正在握手..."}
LIVE_DATA = {
    "2": {"period": "", "next": "", "time": 0, "history": [], "pred": None},
    "3": {"period": "", "next": "", "time": 0, "history": [], "pred": None},
    "13": {"period": "", "next": "", "time": 0, "history": [], "pred": None}
}

# ================== 数据库 ==================
def db():
    conn = sqlite3.connect('predict_v6.db', timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT,
        kill TEXT, rec TEXT, analysis TEXT, real_result TEXT DEFAULT '',
        status TEXT DEFAULT 'wait', time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()

# ================== 调教 DeepSeek AI ==================
def call_ai(gtype, game_name, history, next_period):
    history_str = "".join([f"第{7-i}期:{h['nums']}={h['total']}({h['big_small']}{h['odd_even']})\n" for i, h in enumerate(history[:7])])
    
    prompt = f"""
    你是顶级的逆向博弈精算师。当前游戏：{game_name}。目标期号：{next_period}。
    近7期走势如下：
    {history_str}
    
    请深度分析大小、单双趋势。从【大单、大双、小单、小双】中斩杀1个最危险的选项，推荐另外3个。给出80-500字的深度解析。
    严格输出纯JSON格式（不要带任何markdown标记）：
    {{"kill":"大单", "rec":"大双、小单、小双", "analysis":"【AI深度洞察】近期盘面呈现..."}}
    """
    
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    
    try:
        req = urllib.request.Request(DEEPSEEK_API_URL, data=json.dumps(data).encode('utf-8'), headers=headers)
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            content = json.loads(resp.read().decode('utf-8'))['choices'][0]['message']['content']
            content = content.replace("```json", "").replace("```", "").strip()
            res = json.loads(content)
            
            AI_STATUS["online"] = True
            AI_STATUS["msg"] = "AI 运算完成"
            
            with db() as conn:
                conn.execute('''INSERT INTO logs (gtype, period, kill, rec, analysis) VALUES (?,?,?,?,?)''', 
                             (gtype, next_period, res['kill'], res['rec'], res['analysis']))
                conn.commit()
                
            return {"kill": res['kill'], "rec": res['rec'], "analysis": res['analysis']}
    except Exception as e:
        AI_STATUS["online"] = False
        AI_STATUS["msg"] = f"接口异常: {str(e)}"
        return None

# ================== 抓取与结算 ==================
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
                        history = [{"nums": f"{i['num1']}+{i['num2']}+{i['num3']}", "total": i['total'], "big_small": i['big_small'], "odd_even": i['odd_even']} for i in data['data'][:20]]
                        
                        if LIVE_DATA[gt]['period'] != latest['period']:
                            if LIVE_DATA[gt]['period'] != "":
                                # 结算上期
                                real = latest['big_small'] + latest['odd_even']
                                with db() as conn:
                                    conn.execute("UPDATE logs SET real_result=?, status=? WHERE gtype=? AND period=? AND status='wait'",
                                                 (real, 'win' if real != LIVE_DATA[gt]['pred']['kill'] else 'lose', gt, latest['period']))
                                    conn.commit()
                            
                            # 计算时间
                            dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            next_utc = dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])
                            
                            LIVE_DATA[gt].update({
                                "period": latest['period'], "next": str(int(latest['period'])+1),
                                "time": next_utc.timestamp(), "history": history
                            })
                            
                            # 召唤 AI
                            AI_STATUS["online"] = True
                            AI_STATUS["msg"] = "AI 正在深度推演中..."
                            print(f"🚀 呼叫 AI 预测 {cfg['name']}...")
                            pred = call_ai(gt, cfg['name'], history, LIVE_DATA[gt]['next'])
                            if pred:
                                LIVE_DATA[gt]['pred'] = pred
                                
                        diff = LIVE_DATA[gt]['time'] - datetime.utcnow().timestamp()
                        LIVE_DATA[gt]['left'] = max(0, int(diff))
            except Exception:
                pass
        time.sleep(1)

threading.Thread(target=fetch_loop, daemon=True).start()

# ================== 接口防护 ==================
def verify():
    if request.headers.get('X-Token') != SECRET_KEY:
        return False
    return True

@app.route('/api/data/<gt>')
def api_data(gt):
    if not verify(): return "<h1>Access Denied</h1>", 403
    return jsonify({"status": AI_STATUS, "data": LIVE_DATA.get(gt, {})})

@app.route('/api/logs/<gt>')
def api_logs(gt):
    if not verify(): return "<h1>Access Denied</h1>", 403
    with db() as conn:
        logs = conn.execute("SELECT * FROM logs WHERE gtype=? ORDER BY id DESC LIMIT 30", (gt,)).fetchall()
    return jsonify([dict(l) for l in logs])

@app.route('/api/clear/<gt>', methods=['POST'])
def api_clear(gt):
    if not verify(): return jsonify({"ok": False})
    with db() as conn:
        conn.execute("DELETE FROM logs WHERE gtype=?", (gt,))
        conn.commit()
    return jsonify({"ok": True})

# ================== 页面渲染 ==================
@app.route('/')
def index():
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>DeepSeek AI 预测中枢</title>
    <style>
        body { background: #f0f2f5; margin: 0; font-family: sans-serif; color: #333; }
        .head { background: #000; color: #fff; padding: 15px; text-align: center; font-size: 20px; font-weight: bold; }
        .status { text-align: center; padding: 10px; font-size: 14px; background: #fff; border-bottom: 1px solid #ddd; }
        .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; }
        .on { background: #00b894; } .off { background: #d63031; }
        .tabs { display: flex; padding: 10px; gap: 10px; background: #fff; }
        .tab { flex: 1; padding: 10px; text-align: center; background: #eee; border-radius: 8px; font-weight: bold; cursor: pointer; }
        .tab.on { background: #0984e3; color: #fff; }
        .card { background: #fff; margin: 10px; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
        .title { font-size: 14px; color: #636e72; margin-bottom: 10px; font-weight: bold; }
        .history { display: flex; overflow-x: auto; gap: 10px; font-size: 12px; text-align: center; }
        .h-item { background: #f5f6fa; padding: 8px; border-radius: 8px; min-width: 60px; }
        .kill { color: #d63031; font-size: 24px; font-weight: bold; text-align: center; margin: 10px 0; }
        .rec { color: #00b894; font-size: 20px; font-weight: bold; text-align: center; margin-bottom: 15px; }
        .cd { text-align: center; font-size: 18px; color: #0984e3; font-weight: bold; margin-bottom: 15px; }
        .ana { background: #f5f6fa; padding: 15px; border-left: 4px solid #0984e3; font-size: 14px; line-height: 1.6; border-radius: 4px; white-space: pre-wrap; }
        .log-item { border-bottom: 1px solid #eee; padding: 10px 0; font-size: 13px; display: flex; justify-content: space-between; }
        .win { color: #00b894; } .lose { color: #d63031; }
    </style>
</head>
<body>
    <div class="head">DeepSeek AI 预测中枢</div>
    <div class="status" id="status"><span class="dot off"></span> 正在握手...</div>
    
    <div class="tabs">
        <div class="tab on" onclick="switchG('2', this)">加拿大28</div>
        <div class="tab" onclick="switchG('3', this)">分分28</div>
        <div class="tab" onclick="switchG('13', this)">比特28</div>
    </div>

    <div class="card">
        <div class="title">近期走势</div>
        <div class="history" id="history"></div>
    </div>

    <div class="card" id="pred-box" style="display:none">
        <div class="title">目标期号: <span id="next-period" style="color:#0984e3"></span></div>
        <div class="kill">🚫 绝杀: <span id="kill-item"></span></div>
        <div class="rec">✅ 推荐: <span id="rec-item"></span></div>
        <div class="cd">倒计时: <span id="cd">--:--</span></div>
        <div class="ana" id="ana"></div>
    </div>

    <div class="card">
        <div class="title">历史复盘记录 (带实开)</div>
        <button onclick="clearLogs()" style="float:right; margin-top:-30px; font-size:12px; padding:5px 10px; border:1px solid #d63031; background:#fff; color:#d63031; border-radius:5px;">清空</button>
        <div id="logs" style="margin-top:15px;"></div>
    </div>

<script>
    let curG = '2';
    let timer = null;
    const KEY = "deepseek_ai_v6";

    function switchG(g, el) {
        curG = g;
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
        el.classList.add('on');
        document.getElementById('pred-box').style.display = 'none';
        fetchData();
        fetchLogs();
    }

    function fetchData() {
        fetch(`/api/data/${curG}`, { headers: {'X-Token': KEY} })
        .then(r => r.json()).then(res => {
            let st = document.getElementById('status');
            if(res.status.online) {
                st.innerHTML = `<span class="dot on"></span> ${res.status.msg}`;
            } else {
                st.innerHTML = `<span class="dot off"></span> ${res.status.msg}`;
            }

            let d = res.data;
            if(!d.period) return;

            let hHtml = '';
            d.history.slice(0, 10).forEach(h => {
                hHtml += `<div class="h-item"><div>${h.nums}</div><div style="color:#d63031">${h.total}</div><div>${h.big_small}${h.odd_even}</div></div>`;
            });
            document.getElementById('history').innerHTML = hHtml;

            if(d.pred) {
                document.getElementById('pred-box').style.display = 'block';
                document.getElementById('next-period').innerText = d.next;
                document.getElementById('kill-item').innerText = d.pred.kill;
                document.getElementById('rec-item').innerText = d.pred.rec;
                document.getElementById('ana').innerText = d.pred.analysis;
            }

            if(timer) clearInterval(timer);
            let left = d.left || 0;
            timer = setInterval(() => {
                if(left <= 0) { document.getElementById('cd').innerText = "结算中"; return; }
                left--;
                let m = Math.floor(left / 60);
                let s = left % 60;
                document.getElementById('cd').innerText = `${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
            }, 1000);
        });
    }

    function fetchLogs() {
        fetch(`/api/logs/${curG}`, { headers: {'X-Token': KEY} })
        .then(r => r.json()).then(data => {
            let html = '';
            data.forEach(l => {
                let cls = l.status === 'win' ? 'win' : (l.status === 'lose' ? 'lose' : '');
                let txt = l.status === 'win' ? '命中' : (l.status === 'lose' ? '被杀' : '等待');
                let real = l.real_result ? `(实开:${l.real_result})` : '';
                html += `<div class="log-item">
                    <div><div style="color:#666">${l.period}</div><div>杀:<span class="lose">${l.kill}</span> 推:<span class="win">${l.rec}</span></div></div>
                    <div style="text-align:right"><div class="${cls}">${txt}</div><div style="color:#999; font-size:12px">${real}</div></div>
                </div>`;
            });
            document.getElementById('logs').innerHTML = html || '暂无记录';
        });
    }

    function clearLogs() {
        if(!confirm("确定清空记录吗？")) return;
        fetch(`/api/clear/${curG}`, { method: 'POST', headers: {'X-Token': KEY} })
        .then(r => r.json()).then(() => fetchLogs());
    }

    fetchData();
    fetchLogs();
    setInterval(fetchData, 2000);
    setInterval(fetchLogs, 5000);
</script>
</body>
</html>
    """

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8888))
    app.run(host='0.0.0.0', port=port)
