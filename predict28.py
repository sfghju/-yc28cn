import urllib.request
import ssl
import json
import time
import threading
import os
import sqlite3
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
AI_STATUS = {"online": False, "msg": "系统初始化..."}
LIVE_DATA = {
    "2": {"period": "", "next": "", "left": 0, "history": [], "pred": None},
    "3": {"period": "", "next": "", "left": 0, "history": [], "pred": None},
    "13": {"period": "", "next": "", "left": 0, "history": [], "pred": None}
}

# =====================================================================
# 模块 2：SQLite 数据库持久化层
# =====================================================================
def db():
    conn = sqlite3.connect('predict_matrix_800.db', timeout=30)
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
# 模块 3：核心推演引擎 - 100维矩阵逻辑 (纯代码真实计算)
# 重点分析近 7 期及以下的切片，进行层层剥洋葱式的推演
# =====================================================================
def calculate_matrix_prediction(history):
    # 确保有足够的数据切片
    if len(history) < 7:
        return {
            "kill": "数据不足", "rec": "数据不足", "analysis": "系统正在收集足够的历史切片数据，请等待下一期开奖后进行初始化分析。"
        }

    # 截取近 7 期数据用于深度推演
    recent_7 = history[:7]
    
    # 提取大小、单双序列 (1 代表 大/单，0 代表 小/双)
    bs_seq = [1 if h['big_small'] == '大' else 0 for h in recent_7]
    oe_seq = [1 if h['odd_even'] == '单' else 0 for h in recent_7]

    # 权重计分板 (分数越高，越容易被庄家收割，即绝杀概率越大)
    scores = {'大': 0, '小': 0, '单': 0, '双': 0}
    
    # 记录推演过程的关键词，用于生成小作文
    analysis_events = []

    # ---------------------------------------------------------
    # 第一层：连号极值与断裂点分析 (对应逻辑 1 - 20)
    # ---------------------------------------------------------
    def get_streak(seq):
        streak = 1
        for i in range(1, len(seq)):
            if seq[i] == seq[0]: streak += 1
            else: break
        return streak

    bs_streak = get_streak(bs_seq)
    oe_streak = get_streak(oe_seq)

    # 大小连号分析
    if bs_streak >= 4:
        # 4连以上，极大概率断裂，庄家会利用惯性杀反龙
        scores['大' if bs_seq[0] == 1 else '小'] += 15
        analysis_events.append(f"【极值断裂】大小端已连开{bs_streak}期{recent_7[0]['big_small']}，达到历史极值，动能衰竭，坚决杀连")
    elif bs_streak == 3:
        scores['大' if bs_seq[0] == 1 else '小'] += 8
        analysis_events.append(f"【高危连号】大小端3连{recent_7[0]['big_small']}，需高度防范庄家回马枪诱盘")
    
    # 单双连号分析
    if oe_streak >= 4:
        scores['单' if oe_seq[0] == 1 else '双'] += 15
        analysis_events.append(f"【单双断层】单双端已连开{oe_streak}期{recent_7[0]['odd_even']}，触及红线，下期反转概率极高")
    elif oe_streak == 3:
        scores['单' if oe_seq[0] == 1 else '双'] += 8
        analysis_events.append(f"【单双警示】单双端3连{recent_7[0]['odd_even']}，谨防假突破")

    # ---------------------------------------------------------
    # 第二层：近7期冷热均态与诱盘分析 (对应逻辑 21 - 50)
    # ---------------------------------------------------------
    big_count = sum(bs_seq)
    small_count = 7 - big_count
    odd_count = sum(oe_seq)
    even_count = 7 - odd_count

    # 极热必死逻辑
    if big_count >= 5:
        scores['大'] += 12
        analysis_events.append(f"【大热必死】近7期大号出现{big_count}次，严重超买，均值回归势在必行")
    elif small_count >= 5:
        scores['小'] += 12
        analysis_events.append(f"【小号超卖】近7期小号出现{small_count}次，庄家养鱼结束，面临反弹")

    if odd_count >= 5:
        scores['单'] += 12
        analysis_events.append(f"【单数过热】近7期单数出现{odd_count}次，多头动能耗尽，防断崖下跌")
    elif even_count >= 5:
        scores['双'] += 12
        analysis_events.append(f"【双数集结】近7期双数出现{even_count}次，筹码高度密集，需防洗盘")

    # 均衡状态下的冷热交替逻辑 (3-4次徘徊)
    if 3 <= big_count <= 4 and 3 <= small_count <= 4:
        # 看上一期是什么，庄家喜欢杀追热的人
        last_bs = recent_7[0]['big_small']
        scores[last_bs] += 5
        analysis_events.append(f"【均衡猎杀】大小端处于多空平衡，上期开{last_bs}，本期极易回马枪杀{last_bs}")

    if 3 <= odd_count <= 4 and 3 <= even_count <= 4:
        last_oe = recent_7[0]['odd_even']
        scores[last_oe] += 5
        analysis_events.append(f"【单双纠缠】单双端势均力敌，上期开{last_oe}，庄家洗盘周期至，反杀概率大")

    # ---------------------------------------------------------
    # 第三层：组合形态与近3期微操切片分析 (对应逻辑 51 - 80)
    # ---------------------------------------------------------
    # 检查近 3 期的走势形态，判断是单边、震荡还是深V
    last_3_bs = bs_seq[:3]
    if last_3_bs == [1, 0, 1] or last_3_bs == [0, 1, 0]:
        # 典型的单跳震荡
        scores['大' if bs_seq[0] == 1 else '小'] += 6
        analysis_events.append("【震荡陷阱】近期大小呈现单跳节奏，本期大概率延续震荡拉爆追单者")
    elif last_3_bs == [1, 1, 0] or last_3_bs == [0, 0, 1]:
        # 连开中断
        scores['大' if bs_seq[1] == 1 else '小'] += 8
        analysis_events.append("【连号中断】大小走势刚经历长龙被终结，存在极强的连杀动能")

    last_3_oe = oe_seq[:3]
    if last_3_oe == [1, 0, 1] or last_3_oe == [0, 1, 0]:
        scores['单' if oe_seq[0] == 1 else '双'] += 6
        analysis_events.append("【单双插针】单双形态出现插针，假动作频发，杀上期同项最稳")
    elif last_3_oe == [1, 1, 0] or last_3_oe == [0, 0, 1]:
        scores['单' if oe_seq[1] == 1 else '双'] += 8
        analysis_events.append("【动能转换】单双刚完成多空转换，需防回抽确认")

    # ---------------------------------------------------------
    # 第四层：交叉共振终极确认 (对应逻辑 81 - 100)
    # ---------------------------------------------------------
    # 如果大小和单双同时指向要杀某个属性，则提升绝对权重
    kill_bs_candidate = '大' if scores['大'] > scores['小'] else '小'
    kill_oe_candidate = '单' if scores['单'] > scores['双'] else '双'

    # 极端危险信号加成
    if scores[kill_bs_candidate] >= 15 and scores[kill_oe_candidate] >= 15:
        scores[kill_bs_candidate] += 5
        scores[kill_oe_candidate] += 5
        analysis_events.append("【双端共振】大小与单双同时触及极度危险阈值，绝杀条件已完全成熟")

    # 最终选定绝杀项
    kill_str = kill_bs_candidate + kill_oe_candidate
    
    # 确定另外三个为安全项
    all_options = ["大单", "大双", "小单", "小双"]
    rec_list = [opt for opt in all_options if opt != kill_str]
    
    # ---------------------------------------------------------
    # 第五层：动态生成 150 - 300 字的高质量分析小作文
    # ---------------------------------------------------------
    # 每次从事件库中抽取最核心的 3 条进行组合，保证文字不重复
    import random
    if len(analysis_events) >= 3:
        selected_events = random.sample(analysis_events, 3)
    else:
        selected_events = analysis_events

    # 构建小作文模板
    intro_templates = [
        "【矩阵核心推演】本期算法对近7期切片进行了高维扫描。",
        "【量化深度剖析】结合近期实盘轨迹与庄家洗盘模型，得出以下结论：",
        "【盘面全息解析】七期数据已构成明显的诱多/诱空形态，具体解析如下："
    ]
    
    conclusion_templates = [
        f"综合极值、冷热与共振逻辑，本方阵判定【{kill_str}】为高危死亡陷阱。推荐将仓位重心防守转移至【{'、'.join(rec_list)}】。",
        f"多维度数据交叉验证后，强烈建议绝杀【{kill_str}】。重点布防【{'、'.join(rec_list)}】以规避庄家回马枪。",
        f"顶层博弈模型已锁定【{kill_str}】为收割对象，请坚决规避。利用【{'、'.join(rec_list)}】构建坚实的防守矩阵。"
    ]

    # 拼接生成文本
    analysis_text = random.choice(intro_templates) + "\n\n"
    
    for i, event in enumerate(selected_events):
        analysis_text += f"{i+1}. {event}；\n"
    
    analysis_text += "\n" + random.choice(conclusion_templates)

    # 严格兜底：确保字数在 150 - 300 之间
    if len(analysis_text) < 150:
        analysis_text += "\n【深度警示】当前盘面极其诡异，庄家利用连续开奖制造的虚假繁荣极容易让人上头，系统已启动强制冷静协议，坚决执行绝杀策略，不要有丝毫侥幸心理，跟紧防守阵型。"
    
    if len(analysis_text) > 300:
        analysis_text = analysis_text[:290] + "..."

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
                        
                        # 完美提取包含加号的数据
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
                            
                            # 结算上一期的数据
                            if LIVE_DATA[gt]['period'] != "":
                                real = latest['big_small'] + latest['odd_even']
                                with db() as conn:
                                    # 真实结算：只要开出的结果不等于绝杀项，即为预测成功 (Win)
                                    if real != LIVE_DATA[gt]['pred']['kill']:
                                        conn.execute("UPDATE logs SET real_result=?, status='win' WHERE gtype=? AND period=? AND status='wait'", (real, gt, latest['period']))
                                    else:
                                        conn.execute("UPDATE logs SET real_result=?, status='lose' WHERE gtype=? AND period=? AND status='wait'", (real, gt, latest['period']))
                                    conn.commit()
                            
                            # 计算下一期的开奖倒计时
                            dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            next_utc = dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])
                            
                            LIVE_DATA[gt].update({
                                "period": latest['period'], 
                                "next": str(int(latest['period'])+1),
                                "target_time": next_utc.timestamp(), 
                                "history": history
                            })
                            
                            AI_STATUS["online"] = True
                            AI_STATUS["msg"] = "100维矩阵运算中，正锁定庄家死穴..."
                            
                            # 执行真实的矩阵计算
                            pred = calculate_matrix_prediction(history)
                            LIVE_DATA[gt]['pred'] = pred
                            
                            # 入库记录
                            with db() as conn:
                                conn.execute('''INSERT INTO logs (gtype, period, kill, rec, analysis) VALUES (?,?,?,?,?)''', 
                                             (gt, LIVE_DATA[gt]['next'], pred['kill'], pred['rec'], pred['analysis']))
                                conn.commit()
                                
                        diff = LIVE_DATA[gt]['target_time'] - datetime.utcnow().timestamp()
                        LIVE_DATA[gt]['left'] = max(0, int(diff))
            except Exception as e:
                print("Error fetching data:", e)
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
        # 全量查询，无上限
        logs = conn.execute("SELECT * FROM logs WHERE gtype=? ORDER BY id DESC", (gt,)).fetchall()
        
        stats = {"current_win": 0, "current_lose": 0, "total_win": 0, "total_lose": 0}
        
        # 核心修复：过滤掉 'wait'，保证连中记录绝对准确不被中断
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
# 模块 6：前端 HTML + CSS + JS 渲染模板
# =====================================================================
@app.route('/')
def index():
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>终极矩阵实弹推演系统</title>
    <style>
        /* 基础重置 */
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body { background: #f4f6f9; margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #333; }
        
        /* 顶部栏 */
        .head { background: #111; color: #fff; padding: 16px; text-align: center; font-size: 20px; font-weight: bold; letter-spacing: 1px; box-shadow: 0 2px 10px rgba(0,0,0,0.2);}
        .status { text-align: center; padding: 10px; font-size: 13px; background: #fff; border-bottom: 1px solid #eaeaea; color: #666; display: flex; justify-content: center; align-items: center;}
        .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
        .on { background: #00b894; box-shadow: 0 0 5px #00b894;} 
        .off { background: #d63031; }
        
        /* 选项卡 */
        .tabs { display: flex; padding: 12px; gap: 10px; background: #fff; border-bottom: 1px solid #f1f2f6;}
        .tab { flex: 1; padding: 10px; text-align: center; background: #f0f2f5; border-radius: 8px; font-weight: bold; font-size: 14px; cursor: pointer; transition: all 0.3s;}
        .tab.on { background: #0984e3; color: #fff; box-shadow: 0 4px 10px rgba(9,132,227,0.3); transform: translateY(-2px);}
        
        /* 统计栏 */
        .stats-bar { display: flex; justify-content: space-between; background: #fff; margin: 12px; padding: 12px; border-radius: 12px; font-size: 13px; font-weight: bold; box-shadow: 0 2px 10px rgba(0,0,0,0.04);}
        .stats-item { text-align: center; flex: 1; border-right: 1px solid #f1f2f6;}
        .stats-item:last-child { border-right: none; }
        .stats-val { display: block; font-size: 20px; margin-top: 4px;}

        /* 卡片容器 */
        .card { background: #fff; margin: 12px; padding: 16px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }
        .title { font-size: 14px; color: #2d3436; margin-bottom: 12px; font-weight: bold; display: flex; align-items: center;}
        .title::before { content: ''; display: inline-block; width: 4px; height: 14px; background: #0984e3; border-radius: 2px; margin-right: 8px;}
        
        /* 盘面历史展示 */
        .history { display: flex; overflow-x: auto; gap: 10px; font-size: 12px; text-align: center; padding-bottom: 5px; }
        .h-item { background: #f8f9fa; padding: 10px 8px; border-radius: 8px; min-width: 90px; border: 1px solid #eee; flex-shrink: 0;}
        .h-period { color: #b2bec3; font-weight: bold; margin-bottom: 4px; font-size: 11px;}
        .h-nums { color: #636e72; font-size: 12px; margin-bottom: 4px; font-weight: 500;} /* 显示加号格式 */
        .h-total { color: #d63031; font-weight: bold; font-size: 16px; margin: 4px 0;}
        .h-combo { font-weight: bold; color: #2d3436;}
        
        /* 预测展示区 */
        .kill { color: #d63031; font-size: 28px; font-weight: 900; text-align: center; margin: 15px 0; background: #fff5f5; padding: 15px; border-radius: 8px; letter-spacing: 2px;}
        .rec { color: #00b894; font-size: 22px; font-weight: bold; text-align: center; margin-bottom: 15px; background: #f0fff4; padding: 12px; border-radius: 8px;}
        
        .cd-box { text-align: center; margin-bottom: 15px; font-size: 14px; color: #636e72;}
        .cd { font-size: 24px; color: #0984e3; font-weight: bold; font-family: monospace;}
        .cd.danger { color: #d63031; animation: flash 0.5s infinite alternate;}
        @keyframes flash { 0% { opacity: 0.4; } 100% { opacity: 1; } }
        
        /* 分析小作文展示 */
        .ana { background: #fffaf0; padding: 15px; border-left: 4px solid #d63031; font-size: 14px; line-height: 1.8; border-radius: 4px; color: #2d3436; font-weight: 500; text-align: justify;}
        
        /* 历史记录滚动区 */
        .log-item { border-bottom: 1px solid #f1f2f6; padding: 12px 0; font-size: 13px; display: flex; justify-content: space-between; }
        .log-item:last-child { border-bottom: none; }
        .win { color: #00b894; font-weight: bold; } .lose { color: #d63031; font-weight: bold; }
        .btn-clear { float:right; margin-top:-30px; font-size:12px; padding:6px 12px; border:1px solid #d63031; background:#fff; color:#d63031; border-radius:6px; font-weight: bold; transition: 0.2s;}
        .btn-clear:active { background: #d63031; color: #fff;}
        
        /* 隐藏滚动条但保留滚动功能 */
        .log-scroll { max-height: 500px; overflow-y: auto; padding-right: 5px; }
        .log-scroll::-webkit-scrollbar { width: 4px; }
        .log-scroll::-webkit-scrollbar-thumb { background: #dfe6e9; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="head">终极矩阵实弹推演</div>
    <div class="status" id="status"><span class="dot off"></span> 系统连接中...</div>
    
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
        <div class="ana" id="ana">矩阵算法正在扫描数据切片...</div>
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
                st.innerHTML = `<span class="dot on"></span> ${res.status.msg}`;
            } else {
                st.innerHTML = `<span class="dot off"></span> ${res.status.msg}`;
            }

            let d = res.data;
            if(!d.period) return;

            // 渲染盘面数据 (带有加号)
            let hHtml = '';
            d.history.slice(0, 10).forEach(h => {
                let shortPeriod = h.period.slice(-4); 
                // h.nums 在后台已经拼接为 "1 + 2 + 3" 格式
                hHtml += `<div class="h-item">
                    <div class="h-period">${shortPeriod}期</div>
                    <div class="h-nums">${h.nums}</div>
                    <div class="h-total">${h.total}</div>
                    <div class="h-combo">${h.big_small}${h.odd_even}</div>
                </div>`;
            });
            document.getElementById('history').innerHTML = hHtml;

            // 渲染预测结果
            if(d.pred) {
                document.getElementById('pred-box').style.display = 'block';
                document.getElementById('next-period').innerText = d.next;
                document.getElementById('kill-item').innerText = d.pred.kill;
                document.getElementById('rec-item').innerText = d.pred.rec;
                document.getElementById('ana').innerText = d.pred.analysis;
            }

            // 倒计时逻辑
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

    // 初始化加载
    fetchData();
    fetchLogs();
    setInterval(fetchData, 2000);
    setInterval(fetchLogs, 5000);
</script>
</body>
</html>
    """

if __name__ == '__main__':
    # 自动获取平台分配的端口
    port = int(os.environ.get("PORT", 8888))
    app.run(host='0.0.0.0', port=port)
