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
SECRET_KEY = "deepseek_ai_pro_v8"
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
    conn = sqlite3.connect('predict_v8.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT,
        kill TEXT, rec TEXT, analysis TEXT, real_result TEXT DEFAULT '',
        status TEXT DEFAULT 'wait'
    )''')
    conn.commit()

# ================== AI 核心推演引擎 (50项深度任务) ==================
def call_ai(gtype, game_name, history, next_period, last_status):
    # 提取近7期数据
    history_str = "".join([f"第{7-i}期:{h['nums']}={h['total']}({h['big_small']}{h['odd_even']})\n" for i, h in enumerate(history[:7])])
    
    # 计算基础连号特征 (辅助AI)
    bs_seq = [h['big_small'] for h in history[:7]]
    oe_seq = [h['odd_even'] for h in history[:7]]
    bs_streak = 1
    for i in range(1, len(bs_seq)):
        if bs_seq[i] == bs_seq[0]: bs_streak += 1
        else: break
    oe_streak = 1
    for i in range(1, len(oe_seq)):
        if oe_seq[i] == oe_seq[0]: oe_streak += 1
        else: break

    streak_info = f"当前【大小】连开{bs_streak}期，【单双】连开{oe_streak}期。"
    rule_hint = ""
    if bs_streak >= 5 or oe_streak >= 5:
        rule_hint = "【铁律】连开5期以上，极易走长龙，必须顺势跟，切莫无脑反杀，防回马枪诱空！"
    else:
        rule_hint = "【铁律】未达5连，重点关注冷热回补，反向杀掉热号，防庄家虚假繁荣回马枪。"

    warning = ""
    if last_status == 'lose':
        warning = "【最高警报】：上期预测失败，本期必须立刻变阵，打破惯性思维，深度排查长龙诱多！"
    elif last_status == 'win':
        warning = "【状态提示】：上期精准命中，保持状态，稳扎稳打。"

    # 严格遵循 50 个深度任务
    prompt = f"""
    【身份设定】
    你是全球最顶尖的逆向博弈精算师。你的胜率极高，因为你不仅懂数学，更懂人性的弱点与庄家的底牌。现在，只为你提供绝对独立、没有其他游戏干扰的盘口数据。

    【当前盘口】
    游戏专区：{game_name} (与其他游戏毫无关联)
    目标期号：{next_period}
    {warning}
    
    【近期实盘走势】
    {history_str}
    {streak_info}
    {rule_hint}

    【50项核心深度推演任务】
    在给出结论前，你必须在内部完成以下50项高维思考：
    1. 连号极值与断裂点：大小或单双是否存在连号？连几期了？
    2. 长龙跟随与回马枪：大于等于5连时，庄家是否在诱空？我们能否安全骑龙？
    3. 单跳双跳节拍：是否出现规律性的单跳或双跳？
    4. 均值回归与极值：当前冷热属性偏离历史均值多少？
    5. 赌徒谬误陷阱：大众是否在死磕冷门？
    6. 诱多与诱空：庄家当前的开奖在引诱买大还是买小？
    7. 筹码分布：大单、大双、小单、小双，哪边筹码最重（最危险）？
    8. 虚假繁荣：近期的热度是否是刻意营造的假象？
    9. 时间窗口共振：当前期号是否在江恩或斐波那契变盘节点？
    10. 顺逆势抉择：本轮究竟该跟还是反？
    11. 振幅收敛：近期和值波动是变大还是变小？
    12. 极端变异阈值：是否触及了物极必反的临界点？
    13. 静默冷门：哪个选项很久没出，已积蓄爆发力？
    14. 散户口袋：散户最习惯追什么号？我们要避开。
    15. 大小单双的撕裂感：大小与单双是否产生矛盾？
    16. 庄家洗盘周期：最近是否有洗盘动作？
    17. 回马枪概率：如果杀掉热门，冷门接棒的概率有多高？
    18. 独立随机期望：纯数学角度，下一期的最大概率项。
    19. 容错率评估：如果绝杀项爆冷，系统能否兜底？
    20. 三维共振验证：大小、单双、和值，是否指向同一方向？
    21. 盘口情绪指数：贪婪还是恐慌？
    22. 惯性陷阱：由于惯性，大众会怎么买？
    23. 破位风险：热号是否会在此刻破位？
    24. 区间震荡率：是否还在此前的震荡区间内？
    25. 诱盘深度：庄家为了收割，会怎么走？
    26. 下探支撑位：热号如果下跌，底在哪？
    27. 上攻阻力位：冷号如果反弹，顶在哪？
    28. 异动信号：突然的连号是否意味着趋势反转？
    29. 死亡螺旋：如果继续反杀，会不会连败？
    30. 连胜保护：上期赢了，这期是否该保守？
    31. 形态学分析：K线形态是否出现吞没或反转信号？
    32. 资金流向模拟：哪边有大资金默默入场？
    33. 散户跟风系数：散户最爱跟哪边？
    34. 极限施压：如果连开6期，还敢不敢反？
    35. 周期共振：是否与某个特定的开奖时间周期重合？
    36. 遗漏值修正：近期的冷门是否已到达遗漏极限？
    37. 多空双杀：庄家是否会选择一种两边通杀的结局？
    38. 假突破：当前的走势是不是在假突破诱多？
    39. 盘口重力：热号自然回落的引力有多大？
    40. 核心博弈点：本期庄家与散户的核心分歧在哪？
    41. 概率重置：独立事件在连续发生后，真实概率是多少？
    42. 情绪冰点：散户是否有绝望情绪？
    43. 诱敌深入：是否需要先顺一手再反杀？
    44. 历史回测：类似当前形态，历史上是怎么开的？
    45. 盘面强弱：大/小，单/双，谁更强？
    46. 变盘节点：时间上是否到了该变的时候？
    47. 庄家底牌：剥开伪装，庄家真实意图是什么？
    48. 反人性操作：大众都看好什么，我们就杀什么？
    49. 防守纵深：推荐的三项是否足够安全？
    50. 一击必杀：经过所有推演，最终锁定的唯一绝杀项是谁？

    【输出指令】
    1. 必须结合上述逻辑，进行字数 100 - 500 字的极度硬核分析，直接指出“是跟随还是反杀”以及“为何要防回马枪”。
    2. 必须从【大单、大双、小单、小双】中斩杀 1 个，推荐另外 3 个。
    3. 纯 JSON 格式（千万别带 ```json），格式如下：
    {{"kill":"大单", "rec":"大双、小单、小双", "analysis":"【精算推演】当前盘口呈现...（你的深度分析）"}}
    """
    
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一个顶级精算师，直接输出 JSON，绝对不要带 ```json 等标记。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.75,
        "max_tokens": 1200
    }
    
    try:
        req = urllib.request.Request(DEEPSEEK_API_URL, data=json.dumps(data).encode('utf-8'), headers=headers)
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            content = json.loads(resp.read().decode('utf-8'))['choices'][0]['message']['content']
            content = content.replace("```json", "").replace("```", "").strip()
            res = json.loads(content)
            
            AI_STATUS["online"] = True
            AI_STATUS["msg"] = "算力充沛 · 深度推演完成"
            
            with db() as conn:
                conn.execute('''INSERT INTO logs (gtype, period, kill, rec, analysis) VALUES (?,?,?,?,?)''', 
                             (gtype, next_period, res['kill'], res['rec'], res['analysis']))
                conn.commit()
                
            return {"kill": res['kill'], "rec": res['rec'], "analysis": res['analysis']}
    except Exception as e:
        AI_STATUS["online"] = False
        AI_STATUS["msg"] = f"解析失败或接口超时"
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
        <div class="ana" id="ana">AI 正在进行 50 项深度逻辑推演...</div>
    </div>

    <div class="card">
        <div class="title">历史复盘记录 (带实开)</div>
        <button class="btn-clear" onclick="clearLogs()">清空记录</button>
        <div id="logs" style="margin-top:15px;"></div>
    </div>

<script>
    let curG = '2';
    let timer = null;
    const KEY = "deepseek_ai_pro_v8";

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
