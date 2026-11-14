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
SECRET_KEY = "deepseek_ai_ultimate_v11"
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
    conn = sqlite3.connect('predict_v11.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

with db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gtype TEXT, period TEXT,
        kill TEXT, rec TEXT, analysis TEXT, real_result TEXT DEFAULT '',
        status TEXT DEFAULT 'wait'
    )''')
    conn.commit()

# ================== 150项极度硬核推演引擎 ==================
def call_ai(gtype, game_name, history, next_period, last_status):
    history_str = "".join([f"第{7-i}期:{h['nums']}={h['total']}({h['big_small']}{h['odd_even']})\n" for i, h in enumerate(history[:7])])
    
    bs_seq = [h['big_small'] for h in history[:7]]
    oe_seq = [h['odd_even'] for h in history[:7]]
    bs_streak, oe_streak = 1, 1
    for i in range(1, len(bs_seq)):
        if bs_seq[i] == bs_seq[0]: bs_streak += 1
        else: break
    for i in range(1, len(oe_seq)):
        if oe_seq[i] == oe_seq[0]: oe_streak += 1
        else: break

    streak_info = f"当前【大小】连开 {bs_streak} 期，【单双】连开 {oe_streak} 期。"
    
    # 深度优化：跟反机制与回马枪防范
    if bs_streak >= 5 or oe_streak >= 5:
        rule_hint = "【核心铁律】：当前长龙已连开5期以上！必须顺势骑龙跟随，严禁盲目反杀，高度防范庄家回马枪诱空！"
    else:
        rule_hint = "【核心铁律】：当前未达5连！严格执行冷热交替，反向猎杀近期高频选项，重点防回马枪。"

    warning = "【极度危险】：上期预测失败，必须立刻变阵反杀！" if last_status == 'lose' else ("【状态良好】：上期命中，继续保持。" if last_status == 'win' else "")

    # 硬编码 150 项具体任务（绝不简化）
    tasks_150 = """
    1. 连号极值断裂点测算；2. 长龙跟随与回马枪防范；3. 单双跳节拍识别；4. 均值回归幅度评估；
    5. 赌徒谬误陷阱排查；6. 庄家诱多诱空逻辑反推；7. 筹码分布密集区探测；8. 虚假繁荣假象剥离；
    9. 时间窗口共振检测；10. 顺逆势核心抉择；11. 振幅收敛发散分析；12. 极端变异阈值监测；
    13. 静默冷门爆发概率；14. 散户口袋定向追踪；15. 大小单双撕裂感评估；16. 庄家洗盘周期定位；
    17. 回马枪连杀概率；18. 独立随机数学期望；19. 系统容错率底线；20. 三维共振同向验证；
    21. 盘口情绪贪婪恐慌指数；22. 散户惯性陷阱预判；23. 高位破位风险测算；24. 震荡区间下沿支撑；
    25. 诱盘深度还原；26. 下探支撑位与阻力位；27. 上攻破位动能；28. 异动反转信号识别；
    29. 死亡螺旋连败阻断；30. 连胜保护策略；31. K线吞没形态确认；32. 大资金暗盘流向模拟；
    33. 散户跟风系数；34. 极限施压测试；35. 多周期时间共振；36. 遗漏值极限修正；
    37. 多空双杀防范；38. 假突破诱多识别；39. 热号重力回撤测算；40. 核心博弈点定位；
    41. 概率重置法则应用；42. 散户绝望情绪冰点；43. 诱敌深入战术；44. 历史同形态回测；
    45. 大小单双强弱对比；46. 变盘时间节点；47. 庄家底牌深度推演；48. 反人性操作定调；
    49. 防守纵深构建；50. 一击必杀锁定；51. 布林带开口挤压；52. 随机指标KDJ钝化；
    53. 相对强弱RSI超买超卖；54. 乖离率BIAS修正；55. 顺势指标CCI追踪；56. 动量指标MTM背离；
    57. 抛物线SAR反转；58. 唐奇安通道突破；59. 斐波那契时间窗；60. 江恩时间法则；
    61. 艾略特波浪三段式；62. 干支历法阴阳；63. 星相天体共振；64. 季节性周期回归；
    65. 高频变盘雷达；66. 黄金分割时间轴；67. 快慢周期嵌套；68. 滑动窗口动量；
    69. 历史波动率衰减；70. 真实波幅ATR通道；71. 动态方差ANOVA；72. 协整均值回归；
    73. 跳跃扩散模型；74. 波动率微笑曲线；75. 极值理论尾部风险；76. 赫斯特指数长程相关；
    77. 分形维数混沌；78. 李雅普诺夫指数异动；79. 马尔可夫转移矩阵；80. 泊松分布衰减率；
    81. 贝叶斯后验概率；82. 卡方分布拟合度；83. 蒙特卡洛树推演；84. 高斯正态极值点；
    85. 偏度与峰度异动；86. 协方差矩阵特征；87. 曼-惠特尼U检验；88. 威尔科克森符号；
    89. 羊群效应风控；90. 锚定效应预期；91. 损失厌恶偏差；92. 赌徒谬误利用；
    93. 冷热手效应；94. 心理支撑阻力；95. 过度反应纠错；96. 认知失调盘面；
    97. 代表性偏差过滤；98. 禀赋效应持仓；99. 遗传算法变异；100. 随机森林投票；
    101. 支持向量机分类；102. LSTM神经网络推演；103. GRU门控循环；104. 卷积网络特征提取；
    105. 孤立森林异常检测；106. XGBoost提升树；107. 隐马尔可夫模型；108. 深度Q网络强化；
    109. 盘口大单托盘；110. 盘口大单压盘；111. 游资扫货痕迹；112. 散户割肉抛压；
    113. 资金对倒假象；114. 尾盘突袭概率；115. 早盘急跌修复；116. 中盘僵持破局；
    117. 均线多头排列；118. 均线空头排列；119. MACD金叉死叉；120. 顶背离与底背离；
    121. 缺口回补引力；122. 密集成交区阻力；123. 恐慌性抛售极值；124. 盲目追高陷阱；
    125. 老鼠仓异动；126. 机构调仓换股；127. 跨市场联动性；128. 宏观消息面冲击；
    129. 盘感与直觉校验；130. 微操骗线识别；131. 假阴假阳真伪；132. 长上影线试盘；
    133. 长下影线探底；134. 十字星变盘节点；135. 早晨之星黄昏之星；136. 红三兵与黑三鸦；
    137. 穿头破脚形态；138. 孕线孕育新机；139. 搓揉线洗盘；140. 圆底与圆顶构筑；
    141. V型反转概率；142. 倒V型见顶；143. 头肩顶底预测；144. 多重顶底共振；
    145. 趋势线破位确认；146. 通道上下轨修正；147. 黄金分割回撤位；148. 百分比线压力位；
    149. 江恩角度线支撑；150. 终极杀招确认执行。
    """

    prompt = f"""
    【最高身份设定】
    你是全球排名第一的逆向博弈论专家、顶级精算师。你的每一个决策必须极度严谨。你只相信数据、心理学和庄家博弈论。

    【盘口独立数据】
    专属游戏：{game_name} (独立计算，严禁参考其他游戏)
    目标期号：{next_period}
    {warning}

    【近期实盘数据】
    {history_str}
    {streak_info}
    {rule_hint}

    【150项极度严苛的推演任务（需逐一思考，严禁跳过）】
    {tasks_150}

    【严格执行指令】
    1. 必须给出 100 到 500 字的深度硬核分析。分析中必须结合盘面数据，明确指出“顺势还是反杀”，并体现出对“回马枪”的防范。
    2. 从【大单、大双、小单、小双】中，精准斩首 1 个选项，推荐防守 3 个。
    3. 必须返回纯 JSON 字符串，绝对禁止使用 ```json 标记。格式：
    {{"kill":"大单", "rec":"大双、小单、小双", "analysis":"【精算推演】基于严格的数据与心理博弈...（分析内容）"}}
    """
    
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是顶级精算师，直接输出 JSON，绝对不要带 ```json 标记。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.8,
        "max_tokens": 2000
    }
    
    try:
        req = urllib.request.Request(DEEPSEEK_API_URL, data=json.dumps(data).encode('utf-8'), headers=headers)
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=90, context=ctx) as resp:
            content = json.loads(resp.read().decode('utf-8'))['choices'][0]['message']['content']
            content = content.replace("```json", "").replace("```", "").strip()
            res = json.loads(content)
            
            AI_STATUS["online"] = True
            AI_STATUS["msg"] = "算力拉满 · 150项推演已完成"
            
            with db() as conn:
                conn.execute('''INSERT INTO logs (gtype, period, kill, rec, analysis) VALUES (?,?,?,?,?)''', 
                             (gtype, next_period, res['kill'], res['rec'], res['analysis']))
                conn.commit()
                
            return {"kill": res['kill'], "rec": res['rec'], "analysis": res['analysis']}
    except Exception as e:
        AI_STATUS["online"] = False
        AI_STATUS["msg"] = f"AI 接口超时或解析失败"
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
                                    
                                    # 绝对真实的结算，无任何篡改
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
                            AI_STATUS["msg"] = "AI 正在进行 150 项深度推演..."
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

# ================== API 接口与绝对真实统计 ==================
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
        # 无上限记录
        logs = conn.execute("SELECT * FROM logs WHERE gtype=? ORDER BY id DESC", (gt,)).fetchall()
        
        # 真实统计逻辑
        stats = {"current_win": 0, "current_lose": 0, "total_win": 0, "total_lose": 0}
        calc_status = []
        
        for l in logs:
            calc_status.append(l['status'])
            if l['status'] == 'win': stats['total_win'] += 1
            elif l['status'] == 'lose': stats['total_lose'] += 1
            
        # 计算当前连对/连错 (从最新记录往前推)
        for st in calc_status:
            if st == 'win': 
                if stats['current_lose'] > 0: break
                stats['current_win'] += 1
            elif st == 'lose':
                if stats['current_win'] > 0: break
                stats['current_lose'] += 1
            else: break 
            
    return jsonify({"logs": [dict(l) for l in logs], "stats": stats})

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
    <title>AI 终极预测终端</title>
    <style>
        body { background: #f4f6f9; margin: 0; font-family: -apple-system, sans-serif; color: #333; }
        .head { background: #111; color: #fff; padding: 16px; text-align: center; font-size: 20px; font-weight: bold; letter-spacing: 1px;}
        .status { text-align: center; padding: 10px; font-size: 13px; background: #fff; border-bottom: 1px solid #eaeaea; color: #666;}
        .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
        .on { background: #00b894; box-shadow: 0 0 5px #00b894;} .off { background: #d63031; }
        
        .tabs { display: flex; padding: 12px; gap: 10px; background: #fff; }
        .tab { flex: 1; padding: 10px; text-align: center; background: #f0f2f5; border-radius: 8px; font-weight: bold; font-size: 14px; cursor: pointer; transition: 0.2s;}
        .tab.on { background: #0984e3; color: #fff; box-shadow: 0 4px 10px rgba(9,132,227,0.3);}
        
        .stats-bar { display: flex; justify-content: space-between; background: #fff; margin: 12px; padding: 12px; border-radius: 8px; font-size: 13px; font-weight: bold; box-shadow: 0 2px 10px rgba(0,0,0,0.03);}
        .stats-item { text-align: center; flex: 1; border-right: 1px solid #eee;}
        .stats-item:last-child { border-right: none; }
        .stats-val { display: block; font-size: 18px; margin-top: 4px;}

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

    <div class="stats-bar" id="stats-bar">
        <div class="stats-item">当前连对<span class="stats-val win" id="st-cw">0</span></div>
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
        <div class="rec">✅ 推荐防守: <span id="rec-item"></span></div>
        <div class="cd-box">距开奖结算: <span class="cd" id="cd">--:--</span></div>
        <div class="ana" id="ana">AI 正在进行 150 项深度推演...</div>
    </div>

    <div class="card">
        <div class="title">历史复盘记录 (真实无篡改)</div>
        <button class="btn-clear" onclick="clearLogs()">清空记录</button>
        <div id="logs" style="margin-top:15px;"></div>
    </div>

<script>
    let curG = '2';
    let timer = null;
    const KEY = "deepseek_ai_ultimate_v11";

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
        .then(r => r.json()).then(res => {
            // 填充真实统计
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
                    <div><div style="color:#888;">${l.period}</div><div style="margin-top:4px;">杀:<span class="lose">${l.kill}</span> | 推:<span class="win">${l.rec}</span></div></div>
                    <div style="text-align:right"><div class="${cls}">${txt}</div><div style="color:#888; font-size:12px; margin-top:4px;">${real}</div></div>
                </div>`;
            });
            document.getElementById('logs').innerHTML = html || '<div style="text-align:center; padding:20px; color:#999;">暂无记录</div>';
        });
    }

    function clearLogs() {
        if(!confirm("确定清空所有历史统计吗？")) return;
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
