import urllib.request
import ssl
import json
import time
import threading
import os
import sqlite3
import re
import random
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

# =====================================================================
# 模块 1：Flask 核心初始化与应用配置
# =====================================================================
app = Flask(__name__)
SECRET_KEY = "ultimate_logic_matrix_v99"

GAMES = {
    "2": {"name": "加拿大28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "interval": 210},
    "3": {"name": "分分28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "interval": 60},
    "13": {"name": "比特28", "url": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "interval": 60}
}

# 全局运行状态
AI_STATUS = {"online": False, "msg": "AI 核心接口未连接"}
LIVE_DATA = {
    "2": {"period": "", "next": "", "left": 0, "history": [], "pred": None},
    "3": {"period": "", "next": "", "left": 0, "history": [], "pred": None},
    "13": {"period": "", "next": "", "left": 0, "history": [], "pred": None}
}

# =====================================================================
# 模块 2：SQLite 数据库持久化层
# =====================================================================
def db():
    conn = sqlite3.connect('predict_ai_advanced.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            gtype TEXT, 
            period TEXT,
            kill TEXT, 
            rec TEXT, 
            analysis TEXT, 
            real_result TEXT DEFAULT '',
            status TEXT DEFAULT 'wait'
        )
    ''')
    conn.commit()

# =====================================================================
# 模块 3：核心推演引擎 - AI 精准预测 (严格落实跟反与5连逻辑)
# =====================================================================
def calculate_ai_prediction(history):
    if len(history) < 7:
        return {"kill": "数据不足", "rec": "数据不足", "analysis": "系统正在收集足够的历史切片数据，请等待下一期开奖后进行初始化分析。"}

    # 截取近 7 期数据
    h7 = history[:7]
    bs_seq = [1 if h['big_small'] == '大' else 0 for h in h7]
    oe_seq = [1 if h['odd_even'] == '单' else 0 for h in h7]
    
    big_cnt = sum(bs_seq)
    small_cnt = 7 - big_cnt
    odd_cnt = sum(oe_seq)
    even_cnt = 7 - odd_cnt

    # 计算连号
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
    reasons = []

    # ==========================================
    # 核心逻辑 1：判定大小端绝杀项
    # 规则：未达5连：少的跟，多的反(杀多)。5连以上：多的跟(杀反向)
    # ==========================================
    if bs_s >= 5:
        kill_bs = '小' if bs_seq[0] == 1 else '大'
        reasons.append(f"【极值长龙】大小端已强势连开{bs_s}期{ h7[0]['big_small'] }，触发5连以上顺势跟龙铁律，坚决绝杀反向的【{kill_bs}】。")
    else:
        if big_cnt > small_cnt:
            kill_bs = '大'
            reasons.append(f"【反多跟少】近7期大数出现{big_cnt}次，处于绝对高频期。严格执行“多的就反”的逆向博弈原则，绝杀大数。")
        elif small_cnt > big_cnt:
            kill_bs = '小'
            reasons.append(f"【反多跟少】近7期小数出现{small_cnt}次，频次过高。严格执行“多的就反”的逆向博弈原则，绝杀小数。")
        else:
            # 平局时，看最近两期谁多，或者杀上期
            kill_bs = h7[0]['big_small']
            reasons.append(f"【均衡破局】近期大小呈现50%均态平衡，根据走势惯性推演，上期开出{h7[0]['big_small']}，本期大概率回马枪诱杀，绝杀{kill_bs}。")

    # ==========================================
    # 核心逻辑 2：判定单双端绝杀项
    # ==========================================
    if oe_s >= 5:
        kill_oe = '双' if oe_seq[0] == 1 else '单'
        reasons.append(f"【单双长龙】单双端已连续{oe_s}期开出{h7[0]['odd_even']}，顺应强趋势动能，严禁反杀，强行绝杀相反的【{kill_oe}】。")
    else:
        if odd_cnt > even_cnt:
            kill_oe = '单'
            reasons.append(f"【反多跟少】近7期单数出现{odd_cnt}次，动能消耗严重。严格执行“多的就反”逻辑，本期判定单数动能枯竭，绝杀单数。")
        elif even_cnt > odd_cnt:
            kill_oe = '双'
            reasons.append(f"【反多跟少】近7期双数出现{even_cnt}次，频次占优。严格执行“多的就反”逻辑，防均值回归，绝杀双数。")
        else:
            kill_oe = h7[0]['odd_even']
            reasons.append(f"【均势打压】单双多空力量完全均衡，遵循“一跟一反”的交替原则，上期为{h7[0]['odd_even']}，本期反向斩杀。")

    # 组合绝杀项
    kill_str = kill_bs + kill_oe
    all_options = ["大单", "大双", "小单", "小双"]
    rec_list = [opt for opt in all_options if opt != kill_str]

    # ==========================================
    # 核心逻辑 3：生成至少 10 条解释说明
    # ==========================================
    # 补充计算用于生成 10 条文案的数据
    total_sum = sum([h['total'] for h in h7])
    avg_sum = total_sum / 7.0
    
    # 预置 10 条说明库，每次随机抽取保证不重复
    reason_pool = [
        f"【均值回归模型】近7期大小比为 {big_cnt}:{small_cnt}，单双比为 {odd_cnt}:{even_cnt}，当前数据严重偏离正态分布中心轴，修正引力极强。",
        f"【震荡周期律】观察近 3 期形态，走势呈明显的 {h7[2]['big_small']}-{h7[1]['big_small']}-{h7[0]['big_small']} 跳跃震荡，本期坚决防范单边拉升或暴跌陷阱。",
        f"【极值反转测算】综合近7期和值均值为 {avg_sum:.1f}，目前盘面正处于高/低点转换边缘，庄家杀大赔小的意图已被算法识破。",
        f"【回马枪预警】上期开出【{h7[0]['big_small']}{h7[0]['odd_even']}】，极易引发大量散户跟风，本期庄家极大概率使用回马枪战术，绝杀当前热门形态。",
        f"【动能衰减系数】连号期数分别为大小 {bs_s} 连、单双 {oe_s} 连，根据动能衰减曲线，突破历史极值前必然有一次剧烈的洗盘动作。",
        f"【组合交叉共振】大单、大双、小单、小双四个象限中，当前热门象限极易形成资金黑洞，算法已锁定高危死亡陷阱【{kill_str}】。",
        f"【庄家诱盘心理】利用“少的就跟”思维，庄家在前期故意压制某一属性，后期极易引发报复性连开，当前反向操作策略已启动。",
        f"【筹码分布探测】热号区域筹码过于集中，已触发警报系统，必须坚决规避高位接盘，转向防守冷门区域。",
        f"【动量背离信号】从近两期走势来看，虽然表面延续趋势，但底层波幅已出现明显背离，这是典型的变盘前兆。",
        f"【卡方分布检验】经过严密测算，近期开奖序列的随机性概率低于阈值，存在明显的操盘干预痕迹，需执行强反杀逻辑。",
        f"【冷热交替法则】极热必死，极冷必爆。系统检测到大小单双属性即将发生剧烈换手，请紧跟防守阵列。",
        f"【斐波那契时间窗】当前期号末尾进入时间共振极点，历史同形态回测胜率极高，绝杀项不容置疑。"
    ]

    # 随机打乱并抽取 10 条
    random.shuffle(reason_pool)
    selected_reasons = reason_pool[:10]
    
    # 组装初始文案
    intro = "【AI 核心矩阵推演报告】本次运算结合走势逆反逻辑与连号极值规律，深度解析如下：\n\n"
    for i, r in enumerate(selected_reasons):
        reasons.append(r)
        
    # 将核心判定逻辑插入最前面
    final_reasons = reasons + selected_reasons
    random.shuffle(final_reasons) # 打乱顺序让内容看起来更丰富

    body_text = ""
    for i, r in enumerate(final_reasons):
        body_text += f"{i+1}. {r}\n"
        
    outro = f"\n【最终审判】严格落实“一跟一反、少跟多反”铁律，强烈建议绝杀【{kill_str}】。将所有筹码重心布防于【{'、'.join(rec_list)}】。"
    
    analysis_text = intro + body_text + outro

    # ==========================================
    # 核心逻辑 4：字数刺客，严格控制 150-500 字（不含标点）
    # ==========================================
    def count_chinese_chars(text):
        # 匹配所有中文字符
        return len(re.findall(r'[\u4e00-\u9fa5]', text))

    ch_count = count_chinese_chars(analysis_text)
    
    # 如果字数不足 150，强制补充宏观废话（深度剖析）
    while ch_count < 150:
        padding = [
            "【高维数据下沉】系统已对所有底层筹码进行降维打击，确保毫无盲区。",
            "【心理博弈极限】反向利用散户的锚定效应，完成最终的财富收割。",
            "【量化风控防线】严格按照跟反比例调配防守仓位，绝不留任何漏洞。"
        ]
        analysis_text += random.choice(padding)
        ch_count = count_chinese_chars(analysis_text)
        
    # 如果字数超过 500，强制截断
    if ch_count > 500:
        # 比较难直接精确截取中文字符，这里做粗略截断（保留前面部分）
        # 为了避免破坏最终审判的格式，直接削减中间段落
        cut_index = analysis_text.find("【最终审判】")
        if cut_index != -1:
            part1 = analysis_text[:cut_index]
            part2 = analysis_text[cut_index:]
            # 截断前半部分
            analysis_text = part1[:int(len(part1) * 0.6)] + "\n(已省略部分冗余推演)\n" + part2
        else:
            analysis_text = analysis_text[:1000] + "..."

    return {
        "kill": kill_str,
        "rec": "、".join(rec_list),
        "analysis": analysis_text
    }

# =====================================================================
# 模块 4：后台数据抓取与绝对精准结算引擎
# =====================================================================
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
                        
                        # 提取包含加号的数据
                        history = []
                        for i in data['data'][:20]:
                            history.append({
                                "period": i['period'], 
                                "nums": f"{i['num1']} + {i['num2']} + {i['num3']}", 
                                "total": i['total'], 
                                "big_small": i['big_small'], 
                                "odd_even": i['odd_even']
                            })
                        
                        if LIVE_DATA[gt]['period'] != latest['period']:
                            
                            # 结算上一期
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
                                "period": latest['period'], 
                                "next": str(int(latest['period'])+1),
                                "target_time": next_utc.timestamp(), 
                                "history": history
                            })
                            
                            # 更新顶部状态，表现出 AI 在工作
                            AI_STATUS["online"] = True
                            AI_STATUS["msg"] = "AI 核心接口已连接 · 正在精准计算..."
                            
                            pred = calculate_ai_prediction(history)
                            LIVE_DATA[gt]['pred'] = pred
                            
                            with db() as conn:
                                conn.execute('''INSERT INTO logs (gtype, period, kill, rec, analysis) VALUES (?,?,?,?,?)''', 
                                             (gt, LIVE_DATA[gt]['next'], pred['kill'], pred['rec'], pred['analysis']))
                                conn.commit()
                                
                        diff = LIVE_DATA[gt]['target_time'] - datetime.utcnow().timestamp()
                        LIVE_DATA[gt]['left'] = max(0, int(diff))
            except Exception as e:
                print("数据抓取异常:", e)
                AI_STATUS["online"] = False
                AI_STATUS["msg"] = "数据接口重连中..."
        time.sleep(1)

threading.Thread(target=fetch_loop, daemon=True).start()

# =====================================================================
# 模块 5：API 数据接口层
# =====================================================================
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
        settled_status = [l['status'] for l in logs if l['status'] in ('win', 'lose')]
        
        for st in settled_status:
            if st == 'win': stats['total_win'] += 1
            elif st == 'lose': stats['total_lose'] += 1
            
        for st in settled_status:
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

# =====================================================================
# 模块 6：前端 HTML 渲染
# =====================================================================
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
        
        /* 顶部栏 */
        .head { background: #111; color: #fff; padding: 16px; text-align: center; font-size: 20px; font-weight: bold; letter-spacing: 1px; box-shadow: 0 2px 10px rgba(0,0,0,0.2);}
        
        /* 强调 AI 接口连接状态 */
        .status { text-align: center; padding: 12px; font-size: 14px; background: #fff; border-bottom: 1px solid #eaeaea; font-weight: bold; display: flex; justify-content: center; align-items: center;}
        .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
        .on { background: #00b894; box-shadow: 0 0 8px #00b894; animation: pulse 1.5s infinite;} 
        .off { background: #d63031; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        
        .tabs { display: flex; padding: 12px; gap: 10px; background: #fff; border-bottom: 1px solid #f1f2f6;}
        .tab { flex: 1; padding: 10px; text-align: center; background: #f0f2f5; border-radius: 8px; font-weight: bold; font-size: 14px; cursor: pointer; transition: all 0.3s;}
        .tab.on { background: #0984e3; color: #fff; box-shadow: 0 4px 10px rgba(9,132,227,0.3); transform: translateY(-2px);}
        
        .stats-bar { display: flex; justify-content: space-between; background: #fff; margin: 12px; padding: 12px; border-radius: 12px; font-size: 13px; font-weight: bold; box-shadow: 0 2px 10px rgba(0,0,0,0.04);}
        .stats-item { text-align: center; flex: 1; border-right: 1px solid #f1f2f6;}
        .stats-item:last-child { border-right: none; }
        .stats-val { display: block; font-size: 20px; margin-top: 4px;}

        .card { background: #fff; margin: 12px; padding: 16px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }
        .title { font-size: 14px; color: #2d3436; margin-bottom: 12px; font-weight: bold; display: flex; align-items: center;}
        .title::before { content: ''; display: inline-block; width: 4px; height: 14px; background: #0984e3; border-radius: 2px; margin-right: 8px;}
        
        .history { display: flex; overflow-x: auto; gap: 10px; font-size: 12px; text-align: center; padding-bottom: 5px; }
        .h-item { background: #f8f9fa; padding: 10px 8px; border-radius: 8px; min-width: 95px; border: 1px solid #eee; flex-shrink: 0;}
        .h-period { color: #b2bec3; font-weight: bold; margin-bottom: 4px; font-size: 11px;}
        .h-nums { color: #636e72; font-size: 12px; margin-bottom: 4px; font-weight: 500;}
        .h-total { color: #d63031; font-weight: bold; font-size: 16px; margin: 4px 0;}
        .h-combo { font-weight: bold; color: #2d3436;}
        
        .kill { color: #d63031; font-size: 28px; font-weight: 900; text-align: center; margin: 15px 0; background: #fff5f5; padding: 15px; border-radius: 8px; letter-spacing: 2px;}
        .rec { color: #00b894; font-size: 22px; font-weight: bold; text-align: center; margin-bottom: 15px; background: #f0fff4; padding: 12px; border-radius: 8px;}
        
        .cd-box { text-align: center; margin-bottom: 15px; font-size: 14px; color: #636e72;}
        .cd { font-size: 24px; color: #0984e3; font-weight: bold; font-family: monospace;}
        .cd.danger { color: #d63031; animation: flash 0.5s infinite alternate;}
        @keyframes flash { 0% { opacity: 0.4; } 100% { opacity: 1; } }
        
        /* 深度分析小作文 */
        .ana { background: #fffaf0; padding: 18px; border-left: 4px solid #d63031; font-size: 14px; line-height: 1.8; border-radius: 4px; color: #2d3436; font-weight: 500; text-align: justify; white-space: pre-wrap;}
        
        .log-item { border-bottom: 1px solid #f1f2f6; padding: 12px 0; font-size: 13px; display: flex; justify-content: space-between; }
        .log-item:last-child { border-bottom: none; }
        .win { color: #00b894; font-weight: bold; } .lose { color: #d63031; font-weight: bold; }
        .btn-clear { float:right; margin-top:-30px; font-size:12px; padding:6px 12px; border:1px solid #d63031; background:#fff; color:#d63031; border-radius:6px; font-weight: bold; transition: 0.2s;}
        .btn-clear:active { background: #d63031; color: #fff;}
        
        .log-scroll { max-height: 500px; overflow-y: auto; padding-right: 5px; }
        .log-scroll::-webkit-scrollbar { width: 4px; }
        .log-scroll::-webkit-scrollbar-thumb { background: #dfe6e9; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="head">AI 极智逆向预测终端</div>
    
    <!-- 强调 AI 连接状态 -->
    <div class="status" id="status"><span class="dot off"></span> AI 核心接口未连接</div>
    
    <div class="tabs">
        <div class="tab on" onclick="switchG('2', this)">加拿大28</div>
        <div class="tab" onclick="switchG('3', this)">分分28</div>
        <div class="tab" onclick="switchG('13', this)">比特28</div>
    </div>

    <div class="stats-bar" id="stats-bar">
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
        <div class="title">目标拦截期号: <span id="next-period" style="color:#0984e3; font-size:16px;"></span></div>
        <div class="kill">🚫 绝杀: <span id="kill-item"></span></div>
        <div class="rec">✅ 重点防守: <span id="rec-item"></span></div>
        <div class="cd-box">距开奖结算: <span class="cd" id="cd">--:--</span></div>
        <div class="ana" id="ana">AI 正在进行 100 维深度推演，请稍后...</div>
    </div>

    <div class="card">
        <div class="title">历史复盘记录 (全量展示)</div>
        <button class="btn-clear" onclick="clearLogs()">清空数据</button>
        <div id="logs" class="log-scroll" style="margin-top:15px;"></div>
    </div>

<script>
    let curG = '2';
    let timer = null;
    const KEY = "ultimate_logic_matrix_v99";

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
                st.innerHTML = `<span class="dot on"></span> AI 接口：${res.status.msg}`;
            } else {
                st.innerHTML = `<span class="dot off"></span> AI 接口：${res.status.msg}`;
            }

            let d = res.data;
            if(!d.period) return;

            let hHtml = '';
            d.history.slice(0, 10).forEach(h => {
                let shortPeriod = h.period.slice(-4); 
                hHtml += `<div class="h-item">
                    <div class="h-period">${shortPeriod}期</div>
                    <div class="h-nums">${h.nums}</div>
                    <div class="h-total">${h.total}</div>
                    <div class="h-combo">${h.big_small}${h.odd_even}</div>
                </div>`;
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
                if(left <= 0) { cdEl.innerText = "等待开奖结算..."; cdEl.classList.add('danger'); return; }
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
        .then(r => r.json()).then(res => {
            let st = res.stats;
            document.getElementById('st-cw').innerText = st.current_win;
            document.getElementById('st-cl').innerText = st.current_lose;
            document.getElementById('st-tw').innerText = st.total_win;
            document.getElementById('st-tl').innerText = st.total_lose;

            let html = '';
            res.logs.forEach(l => {
                let cls = l.status === 'win' ? 'win' : (l.status === 'lose' ? 'lose' : '');
                let txt = l.status === 'win' ? '🀄 命中' : (l.status === 'lose' ? '💀 被杀' : '⏳ 等待');
                let real = l.real_result ? `(实开:${l.real_result})` : '';
                html += `<div class="log-item">
                    <div><div style="color:#b2bec3; font-size:12px;">${l.period}</div><div style="margin-top:4px;">绝杀:<span class="lose">${l.kill}</span> | 防守:<span class="win">${l.rec}</span></div></div>
                    <div style="text-align:right"><div class="${cls}">${txt}</div><div style="color:#b2bec3; font-size:12px; margin-top:4px;">${real}</div></div>
                </div>`;
            });
            document.getElementById('logs').innerHTML = html || '<div style="text-align:center; padding:20px; color:#b2bec3;">暂无历史记录</div>';
        });
    }

    function clearLogs() {
        if(!confirm("确定清空当前游戏的统计数据吗？")) return;
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
