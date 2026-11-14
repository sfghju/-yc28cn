import urllib.request
import ssl
import json
import time
import threading
import os
import sqlite3
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

# ================== 核心配置 ==================
SECRET_KEY = "deepseek_ai_pro_v7"
DEEPSEEK_API_KEY = "sk-43c18b39aeb346fc841937b30cade25b"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

# 全局状态
AI_STATUS = {"online": False, "msg": "等待连接"}
LIVE_DATA = {
    "2": {"period": "", "next": "", "left": 0, "history": [], "pred": None},
    "3": {"period": "", "next": "", "left": 0, "history": [], "pred": None},
    "13": {"period": "", "next": "", "left": 0, "history": [], "pred": None}
}

# ================== 数据库 ==================
def db():
    conn = sqlite3.connect('predict_v7.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT,
        kill TEXT, rec TEXT, analysis TEXT, real_result TEXT DEFAULT '',
        status TEXT DEFAULT 'wait'
    )''')
    conn.commit()

# ================== 赋予 AI 顶级精算师灵魂 ==================
def call_ai(gtype, game_name, history, next_period, last_status):
    # 构建真实数据矩阵
    history_str = "".join([f"第{7-i}期:{h['nums']}={h['total']}({h['big_small']}{h['odd_even']})\n" for i, h in enumerate(history[:7])])
    
    # 加入防连杀机制提示
    warning = ""
    if last_status == 'lose':
        warning = "【系统最高警报】：上一期我们预测失败（被庄家诱杀）。本期必须立刻切换策略，抛弃惯性思维，深度排查是否存在长龙诱多或极值反转！"
    elif last_status == 'win':
        warning = "【系统提示】：上期精准命中。请继续保持当前敏锐度，但切忌骄傲，重新审视当前走势。"

    # 核心系统级 Prompt (包含你要求的 20 大深度思考维度)
    prompt = f"""
    【身份设定】
    你现在是全球最顶尖的逆向博弈精算师、概率论大师。你绝不依赖运气，只相信深度博弈与反人性逻辑。
    
    【当前任务】
    游戏专区：{game_name}（注意：此游戏的走势逻辑完全独立，严禁套用其他游戏的数据！）
    预测目标：第 {next_period} 期
    {warning}
    
    【近7期实盘数据】
    {history_str}
    
    【核心指令】
    在给出最终预测前，你的底层逻辑必须进行以下 20 项深度思考推演（请在分析中体现出这些维度的博弈）：
    1. 连号惯性分析：大小或单双是否存在长龙？长龙是在延续还是在筑顶？
    2. 单跳双跳规律：是否出现大小交替或单双交替的固定节拍？
    3. 均值回归偏离：当前的冷热属性距离历史均值偏离了多少？
    4. 赌徒谬误陷阱：当前大众情绪是否在无脑追热或死磕冷门？
    5. 庄家诱盘逻辑：如果我是庄家，这一期怎么开最能收割市场？
    6. 资金筹码分布：大单/大双/小单/小双，哪一边的筹码最重、最危险？
    7. 极值反转信号：是否已经触发了物极必反的数学阈值？
    8. 波动率异动：近期和值波动是收敛还是发散？
    9. 形态对称性：当前走势图是否存在黄金分割或对称结构？
    10. 顺逆势取舍：这一期究竟该顺势跟随（骑龙），还是该果断反杀（屠龙）？
    11. 冷门补涨概率：连续未出的冷门属性是否积蓄了爆发力？
    12. 盘口情绪指数：通过当前走势，洞穿散户的恐慌与贪婪区间。
    13. 斐波那契周期：是否抵达了时间窗口的变盘节点？
    14. 暗盘防守真空：哪个选项目前被市场完全忽略，最容易爆冷？
    15. 阻力位与支撑位：历史开奖周期中的天然阻力区间在哪？
    16. 异常值偏离过滤：上一期的开奖是常态还是极端异常？
    17. 资金诱多洗盘：如果是你，如何利用惯性思维布局陷阱？
    18. 概率重置法则：独立随机事件在连续发生后，下一期的真实数学期望。
    19. 杀号容错率：挑选出的绝杀项，如果在极端情况下爆出，系统该如何防守？
    20. 三维交叉验证：大小、单双、和值，三个维度是否产生同向共振？
    
    【输出要求】
    1. 彻底摒弃套路化废话，必须像一个真正的人类精算师一样进行深度、硬核的逻辑推断。
    2. 从【大单、大双、小单、小双】中，果断绝杀掉 1 个（最不可能出的），并推荐防守另外 3 个。
    3. 生成 80 到 500 字的深度解析。分析中必须明确指出本期是采取“顺势”还是“反杀”，并引用近期的真实走势作为论据。
    4. 绝对禁止带有任何 markdown 格式，直接返回纯 JSON 字符串。
    
    返回格式：
    {{"kill":"大单", "rec":"大双、小单、小双", "analysis":"【AI核心博弈推演】...（这里写分析）"}}
    """
    
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一个顶级精算师，直接输出 JSON，绝对不要带 ```json 等标记。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.85, # 稍微调高一点，让它的逆向思维更活跃
        "max_tokens": 1000
    }
    
    try:
        req = urllib.request.Request(DEEPSEEK_API_URL, data=json.dumps(data).encode('utf-8'), headers=headers)
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            content = json.loads(resp.read().decode('utf-8'))['choices'][0]['message']['content']
            content = content.replace("```json", "").replace("```", "").strip()
            res = json.loads(content)
            
            AI_STATUS["online"] = True
            AI_STATUS["msg"] = "数据同步正常"
            
            with db() as conn:
                conn.execute('''INSERT INTO logs (gtype, period, kill, rec, analysis) VALUES (?,?,?,?,?)''', 
                             (gtype, next_period, res['kill'], res['rec'], res['analysis']))
                conn.commit()
                
            return {"kill": res['kill'], "rec": res['rec'], "analysis": res['analysis']}
    except Exception as e:
        AI_STATUS["online"] = False
        AI_STATUS["msg"] = f"AI 思考超时或解析失败"
        return None

# ================== 抓取与结算引擎 ==================
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
                            last_status = None
                            if LIVE_DATA[gt]['period'] != "":
                                real = latest['big_small'] + latest['odd_even']
                                with db() as conn:
                                    # 获取上期预测的状态
                                    prev_log = conn.execute("SELECT status FROM logs WHERE gtype=? AND period=?", (gt, latest['period'])).fetchone()
                                    if prev_log:
                                        last_status = prev_log['status']
                                    
                                    conn.execute("UPDATE logs SET real_result=?, status=? WHERE gtype=? AND period=? AND status='wait'",
                                                 (real, 'win' if real != LIVE_DATA[gt]['pred']['kill'] else 'lose', gt, latest['period']))
                                    conn.commit()
                            
                            dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            next_utc = dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])
                            
                            LIVE_DATA[gt].update({
                                "period": latest['period'], "next": str(int(latest['period'])+1),
                                "target_time": next_utc.timestamp(), "history": history
                            })
                            
                            AI_STATUS["online"] = True
                            AI_STATUS["msg"] = "AI 正在深度博弈中..."
                            print(f"🚀 正在请求 {cfg['name']} 精算分析...")
                            pred = call_ai(gt, cfg['name'], history, LIVE_DATA[gt]['next'], last_status)
                            if pred:
                                LIVE_DATA[gt]['pred'] = pred
                                
                        diff = LIVE_DATA[gt]['target_time'] - datetime.utcnow().timestamp()
                        LIVE_DATA[gt]['left'] = max(0, int(diff))
            except Exception:
                pass
        time.sleep(1)

threading.Thread(target=fetch_loop, daemon=True).start()

# ================== API 接口防护 ==================
def verify():
    return request.headers.get('X-Token') == SECRET_KEY

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

# ================== 前端渲染 ==================
@app.route('/')
def index():
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>AI 顶级精算预测</title>
    <style>
        body { background: #f4f6f9; margin: 0; font-family: -apple-system, sans-serif; color: #333; }
        .head { background: #111; color: #fff; padding: 16px; text-align: center; font-size: 20px; font-weight: bold; letter-spacing: 1px;}
        .status { text-align: center; padding: 10px; font-size: 13px; background: #fff; border-bottom: 1px solid #eaeaea; color: #666;}
        .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
        .on { background: #00b894; box-shadow: 0 0 5px #00b894;} .off { background: #d63031; }
        
        .tabs { display: flex; padding: 12px; gap: 10px; background: #fff; }
        .tab { flex: 1; padding: 10px; text-align: center; background: #f0f2f5; border-radius: 8px; font-weight: bold; font-size: 14px; cursor: pointer; transition: 0.2s;}
        .tab.on { background: #0984e3; color: #fff; box-shadow: 0 4px 10px rgba(9,132,227,0.3);}
        
        .card { background: #fff; margin: 12px; padding: 16px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }
        .title { font-size: 14px; color: #636e72; margin-bottom: 12px; font-weight: bold; display: flex; align-items: center;}
        .title::before { content: ''; display: inline-block; width: 4px; height: 14px; background: #0984e3; border-radius: 2px; margin-right: 8px;}
        
        .history { display: flex; overflow-x: auto; gap: 10px; font-size: 12px; text-align: center; padding-bottom: 5px; }
        .h-item { background: #f8f9fa; padding: 8px; border-radius: 8px; min-width: 65px; border: 1px solid #eee; }
        
        .kill { color: #d63031; font-size: 26px; font-weight: bold; text-align: center; margin: 15px 0; background: #fff5f5; padding: 10px; border-radius: 8px;}
        .rec { color: #00b894; font-size: 22px; font-weight: bold; text-align: center; margin-bottom: 15px; background: #f0fff4; padding: 10px; border-radius: 8px;}
        
        .cd-box { text-align: center; margin-bottom: 15px;}
        .cd { font-size: 22px; color: #0984e3; font-weight: bold; }
        .cd.danger { color: #d63031; animation: flash 0.5s infinite alternate;}
        @keyframes flash { 0% { opacity: 0.5; } 100% { opacity: 1; } }
        
        .ana { background: #f8f9fa; padding: 15px; border-left: 4px solid #0984e3; font-size: 14px; line-height: 1.7; border-radius: 4px; white-space: pre-wrap; color: #2d3436; }
        
        .log-item { border-bottom: 1px solid #f1f2f6; padding: 12px 0; font-size: 13px; display: flex; justify-content: space-between; }
        .log-item:last-child { border-bottom: none; }
        .win { color: #00b894; font-weight: bold; } .lose { color: #d63031; font-weight: bold; }
        .btn-clear { float:right; margin-top:-30px; font-size:12px; padding:6px 12px; border:1px solid #d63031; background:#fff; color:#d63031; border-radius:6px; font-weight: bold;}
    </style>
</head>
<body>
    <div class="head">AI 顶级精算预测中枢</div>
    <div class="status" id="status"><span class="dot off"></span> 连接数据中枢中...</div>
    
    <div class="tabs">
        <div class="tab on" onclick="switchG('2', this)">加拿大28</div>
        <div class="tab" onclick="switchG('3', this)">分分28</div>
        <div class="tab" onclick="switchG('13', this)">比特28</div>
    </div>

    <div class="card">
        <div class="title">近 20 期 独立盘面</div>
        <div class="history" id="history"></div>
    </div>

    <div class="card" id="pred-box" style="display:none">
        <div class="title">目标拦截期号: <span id="next-period" style="color:#0984e3; font-size:16px;"></span></div>
        <div class="kill">🚫 绝杀: <span id="kill-item"></span></div>
        <div class="rec">✅ 推荐防守: <span id="rec-item"></span></div>
        <div class="cd-box">距开奖结算: <span class="cd" id="cd">--:--</span></div>
        <div class="ana" id="ana">AI 正在进行 20 项深度逻辑推演...</div>
    </div>

    <div class="card">
        <div class="title">历史复盘记录 (带实开)</div>
        <button class="btn-clear" onclick="clearLogs()">清空记录</button>
        <div id="logs" style="margin-top:15px;"></div>
    </div>

<script>
    let curG = '2';
    let timer = null;
    const KEY = "deepseek_ai_pro_v7";

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
                hHtml += `<div class="h-item"><div style="color:#999; font-size:11px;">${h.nums.slice(0,5)}..</div><div style="color:#d63031; font-weight:bold; margin:3px 0;">${h.total}</div><div>${h.big_small}${h.odd_even}</div></div>`;
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
            let cdEl = document.getElementById('cd');
            cdEl.classList.remove('danger');
            
            timer = setInterval(() => {
                if(left <= 0) { cdEl.innerText = "结算中..."; cdEl.classList.add('danger'); return; }
                left--;
                let m = Math.floor(left / 60);
                let s = left % 60;
                cdEl.innerText = `${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
                
                if(left <= 10) cdEl.classList.add('danger');
                else cdEl.classList.remove('danger');
            }, 1000);
        });
    }

    function fetchLogs() {
        fetch(`/api/logs/${curG}`, { headers: {'X-Token': KEY} })
        .then(r => r.json()).then(data => {
            let html = '';
            data.forEach(l => {
                let cls = l.status === 'win' ? 'win' : (l.status === 'lose' ? 'lose' : '');
                let txt = l.status === 'win' ? '🀄 命中' : (l.status === 'lose' ? '💀 被杀' : '⏳ 等待');
                let real = l.real_result ? `(实开:${l.real_result})` : '';
                html += `<div class="log-item">
                    <div><div style="color:#888;">${l.period}</div><div style="margin-top:4px;">杀:<span class="lose">${l.kill}</span> | 推:<span class="win">${l.rec}</span></div></div>
                    <div style="text-align:right"><div class="${cls}">${txt}</div><div style="color:#888; font-size:12px; margin-top:4px;">${real}</div></div>
                </div>`;
            });
            document.getElementById('logs').innerHTML = html || '<div style="text-align:center; padding:20px; color:#999;">暂无记录</div>';
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
