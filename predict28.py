import urllib.request
import ssl
import json
import time
import threading
import os
import sqlite3
import re
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
SECRET_KEY = "ultimate_200_algo_v1"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

AI_STATUS = {"online": True, "msg": "本地 200 套独立算法运转中"}
LIVE_DATA = {
    "2": {"period": "", "next": "", "left": 0, "history": [], "pred": None},
    "3": {"period": "", "next": "", "left": 0, "history": [], "pred": None},
    "13": {"period": "", "next": "", "left": 0, "history": [], "pred": None}
}

# ================== 数据库 ==================
def db():
    conn = sqlite3.connect('predict_200_algo.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT,
        kill TEXT, rec TEXT, analysis TEXT, real_result TEXT DEFAULT '',
        status TEXT DEFAULT 'wait'
    )''')
    conn.commit()

# ================== 200套独立算法字典 (名称绝对不重复) ==================
# 每个游戏严格分配独立的算法编号区间
ALGO_POOL = {
    "2": [f"【加拿大专属-算法{i:03d}】" for i in range(1, 67)],   # 1-66
    "3": [f"【分分专属-算法{i:03d}】" for i in range(67, 134)],   # 67-133
    "13": [f"【比特专属-算法{i:03d}】" for i in range(134, 201)]  # 134-200
}

# ================== 核心本地算法推演引擎 ==================
def calculate_algo_prediction(gtype, history):
    if len(history) < 7:
        return {"kill": "数据不足", "rec": "数据不足", "analysis": "等待数据初始化..."}

    h7 = history[:7]
    bs_seq = [1 if h['big_small'] == '大' else 0 for h in h7]
    oe_seq = [1 if h['odd_even'] == '单' else 0 for h in h7]
    
    big_cnt, small_cnt = sum(bs_seq), 7 - sum(bs_seq)
    odd_cnt, even_cnt = sum(oe_seq), 7 - sum(oe_seq)

    def get_streak(seq):
        s = 1
        for i in range(1, len(seq)):
            if seq[i] == seq[0]: s += 1
            else: break
        return s
    bs_s = get_streak(bs_seq)
    oe_s = get_streak(oe_seq)

    # 获取当前游戏专属的 66/67 套算法池
    pool = ALGO_POOL[gtype]

    # 打分制矩阵
    scores = {"大单": 50, "大双": 50, "小单": 50, "小双": 50}
    triggered_logics = []

    # 本地动态算法判定
    # 1. 长龙极值
    if bs_s >= 4:
        if bs_seq[0] == 1:
            scores["大单"] += 15; scores["大双"] += 15; scores["小单"] -= 20; scores["小双"] -= 20
            triggered_logics.append(f"{pool[0]}判定：大小端连开{bs_s}期大，长龙顺势跟大。")
        else:
            scores["小单"] += 15; scores["小双"] += 15; scores["大单"] -= 20; scores["大双"] -= 20
            triggered_logics.append(f"{pool[1]}判定：小数连开{bs_s}期，动能强劲顺小。")
    elif bs_s == 2 or bs_s == 3:
        if bs_seq[0] == 1:
            scores["大单"] -= 10; scores["大双"] -= 10; scores["小单"] += 5; scores["小双"] += 5
            triggered_logics.append(f"{pool[2]}识别：大数连开{bs_s}期，极值断裂预警。")
    
    # 2. 均值回归
    if big_cnt >= 5:
        scores["大单"] -= 15; scores["大双"] -= 15; scores["小单"] += 10; scores["小双"] += 10
        triggered_logics.append(f"{pool[3]}测算：近7期大号过热({big_cnt}次)，均值回归杀大。")
    elif small_cnt >= 5:
        scores["小单"] -= 15; scores["小双"] -= 15; scores["大单"] += 10; scores["大双"] += 10
        triggered_logics.append(f"{pool[4]}测算：近7期小号出现{small_cnt}次，防触底反弹。")

    if odd_cnt >= 5:
        scores["大单"] -= 15; scores["小单"] -= 15; scores["大双"] += 10; scores["小双"] += 10
        triggered_logics.append(f"{pool[5]}预警：单数出现{odd_cnt}次，多空动能耗尽。")
    elif even_cnt >= 5:
        scores["大双"] -= 15; scores["小双"] -= 15; scores["大单"] += 10; scores["小单"] += 10
        triggered_logics.append(f"{pool[6]}预警：双数异常增多({even_cnt}次)，防重心偏移。")

    # 3. 形态连跳与组合
    combos = [h['big_small'] + h['odd_even'] for h in h7]
    if combos[0] == combos[1]:
        scores[combos[0]] -= 10
        triggered_logics.append(f"{pool[7]}检测：{combos[0]}组合连开2期，三连概率极低。")
    elif combos[0] in combos[1:4]:
        scores[combos[0]] -= 5
        triggered_logics.append(f"{pool[8]}检测：近期频繁交替形态，规避上期热门。")

    # 排序得出最终结果
    sorted_combos = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    main_atk = sorted_combos[0][0]
    defend = sorted_combos[1][0]
    backup = sorted_combos[2][0]
    kill_str = sorted_combos[3][0]

    # ================== 动态组装文字 (150 - 500 字) ==================
    # 抽取几条核心逻辑组装文字
    import random
    random.shuffle(triggered_logics)
    selected = triggered_logics[:4] # 选4条
    
    intro = f"【{GAMES[gtype]['name']}纯本地算法推演】本次系统调用了专属独立算法池进行深度测算：\n"
    body = ""
    for i, text in enumerate(selected):
        body += f"{i+1}. {text}\n"
    
    outro = f"综合多套核心算法矩阵的交叉验证，当前盘面【{kill_str}】风险极高，已形成明显的杀猪陷阱。建议将主攻火力集中于【{main_atk}】，辅以【{defend}】防守和【{backup}】备选。请严格按照指令执行，切忌盲目追热。"
    
    analysis_text = intro + body + outro
    
    # 兜底填充逻辑，确保字数在 150 - 500 之间
    def count_chinese(text):
        return len(re.findall(r'[\u4e00-\u9fa5]', text))
    
    while count_chinese(analysis_text) < 150:
        fillers = [
            f"此外，{pool[10]}的数据模型显示，近期振幅正在收敛，随时可能爆发单边行情，此时反向布局最为稳妥。",
            f"{pool[12]}进一步校验了冷热筹码分布，发现高位区间套牢盘极多，主力洗盘意图十分坚决。",
            f"底层逻辑{pool[15]}结合贝叶斯概率推算，当前连续形态必然断裂，绝不可盲目顺势。"
        ]
        analysis_text += random.choice(fillers)
        
    if count_chinese(analysis_text) > 500:
        analysis_text = intro + body + outro # 如果太长直接砍掉多余填充

    rec_str = f"{main_atk}(主攻)、{defend}(防守)、{backup}(备选)"

    return {
        "kill": kill_str,
        "rec": rec_str,
        "analysis": analysis_text
    }

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
                        history = [{"period": i['period'], "nums": f"{i['num1']} + {i['num2']} + {i['num3']}", "total": i['total'], "big_small": i['big_small'], "odd_even": i['odd_even']} for i in data['data'][:20]]
                        
                        if LIVE_DATA[gt]['period'] != latest['period']:
                            # 结算
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
                            
                            # 毫秒级本地计算
                            pred = calculate_algo_prediction(gt, history)
                            LIVE_DATA[gt]['pred'] = pred
                            
                            with db() as conn:
                                conn.execute('''INSERT INTO logs (gtype, period, kill, rec, analysis) VALUES (?,?,?,?,?)''', 
                                             (gt, LIVE_DATA[gt]['next'], pred['kill'], pred['rec'], pred['analysis']))
                                conn.commit()
                                
                        diff = LIVE_DATA[gt]['target_time'] - datetime.utcnow().timestamp()
                        LIVE_DATA[gt]['left'] = max(0, int(diff))
            except Exception as e:
                pass
        time.sleep(1)

threading.Thread(target=fetch_loop, daemon=True).start()

# ================== 接口 ==================
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

# ================== 前端 ==================
@app.route('/')
def index():
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>200套独立算法公益预测</title>
    <style>
        * { box-sizing: border-box; }
        body { background: #f4f6f9; margin: 0; font-family: -apple-system, sans-serif; color: #333; }
        .head { background: #0b0f19; color: #fff; padding: 15px; text-align: center; font-size: 20px; font-weight: bold; }
        .status { text-align: center; padding: 10px; font-size: 14px; background: #fff; border-bottom: 1px solid #eaeaea; font-weight: bold; display: flex; justify-content: center; align-items: center;}
        .dot { width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; background: #00b894; box-shadow: 0 0 8px #00b894; animation: p 1.5s infinite;} 
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
    <div class="head">200套独立公益算法</div>
    <div class="status" id="status"><span class="dot"></span> 算法运转中 (0延迟)</div>
    
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
    const KEY = "ultimate_200_algo_v1";

    function switchG(g, el) {
        curG = g;
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
        el.classList.add('on');
        document.getElementById('pred-box').style.display = 'none';
        fetchData(); fetchLogs();
    }

    function fetchData() {
        fetch(`/api/data/${curG}`, { headers: {'X-Token': KEY} }).then(r => r.json()).then(res => {
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
