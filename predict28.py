import urllib.request
import ssl
import json
import time
import threading
import os
import sqlite3
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
SECRET_KEY = "ultimate_ai_flash_v3"

# ================== DeepSeek 核心配置 ==================
DEEPSEEK_API_KEY = "sk-43c18b39aeb346fc841937b30cade25b"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

AI_STATUS = {"online": False, "msg": "等待连接 AI 核心..."}
LIVE_DATA = {
    "2": {"period": "", "next": "", "left": 0, "history": [], "pred": None},
    "3": {"period": "", "next": "", "left": 0, "history": [], "pred": None},
    "13": {"period": "", "next": "", "left": 0, "history": [], "pred": None}
}

# 线程池执行器，保障10秒内极速响应
executor = ThreadPoolExecutor(max_workers=5)

# ================== 数据库 ==================
def db():
    conn = sqlite3.connect('predict_ai_flash.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT,
        kill TEXT, rec TEXT, analysis TEXT, real_result TEXT DEFAULT '',
        status TEXT DEFAULT 'wait'
    )''')
    conn.commit()

# ================== 极速 AI 预测引擎 ==================
def call_deepseek_ai(game_name, history, next_period):
    # 严格只截取近 7 期数据
    history_text = ""
    for i, h in enumerate(history[:7]):
        history_text += f"期号{next_period}-{i+1}: {h['nums']} = {h['total']} ({h['big_small']}{h['odd_even']})\n"

    prompt = f"""
    【系统指令】
    你是一个顶级的数字盘口博弈论专家与量化推演模型。当前游戏：【{game_name}】 目标期号：【{next_period}】
    近 7 期真实盘面数据如下：
    {history_text}

    【50项极度严苛的推演目标（必须逐一在后台逻辑中计算，并体现在最终分析中）】
    1. 频次偏态分析；2. 大小极值判定；3. 单双极值判定；4. 连号断裂概率；5. 交叉共振频率；
    6. 近期形态属性；7. 回马枪战术识别；8. 均值回归引力；9. 散户跟风系数；10. 和值振幅中枢；
    11. 高位逼空陷阱；12. 奇偶失衡修复；13. 同形态回测；14. 虚假繁荣剥离；15. 动能衰减前兆；
    16. 筹码分布风险；17. 情绪指数逆向；18. 极冷爆发潜伏；19. 极热必死概率；20. 斐波那契变盘；
    21. 虚拟均线阻力；22. 指标钝化现象；23. 强弱超买超卖；24. 布林带收口扩张；25. 周期嵌套分析；
    26. 假突破识别；27. 连败阻断策略；28. 连胜防守纵深；29. 混沌分形特征；30. 贝叶斯概率更新；
    31. 泊松分布测算；32. 马尔可夫转移；33. 蒙特卡洛模拟；34. 卡方拟合度；35. 协整均值极限；
    36. 波动率微笑极值；37. 长程相关性；38. 遗传算法寻优；39. 强化学习奖惩；40. 羊群效应极点；
    41. 锚定预期偏差；42. 损失厌恶阻断；43. 赌徒谬误排查；44. 冷热手效应反转；45. 过度反应纠错；
    46. 认知失调破解；47. 代表性偏差过滤；48. 禀赋效应冲击；49. 多空双杀防范；50. 绝对安全垫构建。

    【预测规则】
    1. 基于上述 50 个目标的极限推演，直接输出最精准的预测结果，不需写出具体计算过程。
    2. 必须在【大单、大双、小单、小双】四个选项中：
       - 斩杀 1 个（绝杀）
       - 推荐 3 个作为防守组合，分别标注为：【主攻】、【防守】、【备选】。
    3. 必须写一段 150 - 500 字的深度推演分析（不包含标点符号）。字数必须严格控制在这个区间内！分析要犀利，且必须结合近 7 期的具体期号和开奖结果。
    4. 绝不能包含任何 Markdown 标记，必须返回纯 JSON 格式：

    {{
        "kill": "大单",
        "main": "大双",
        "defend": "小单",
        "backup": "小双",
        "analysis": "此处填入150-500字的深度分析..."
    }}
    """

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 开启深度思考模式（deepseek-flash + thinking: enabled + reasoning_effort: high）
    data = {
        "model": "deepseek-flash",
        "messages": [
            {"role": "system", "content": "你是AI预测机器，只输出纯JSON字符串，绝不带任何Markdown格式（如```json）。"},
            {"role": "user", "content": prompt}
        ],
        "reasoning_effort": "high",
        "max_tokens": 2500,
        "response_format": {"type": "json_object"},
        "extra_body": {"thinking": {"type": "enabled"}}
    }

    try:
        req = urllib.request.Request(DEEPSEEK_API_URL, data=json.dumps(data).encode('utf-8'), headers=headers)
        ctx = ssl._create_unverified_context()
        
        # 将超时严格卡在 9.5 秒内，配合线程池实现开奖后10秒内响应
        with urllib.request.urlopen(req, timeout=9.5, context=ctx) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            content = res_data['choices'][0]['message']['content']
            parsed = json.loads(content)
            
            rec_str = f"{parsed['main']}(主攻)、{parsed['defend']}(防守)、{parsed['backup']}(备选)"
            
            AI_STATUS["online"] = True
            AI_STATUS["msg"] = "DeepSeek-Flash 深度思考完成"
            
            return {
                "kill": parsed['kill'],
                "rec": rec_str,
                "analysis": parsed['analysis']
            }
    except TimeoutError:
        print("AI Error: 请求超时（超过9.5秒）")
        AI_STATUS["online"] = False
        AI_STATUS["msg"] = "AI 响应超时"
        return None
    except Exception as e:
        print(f"AI Error: {e}")
        AI_STATUS["online"] = False
        AI_STATUS["msg"] = "AI 接口异常"
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
                        history = [{"period": i['period'], "nums": f"{i['num1']} + {i['num2']} + {i['num3']}", "total": i['total'], "big_small": i['big_small'], "odd_even": i['odd_even']} for i in data['data'][:20]]
                        
                        if LIVE_DATA[gt]['period'] != latest['period']:
                            # 结算上一期
                            if LIVE_DATA[gt]['period'] != "" and LIVE_DATA[gt]['pred'] is not None:
                                real = latest['big_small'] + latest['odd_even']
                                with db() as conn:
                                    if real != LIVE_DATA[gt]['pred']['kill']:
                                        conn.execute("UPDATE logs SET real_result=?, status='win' WHERE gtype=? AND period=? AND status='wait'", (real, gt, latest['period']))
                                    else:
                                        conn.execute("UPDATE logs SET real_result=?, status='lose' WHERE gtype=? AND period=? AND status='wait'", (real, gt, latest['period']))
                                    conn.commit()
                            
                            dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            next_utc = dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])
                            
                            LIVE_DATA[gt].update({
                                "period": latest['period'], "next": str(int(latest['period'])+1),
                                "target_time": next_utc.timestamp(), "history": history
                            })
                            
                            AI_STATUS["msg"] = "DeepSeek-Flash 极速思考中..."
                            AI_STATUS["online"] = True
                            
                            print(f"🚀 请求 DeepSeek-Flash 分析 {cfg['name']} 第 {LIVE_DATA[gt]['next']} 期 (近7期数据)...")
                            
                            # 使用线程池非阻塞提交，配合 9.5 秒超时
                            future = executor.submit(call_deepseek_ai, cfg['name'], history, LIVE_DATA[gt]['next'])
                            try:
                                pred = future.result(timeout=9.5)
                            except TimeoutError:
                                pred = None
                                AI_STATUS["online"] = False
                                AI_STATUS["msg"] = "AI 响应超时"
                            
                            if pred:
                                LIVE_DATA[gt]['pred'] = pred
                                with db() as conn:
                                    conn.execute('''INSERT INTO logs (gtype, period, kill, rec, analysis) VALUES (?,?,?,?,?)''', 
                                                 (gt, LIVE_DATA[gt]['next'], pred['kill'], pred['rec'], pred['analysis']))
                                    conn.commit()
                                
                        diff = LIVE_DATA[gt]['target_time'] - datetime.utcnow().timestamp()
                        LIVE_DATA[gt]['left'] = max(0, int(diff))
            except Exception:
                pass
        time.sleep(1)

threading.Thread(target=fetch_loop, daemon=True).start()

# ================== API 接口 ==================
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
        logs = conn.execute("SELECT * FROM logs WHERE gtype=? ORDER BY id DESC", (gt,)).fetchall()
        stats = {"current_win": 0, "current_lose": 0, "total_win": 0, "total_lose": 0}
        settled = [l['status'] for l in logs if l['status'] in ('win', 'lose')]
        for st in settled:
            if st == 'win': stats['total_win'] += 1
            elif st == 'lose': stats['total_lose'] += 1
        for st in settled:
            if st == 'win': 
                if stats['current_lose'] > 0: break 
                stats['current_win'] += 1
            elif st == 'lose':
                if stats['current_win'] > 0: break
                stats['current_lose'] += 1
    return jsonify({"logs": [dict(l) for l in logs], "stats": stats})

@app.route('/api/clear/<gt>', methods=['POST'])
def api_clear(gt):
    if not verify(): return jsonify({"ok": False})
    with db() as conn:
        conn.execute("DELETE FROM logs WHERE gtype=?", (gt,))
        conn.commit()
    return jsonify({"ok": True})

# ================== 前端展示 ==================
@app.route('/')
def index():
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>DeepSeek-Flash 极速纯 AI 预测</title>
    <style>
        * { box-sizing: border-box; }
        body { background: #f4f6f9; margin: 0; font-family: -apple-system, sans-serif; color: #333; }
        .head { background: #0b0f19; color: #fff; padding: 15px; text-align: center; font-size: 20px; font-weight: bold; }
        .status { text-align: center; padding: 10px; font-size: 14px; background: #fff; border-bottom: 1px solid #eaeaea; font-weight: bold; display: flex; justify-content: center; align-items: center;}
        .dot { width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
        .on { background: #00b894; box-shadow: 0 0 8px #00b894; animation: p 1.5s infinite;} 
        .off { background: #d63031; }
        @keyframes p { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
        
        .tabs { display: flex; padding: 10px; gap: 10px; background: #fff; border-bottom: 1px solid #f1f2f6;}
        .tab { flex: 1; padding: 10px; text-align: center; background: #f0f2f5; border-radius: 8px; font-weight: bold; font-size: 14px; cursor: pointer; }
        .tab.on { background: #0984e3; color: #fff; }
        
        .stats-bar { display: flex; background: #fff; margin: 12px; padding: 10px; border-radius: 12px; font-size: 13px; font-weight: bold; text-align: center;}
        .stats-item { flex: 1; border-right: 1px solid #f1f2f6;}
        .stats-item:last-child { border-right: none; }
        .stats-val { display: block; font-size: 18px; margin-top: 4px;}

        .card { background: #fff; margin: 12px; padding: 15px; border-radius: 12px; }
        .title { font-size: 14px; font-weight: bold; margin-bottom: 10px; color: #2d3436;}
        
        .history { display: flex; overflow-x: auto; gap: 10px; padding-bottom: 5px; }
        .h-item { background: #f8f9fa; padding: 10px; border-radius: 8px; min-width: 95px; text-align: center; border: 1px solid #eee;}
        .h-period { color: #b2bec3; font-size: 11px;}
        .h-nums { color: #636e72; font-size: 12px; margin: 4px 0; }
        .h-total { color: #d63031; font-weight: bold; font-size: 16px; }
        
        .kill { color: #d63031; font-size: 22px; font-weight: 900; text-align: center; margin: 10px 0; background: #fff5f5; padding: 12px; border-radius: 8px; }
        .rec-main { color: #fff; background: #e17055; font-size: 22px; font-weight: bold; text-align: center; margin-bottom: 10px; padding: 15px; border-radius: 8px; }
        .rec-other { display: flex; gap: 10px; margin-bottom: 15px;}
        .rec-def { flex: 1; color: #0984e3; background: #e8f4f8; font-size: 16px; font-weight: bold; text-align: center; padding: 12px; border-radius: 8px;}
        .rec-bak { flex: 1; color: #636e72; background: #f1f2f6; font-size: 16px; font-weight: bold; text-align: center; padding: 12px; border-radius: 8px;}
        
        .cd-box { text-align: center; font-size: 14px; color: #636e72; margin-bottom: 10px;}
        .cd { font-size: 22px; color: #0984e3; font-weight: bold; }
        
        .ana { background: #fdfaf6; padding: 15px; border-left: 4px solid #e17055; font-size: 14px; line-height: 1.7; color: #2d3436; white-space: pre-wrap; }
        
        .log-item { border-bottom: 1px solid #f1f2f6; padding: 10px 0; font-size: 13px; display: flex; justify-content: space-between; }
        .win { color: #00b894; font-weight: bold; } .lose { color: #d63031; font-weight: bold; }
        .btn-clear { float:right; font-size:12px; padding:5px 10px; border:1px solid #d63031; color:#d63031; border-radius:6px;}
        .log-scroll { max-height: 400px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="head">DeepSeek-Flash 极速纯 AI 预测</div>
    <div class="status" id="status"><span class="dot off"></span> AI 接口未连接</div>
    
    <div class="tabs">
        <div class="tab on" onclick="switchG('2', this)">加拿大28</div>
        <div class="tab" onclick="switchG('3', this)">分分28</div>
        <div class="tab" onclick="switchG('13', this)">比特28</div>
    </div>

    <div class="stats-bar">
        <div class="stats-item">当前连中<span class="stats-val win" id="st-cw">0</span></div>
        <div class="stats-item">当前连错<span class="stats-val lose" id="st-cl">0</span></div>
        <div class="stats-item">总命中<span class="stats-val win" id="st-tw">0</span></div>
        <div class="stats-item">总被杀<span class="stats-val lose" id="st-tl">0</span></div>
    </div>

    <div class="card">
        <div class="title">近 20 期 独立盘面</div>
        <div class="history" id="history"></div>
    </div>

    <div class="card" id="pred-box" style="display:none">
        <div class="title">目标拦截: <span id="next-period" style="color:#0984e3;"></span></div>
        <div class="kill">🚫 高危绝杀: <span id="kill-item"></span></div>
        <div class="rec-main">🔥 核心主攻: <span id="main-item"></span></div>
        <div class="rec-other">
            <div class="rec-def">🛡️ 重点防守: <span id="def-item"></span></div>
            <div class="rec-bak">🎯 战术备选: <span id="bak-item"></span></div>
        </div>
        <div class="cd-box">距开奖: <span class="cd" id="cd">--:--</span></div>
        <div class="ana" id="ana"></div>
    </div>

    <div class="card">
        <div class="title">历史复盘 <button class="btn-clear" onclick="clearLogs()">清空</button></div>
        <div id="logs" class="log-scroll"></div>
    </div>

<script>
    let curG = '2', timer = null;
    const KEY = "ultimate_ai_flash_v3";

    function switchG(g, el) {
        curG = g;
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
        el.classList.add('on');
        document.getElementById('pred-box').style.display = 'none';
        fetchData(); fetchLogs();
    }

    function fetchData() {
        fetch(`/api/data/${curG}`, { headers: {'X-Token': KEY} }).then(r => r.json()).then(res => {
            document.getElementById('status').innerHTML = `<span class="dot ${res.status.online ? 'on' : 'off'}"></span> AI接口：${res.status.msg}`;
            let d = res.data;
            if(!d.period) return;

            document.getElementById('history').innerHTML = d.history.slice(0, 10).map(h => `
                <div class="h-item">
                    <div class="h-period">${h.period.slice(-4)}期</div>
                    <div class="h-nums">${h.nums}</div>
                    <div class="h-total">${h.total}</div>
                    <div>${h.big_small}${h.odd_even}</div>
                </div>`).join('');

            if(d.pred) {
                document.getElementById('pred-box').style.display = 'block';
                document.getElementById('next-period').innerText = d.next;
                document.getElementById('kill-item').innerText = d.pred.kill;
                document.getElementById('ana').innerText = d.pred.analysis;
                
                try {
                    let parts = d.pred.rec.split('、');
                    document.getElementById('main-item').innerText = parts[0].replace('(主攻)', '');
                    document.getElementById('def-item').innerText = parts[1].replace('(防守)', '');
                    document.getElementById('bak-item').innerText = parts[2].replace('(备选)', '');
                } catch(e) {
                    document.getElementById('main-item').innerText = d.pred.rec;
                }
            }

            if(timer) clearInterval(timer);
            let left = d.left || 0;
            let cdEl = document.getElementById('cd');
            timer = setInterval(() => {
                if(left <= 0) { cdEl.innerText = "开奖中..."; return; }
                left--;
                cdEl.innerText = `${Math.floor(left/60).toString().padStart(2,'0')}:${(left%60).toString().padStart(2,'0')}`;
            }, 1000);
        });
    }

    function fetchLogs() {
        fetch(`/api/logs/${curG}`, { headers: {'X-Token': KEY} }).then(r => r.json()).then(res => {
            document.getElementById('st-cw').innerText = res.stats.current_win;
            document.getElementById('st-cl').innerText = res.stats.current_lose;
            document.getElementById('st-tw').innerText = res.stats.total_win;
            document.getElementById('st-tl').innerText = res.stats.total_lose;

            document.getElementById('logs').innerHTML = res.logs.map(l => `
                <div class="log-item">
                    <div><div style="color:#b2bec3; font-size:12px;">${l.period}</div><div>绝杀:<span class="lose">${l.kill}</span> | 推荐:${l.rec.replace(/(\(.*?\))/g, '')}</div></div>
                    <div style="text-align:right">
                        <div class="${l.status === 'win' ? 'win' : (l.status === 'lose' ? 'lose' : '')}">
                            ${l.status === 'win' ? '🀄 命中' : (l.status === 'lose' ? '💀 被杀' : '⏳ 等待')}
                        </div>
                        <div style="color:#b2bec3; font-size:12px;">${l.real_result ? `(实开:${l.real_result})` : ''}</div>
                    </div>
                </div>`).join('') || '<div style="text-align:center; padding:20px;">暂无记录</div>';
        });
    }

    function clearLogs() {
        if(!confirm("确定清空？")) return;
        fetch(`/api/clear/${curG}`, { method: 'POST', headers: {'X-Token': KEY} }).then(() => fetchLogs());
    }

    fetchData(); fetchLogs();
    setInterval(fetchData, 2000); setInterval(fetchLogs, 5000);
</script>
</body>
</html>
    """

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8888))
    app.run(host='0.0.0.0', port=port)
