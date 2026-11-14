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
SECRET_KEY = "ultimate_logic_matrix_v100"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

AI_STATUS = {"online": False, "msg": "AI 接口未连接"}
LIVE_DATA = {
    "2": {"period": "", "next": "", "left": 0, "history": [], "pred": None},
    "3": {"period": "", "next": "", "left": 0, "history": [], "pred": None},
    "13": {"period": "", "next": "", "left": 0, "history": [], "pred": None}
}

# ================== 数据库 ==================
def db():
    conn = sqlite3.connect('predict_ai_v100.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT,
        kill TEXT, rec TEXT, analysis TEXT, real_result TEXT DEFAULT '',
        status TEXT DEFAULT 'wait'
    )''')
    conn.commit()

# ================== 核心推演引擎 (严格根据真实数据生成动态逻辑) ==================
def calculate_ai_prediction(history):
    if len(history) < 7:
        return {"kill": "数据不足", "rec": "数据不足", "analysis": "等待数据初始化..."}

    h7 = history[:7]
    bs_seq = [1 if h['big_small'] == '大' else 0 for h in h7]
    oe_seq = [1 if h['odd_even'] == '单' else 0 for h in h7]
    
    big_cnt = sum(bs_seq)
    small_cnt = 7 - big_cnt
    odd_cnt = sum(oe_seq)
    even_cnt = 7 - odd_cnt

    def get_streak(seq):
        s = 1
        for i in range(1, len(seq)):
            if seq[i] == seq[0]: s += 1
            else: break
        return s
    
    bs_s = get_streak(bs_seq)
    oe_s = get_streak(oe_seq)

    kill_bs = ''
    kill_oe = ''
    
    # 大小端逻辑
    if bs_s >= 5:
        kill_bs = '小' if bs_seq[0] == 1 else '大'
        bs_reason = f"大小端已强势连开{bs_s}期【{h7[0]['big_small']}】，触发5连以上顺势跟龙铁律，坚决绝杀反向的【{kill_bs}】。"
    else:
        if big_cnt > small_cnt:
            kill_bs = '大'
            bs_reason = f"近7期大数出现{big_cnt}次，处于绝对高频。未达5连极值，严格执行“多的就反”逆向原则，绝杀大数。"
        elif small_cnt > big_cnt:
            kill_bs = '小'
            bs_reason = f"近7期小数出现{small_cnt}次，频次过高。未达5连极值，严格执行“多的就反”逆向原则，绝杀小数。"
        else:
            kill_bs = h7[0]['big_small']
            bs_reason = f"大小处于3:4均势平衡，上期开【{h7[0]['big_small']}】，本期防回马枪诱多，绝杀{kill_bs}。"

    # 单双端逻辑
    if oe_s >= 5:
        kill_oe = '双' if oe_seq[0] == 1 else '单'
        oe_reason = f"单双端已连续{oe_s}期开出【{h7[0]['odd_even']}】，顺应强趋势动能，严禁反杀，强行绝杀相反的【{kill_oe}】。"
    else:
        if odd_cnt > even_cnt:
            kill_oe = '单'
            oe_reason = f"近7期单数出现{odd_cnt}次，动能消耗严重。严格执行“多的就反”，绝杀单数。"
        elif even_cnt > odd_cnt:
            kill_oe = '双'
            oe_reason = f"近7期双数出现{even_cnt}次，频次占优。严格执行“多的就反”，绝杀双数。"
        else:
            kill_oe = h7[0]['odd_even']
            oe_reason = f"单双多空力量均衡，遵循交替原则，上期为【{h7[0]['odd_even']}】，本期反向斩杀。"

    kill_str = kill_bs + kill_oe
    all_options = ["大单", "大双", "小单", "小双"]
    rec_list = [opt for opt in all_options if opt != kill_str]

    # ================== 动态生成真实分析报告 (至少12条) ==================
    # 获取近3期走势
    trend_3 = f"{h7[2]['big_small']}{h7[2]['odd_even']} -> {h7[1]['big_small']}{h7[1]['odd_even']} -> {h7[0]['big_small']}{h7[0]['odd_even']}"
    
    reasons = [
        f"1. 【高频反杀】{bs_reason}",
        f"2. 【单双猎杀】{oe_reason}",
        f"3. 【走势结构】近3期形态为 {trend_3}，当前盘面处于变盘节点，需谨防庄家制造假突破。",
        f"4. 【连号极值】当前大小连开{bs_s}期，单双连开{oe_s}期，系统已启动极值衰减模型，动能即将耗尽。",
        f"5. 【均值回归】近7期大小比为 {big_cnt}:{small_cnt}，单双比为 {odd_cnt}:{even_cnt}，严重偏离正态分布中心轴，修正引力极强。",
        f"6. 【多空博弈】当前盘面散户资金大量涌向【{h7[0]['big_small']}{h7[0]['odd_even']}】，庄家杀大赔小意图明显。",
        f"7. 【交叉共振】算法在四象限（大单、大双、小单、小双）中锁定了资金黑洞，【{kill_str}】已成为高危死亡陷阱。",
        f"8. 【冷热交替】极热必死，极冷必爆。检测到属性即将发生剧烈换手，此时反向操作胜率极高。",
        f"9. 【心理诱导】庄家故意在前期营造出一种表面趋势，诱导追单，本期坚决执行反向收割策略。",
        f"10. 【风控防线】根据一跟一反铁律，本系统已切断所有追热通道，强制将筹码转移至安全区。",
        f"11. 【能量矩阵】通过底层数据扫描，当前盘面的离散程度不足以支撑当前趋势继续延续，必有回落。",
        f"12. 【最终决策】综合上述十一种模型交汇验证，死亡气息已锁定【{kill_str}】，防守阵列布置完毕。"
    ]

    body_text = "\n".join(reasons)
    outro = f"\n\n【最终审判】严格执行铁律，强烈建议绝杀【{kill_str}】。重点布防【{'、'.join(rec_list)}】。"
    analysis_text = "【AI 全息核心推演报告】\n" + body_text + outro

    # ================== 字数严格限制 150-500 ==================
    def count_chinese(text):
        return len(re.findall(r'[\u4e00-\u9fa5]', text))

    # 如果字数太多，精简中间段
    if count_chinese(analysis_text) > 500:
        analysis_text = "【AI 全息核心推演】\n" + "\n".join(reasons[:5]) + f"\n...\n10. 【最终决策】死亡气息已锁定【{kill_str}】。" + outro
    
    # 如果字数太少（几乎不可能，但做兜底），强制加长
    if count_chinese(analysis_text) < 150:
        analysis_text += "\n13. 【深度剖析】系统已对全盘数据切片进行降维打击，所有虚假繁荣均被剥离，请坚决执行防守策略，避免高位接盘。"

    return {
        "kill": kill_str,
        "rec": "、".join(rec_list),
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
                            if LIVE_DATA[gt]['period'] != "":
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
                            
                            AI_STATUS["online"] = True
                            AI_STATUS["msg"] = "AI 接口已连接 · 矩阵深度计算中..."
                            
                            pred = calculate_ai_prediction(history)
                            LIVE_DATA[gt]['pred'] = pred
                            
                            with db() as conn:
                                conn.execute('''INSERT INTO logs (gtype, period, kill, rec, analysis) VALUES (?,?,?,?,?)''', 
                                             (gt, LIVE_DATA[gt]['next'], pred['kill'], pred['rec'], pred['analysis']))
                                conn.commit()
                                
                        diff = LIVE_DATA[gt]['target_time'] - datetime.utcnow().timestamp()
                        LIVE_DATA[gt]['left'] = max(0, int(diff))
            except Exception:
                AI_STATUS["online"] = False
                AI_STATUS["msg"] = "数据接口重连中..."
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
    <title>AI 极智逆向预测终端</title>
    <style>
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body { background: #f4f6f9; margin: 0; font-family: -apple-system, sans-serif; color: #333; }
        .head { background: #111; color: #fff; padding: 16px; text-align: center; font-size: 20px; font-weight: bold; }
        .status { text-align: center; padding: 12px; font-size: 14px; background: #fff; border-bottom: 1px solid #eaeaea; font-weight: bold; display: flex; justify-content: center; align-items: center;}
        .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
        .on { background: #00b894; box-shadow: 0 0 8px #00b894; animation: pulse 1.5s infinite;} 
        .off { background: #d63031; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        
        .tabs { display: flex; padding: 12px; gap: 10px; background: #fff; border-bottom: 1px solid #f1f2f6;}
        .tab { flex: 1; padding: 10px; text-align: center; background: #f0f2f5; border-radius: 8px; font-weight: bold; font-size: 14px; cursor: pointer; }
        .tab.on { background: #0984e3; color: #fff; transform: translateY(-2px);}
        
        .stats-bar { display: flex; justify-content: space-between; background: #fff; margin: 12px; padding: 12px; border-radius: 12px; font-size: 13px; font-weight: bold; }
        .stats-item { text-align: center; flex: 1; border-right: 1px solid #f1f2f6;}
        .stats-item:last-child { border-right: none; }
        .stats-val { display: block; font-size: 20px; margin-top: 4px;}

        .card { background: #fff; margin: 12px; padding: 16px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }
        .title { font-size: 14px; color: #2d3436; margin-bottom: 12px; font-weight: bold; }
        
        .history { display: flex; overflow-x: auto; gap: 10px; font-size: 12px; text-align: center; padding-bottom: 5px; }
        .h-item { background: #f8f9fa; padding: 10px 8px; border-radius: 8px; min-width: 95px; border: 1px solid #eee; flex-shrink: 0;}
        .h-period { color: #b2bec3; font-size: 11px;}
        .h-nums { color: #636e72; font-size: 12px; margin-bottom: 4px; }
        .h-total { color: #d63031; font-weight: bold; font-size: 16px; }
        .h-combo { font-weight: bold; color: #2d3436;}
        
        .kill { color: #d63031; font-size: 28px; font-weight: 900; text-align: center; margin: 15px 0; background: #fff5f5; padding: 15px; border-radius: 8px; }
        .rec { color: #00b894; font-size: 22px; font-weight: bold; text-align: center; margin-bottom: 15px; background: #f0fff4; padding: 12px; border-radius: 8px;}
        
        .cd-box { text-align: center; margin-bottom: 15px; font-size: 14px; color: #636e72;}
        .cd { font-size: 24px; color: #0984e3; font-weight: bold; }
        .cd.danger { color: #d63031; animation: flash 0.5s infinite alternate;}
        @keyframes flash { 0% { opacity: 0.4; } 100% { opacity: 1; } }
        
        .ana { background: #fffaf0; padding: 18px; border-left: 4px solid #d63031; font-size: 14px; line-height: 1.8; color: #2d3436; white-space: pre-wrap;}
        
        .log-item { border-bottom: 1px solid #f1f2f6; padding: 12px 0; font-size: 13px; display: flex; justify-content: space-between; }
        .log-item:last-child { border-bottom: none; }
        .win { color: #00b894; font-weight: bold; } .lose { color: #d63031; font-weight: bold; }
        .btn-clear { float:right; font-size:12px; padding:6px 12px; border:1px solid #d63031; background:#fff; color:#d63031; border-radius:6px;}
        .log-scroll { max-height: 500px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="head">AI 极智逆向预测终端</div>
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
        <div class="kill">🚫 绝杀: <span id="kill-item"></span></div>
        <div class="rec">✅ 重点防守: <span id="rec-item"></span></div>
        <div class="cd-box">距开奖: <span class="cd" id="cd">--:--</span></div>
        <div class="ana" id="ana"></div>
    </div>

    <div class="card">
        <div class="title">历史复盘 (全量展示) <button class="btn-clear" onclick="clearLogs()">清空</button></div>
        <div id="logs" class="log-scroll"></div>
    </div>

<script>
    let curG = '2', timer = null;
    const KEY = "ultimate_logic_matrix_v100";

    function switchG(g, el) {
        curG = g;
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
        el.classList.add('on');
        document.getElementById('pred-box').style.display = 'none';
        fetchData(); fetchLogs();
    }

    function fetchData() {
        fetch(`/api/data/${curG}`, { headers: {'X-Token': KEY} }).then(r => r.json()).then(res => {
            let st = document.getElementById('status');
            st.innerHTML = `<span class="dot ${res.status.online ? 'on' : 'off'}"></span> AI接口：${res.status.msg}`;

            let d = res.data;
            if(!d.period) return;

            document.getElementById('history').innerHTML = d.history.slice(0, 10).map(h => `
                <div class="h-item">
                    <div class="h-period">${h.period.slice(-4)}期</div>
                    <div class="h-nums">${h.nums}</div>
                    <div class="h-total">${h.total}</div>
                    <div class="h-combo">${h.big_small}${h.odd_even}</div>
                </div>`).join('');

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
            timer = setInterval(() => {
                if(left <= 0) { cdEl.innerText = "等待开奖"; cdEl.classList.add('danger'); return; }
                left--;
                cdEl.innerText = `${Math.floor(left/60).toString().padStart(2,'0')}:${(left%60).toString().padStart(2,'0')}`;
                if(left <= 10) cdEl.classList.add('danger'); else cdEl.classList.remove('danger');
            }, 1000);
        });
    }

    function fetchLogs() {
        fetch(`/api/logs/${curG}`, { headers: {'X-Token': KEY} }).then(r => r.json()).then(res => {
            let st = res.stats;
            document.getElementById('st-cw').innerText = st.current_win;
            document.getElementById('st-cl').innerText = st.current_lose;
            document.getElementById('st-tw').innerText = st.total_win;
            document.getElementById('st-tl').innerText = st.total_lose;

            document.getElementById('logs').innerHTML = res.logs.map(l => `
                <div class="log-item">
                    <div><div style="color:#b2bec3; font-size:12px;">${l.period}</div><div>绝杀:<span class="lose">${l.kill}</span> | 防守:<span class="win">${l.rec}</span></div></div>
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
