进口urllib.request
进口SSL
进口JSON
进口时间
进口穿线
进口操作系统
进口再
进口sqlite3
进口Hashlib
进口随机
从……起烧瓶进口烧瓶，请求，jsonify，render_template_string
从……起datetime进口datetime，timedelta

app=烧瓶(__name__)

#==================[核心配置]==================
sign_SECRET="captain_ai_predict_v5_secure"
time_WINDOW=2.0 
DEEPSEEK_API_KEY="sk-43c18b39aeb346fc841937b30cade25b"
DEEPSEEK_API_URL="https://api.deepseek.com/chat/completions"

游戏={
    "2": {"名称": "加拿大28", "URL": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQQWERTYUIOPWW9983/8626/0549CASWWW?type=2", "间隔": 210},
    "3": {"名称": "分分28", "URL": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQASDFGHJKLWW9986/8626/0549CFKFGH?type=3", "间隔": 60},
    "13": {"名称": "比特28", "URL": "https://yc28cn-ml1l.onrender.com/vipASDFGHJKLQQZXCVBNMWW9983/8626/0549CCBDR?type=13", "间隔": 60}
}

# 全局实时数据与状态缓存
system_STATUS={
    "ai_connected": 假的,
    "last_ping": "未连接",
    "型号名称": "DeepSeek-V3(聊天)"
}

live_DATA={
    "2": {"句号": "", "next_period": "", "left_time": 0, "历史记录": [], "current_prediction": 没有一个, "ai_status": "等待同步"},
    "3": {"句号": "", "next_period": "", "left_time": 0, "历史记录": [], "current_prediction": 没有一个, "ai_status": "等待同步"},
    "13": {"句号": "", "next_period": "", "left_time": 0, "历史记录": [], "current_prediction": 没有一个, "ai_status": "等待同步"}
}

#==================数据库==================
定义 get_db():
Conn=sqlite3。连接('prediction.db'，timeout=30)
Conn.row_factory=sqlite3。行
Conn.执行("PRAGMA journal_mode=WAL；")
    返回Conn

定义 init_db():
    和……一起 get_db() 作为连接器：
Conn.执行("'如果不存在预测，则创建表(
ID整数主键自动增量，游戏类型文本，句点文本，
kill_item TEXT，recommend_items TEXT，analysis TEXT，actual_result TEXT DEFAULT"，
结果文本默认“挂起”，创建时间戳时默认当前时间戳
        )''')
Conn.犯罪()

init_db()

#================== AI接口探测==================
定义 Ping_deepseek():
    """探测DeepSeek API连通性"""
标题={"授权": F"轴承{DEEPSEEK_API_KEY}", "内容类型": "应用程序/json"}
数据={
        "型号": "deepseek-chat",
        "消息": [{"角色": "用户", "内容": "ping"}],
        "max_token": 1
    }
    尝试:
req=urllib。请求.请求(DEEPSEEK_API_URL，数据=json。转储(数据).编码('UTF-8')，headers=headers)
CTX=ssl._create_unverified_context()
        和……一起urllib。请求.urlopen(req，timeout=10，context=ctx) 作为RESP：
            如果RESP.状态==200:
system_STATUS["ai_connected"]=正确
system_STATUS["last_ping"]=日期时间。现在().strftime("%H：%M：%S")
                返回 正确
    除……之外例外：
system_STATUS["ai_connected"]=假的
system_STATUS["last_ping"]=F"连接失败{datetime。现在().strftime('%H：%M：%S')}"
        返回 假的

#================== AI深度推演核心==================
定义 询问以预测(游戏名称、历史数据、下期、上期预告):
    """调用DeepSeek进行全权接管预测"""
    # 构造历史数据
history_str=""
    为I，h在……内 列举(history_data[:7]):
history_str+=F"第{7-I}期:{h['Nums']}={h['总计']} ({h['big_small']}{h['奇数(_even)']})\n"
    
    # 构造复盘逻辑
过去结果=""
    如果last_prediction和last_prediction['结果']=='输':
过去结果=f"【紧急复盘】：上期预测大败，我们杀掉了[{last_prediction['终止项目(_item)']}]，但实际开出了[{last_prediction['actual_result']}]。 说明盘口诱多或长龙。 本次策略必须极度谨慎，或者立刻反杀/跟风！"
    Eliflast_prediction和last_prediction['结果']=='赢':
过去结果=f"【状态良好】：上期成功猎杀[{last_prediction['终止项目(_item)']}]。 请继续保持这种敏锐度。"

提示=f"""
你现在是全球顶级的博彩精算师、概率论大师和反博弈AI。 当前游戏盘口：{游戏名称}。
    请根据下面最近 7 期的开奖结果，深度预测第 {next_period} 期的走势。

    【近期开奖矩阵】
    {history_str}
    
    【上期战况】
    {past_result}
    
    【你的核心任务】
    1. 从【大单、大双、小单、小双】中，精准推导并绝杀掉 1 个概率最低、最危险的选项。
    2. 推荐剩下的 3 个选项作为安全防守区。
    3. 生成一段 80 到 500 字之间的深度硬核分析（必须基于真实走势数据，不得使用废话模板，要求逻辑严密，像真正的人类精算师在分析盘口）。
    
    请直接输出纯JSON格式，不要使用 ```json 代码块，不要任何多余字符：
    {{
        "kill_item": "这里填杀掉的1项",
        "recommend_items": "另外3项用顿号隔开",
        "analysis": "【AI深度洞察】近期盘面呈现...（这里写分析内容）"
    }}
    """

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一个直接输出 JSON 的预测系统，绝对不要带任何多余的废话和 markdown 标记。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.8,
        "max_tokens": 800
    }

    try:
        req = urllib.request.Request(DEEPSEEK_API_URL, data=json.dumps(data).encode('utf-8'), headers=headers)
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            content = res_data['choices'][0]['message']['content'].strip()
            
            # 清理可能的 Markdown 杂项
            content = re.sub(r'```json', '', content)
            content = re.sub(r'```', '', content).strip()
            
            result_json = json.loads(content)
            SYSTEM_STATUS["ai_connected"] = True
            return {
                "period": next_period,
                "kill_item": result_json['kill_item'],
                "recommend_items": result_json['recommend_items'],
                "analysis": result_json['analysis']
            }
    except Exception as e:
        print(f"❌ {game_name} AI 接口异常: {e}")
        SYSTEM_STATUS["ai_connected"] = False
        return None

# ================== 抓取与结算 ==================
def settle_predictions(game_type, period, result_attr):
    with get_db() as conn:
        preds = conn.execute("SELECT * FROM predictions WHERE game_type=? AND period=? AND result='pending'", (game_type, period)).fetchall()
        for p in preds:
            status = 'win' if result_attr != p['kill_item'] else 'lose'
            conn.execute("UPDATE predictions SET result=?, actual_result=? WHERE id=?", (status, result_attr, p['id']))
        conn.commit()

def fetch_loop():
    ctx = ssl._create_unverified_context()
    # 启动时探测一次接口
    ping_deepseek()
    
    while True:
        for g_type, cfg in GAMES.items():
            try:
                req = urllib.request.Request(cfg['url'], headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    if data.get('data'):
                        latest_data = data['data']
                        latest = latest_data[0]
                        
                        history = []
                        for item in latest_data[:20]:
                            history.append({
                                "period": item['period'], "total": item['total'], 
                                "nums": f"{item['num1']}+{item['num2']}+{item['num3']}",
                                "big_small": item['big_small'], "odd_even": item['odd_even']
                            })
                        
                        if LIVE_DATA[g_type]['period'] != latest['period']:
                            if LIVE_DATA[g_type]['period'] != "":
                                attr = latest['big_small'] + latest['odd_even']
                                settle_predictions(g_type, latest['period'], attr)
                            
                            draw_dt = datetime.strptime(latest['draw_time'], "%Y-%m-%d %H:%M:%S")
                            target_utc = draw_dt - timedelta(hours=8) + timedelta(seconds=cfg['interval'])
                            
                            with get_db() as conn:
                                last_pred = conn.execute("SELECT * FROM predictions WHERE game_type=? ORDER BY id DESC LIMIT 1", (g_type,)).fetchone()
                            
                            # 标记状态为正在请求 AI
                            LIVE_DATA[g_type]['ai_status'] = "AI 演算中"
                            
                            # 异步请求 AI 预测
                            print(f"🚀 正在请求 {cfg['name']} 的 AI 深度推演...")
                            pred = ask_ai_to_predict(cfg['name'], history, str(int(latest['period']) + 1), last_pred)
                            
                            if pred:
                                with get_db() as conn:
                                    conn.execute('''INSERT INTO predictions (game_type, period, kill_item, recommend_items, analysis) 
                                                    VALUES (?, ?, ?, ?, ?)''', 
                                                 (g_type, pred['period'], pred['kill_item'], pred['recommend_items'], pred['analysis']))
                                    conn.commit()
                                LIVE_DATA[g_type]['current_prediction'] = pred
                                LIVE_DATA[g_type]['ai_status'] = "演算完成"
                                print(f"✅ {cfg['name']} AI预测完成：绝杀{pred['kill_item']}")
                            else:
                                LIVE_DATA[g_type]['ai_status'] = "AI 接口异常"
                                print(f"❌ {cfg['name']} 预测失败。")

                            LIVE_DATA[g_type]['period'] = latest['period']
                            LIVE_DATA[g_type]['next_period'] = str(int(latest['period']) + 1)
                            LIVE_DATA[g_type]['target_utc'] = target_utc.timestamp()
                            LIVE_DATA[g_type]['history'] = history
                            
                        diff = LIVE_DATA[g_type]['target_utc'] - datetime.utcnow().timestamp()
                        LIVE_DATA[g_type]['left_time'] = max(0, int(diff))
            except Exception:
                pass
        time.sleep(1)

threading.Thread(target=fetch_loop, daemon=True).start()

# ================== API 防护与状态接口 ==================
def verify_request():
    referer = request.headers.get('Referer', '')
    user_agent = request.headers.get('User-Agent', '')
    if 'onrender.com' not in referer and '127.0.0.1' not in referer:
        return False
    if 'Mozilla' not in user_agent and 'Chrome' not in user_agent:
        return False
    req_time_str = request.headers.get('X-Req-Time', '')
    req_sign = request.headers.get('X-Req-Sign', '')
    if not req_time_str or not req_sign:
        return False
    try:
        req_time = float(req_time_str) / 1000.0
        if abs(time.time() - req_time) > TIME_WINDOW:
            return False
    except ValueError:
        return False
    expected_sign = hashlib.md5(f"{req_time_str}{SIGN_SECRET}".encode('utf-8')).hexdigest()
    if req_sign != expected_sign:
        return False
    return True

def hacker_trap():
    return """
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { background: #000; margin: 0; overflow: hidden; display: flex; justify-content: center; align-items: center; height: 100vh; font-family: monospace; }
        @keyframes jump {
            0%, 100% { transform: translateY(0); text-shadow: 0 0 20px red; color: red; }
            50% { transform: translateY(-30px); text-shadow: 0 0 50px red, 0 0 10px white; color: #ffcccc; }
        }
        .msg { font-size: 32px; font-weight: bold; text-align: center; line-height: 1.6; animation: jump 0.3s infinite; word-break: break-all; padding: 20px; }
    </style></head>
    <body><div class="msg">人机你这个 fw<br>学好计算机技术才有资格来套取我的 API 接口😂😂😂😂😂😂</div></body></html>
    """

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/api/v10/sys/ai_sync/status')
def api_status():
    if not verify_request():
        return hacker_trap(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    # 返回全局状态
    return jsonify({
        "connected": SYSTEM_STATUS["ai_connected"],
        "last_ping": SYSTEM_STATUS["last_ping"],
        "model": SYSTEM_STATUS["model_name"]
    })

@app.route('/api/v10/sys/ai_sync/live/<g_type>')
def api_live(g_type):
    if not verify_request():
        return hacker_trap(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    return jsonify(LIVE_DATA.get(g_type, {}))

@app.route('/api/v10/sys/ai_sync/records/<g_type>')
def api_predictions(g_type):
    if not verify_request():
        return hacker_trap(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    with get_db() as conn:
        preds = conn.execute("SELECT * FROM predictions WHERE game_type=? ORDER BY id DESC LIMIT 30", (g_type,)).fetchall()
    return jsonify([dict(p) for p in preds])

@app.route('/api/v10/sys/ai_sync/delete/<g_type>', methods=['POST'])
def delete_preds(g_type):
    if not verify_request():
        return hacker_trap(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    with get_db() as conn:
        conn.execute("DELETE FROM predictions WHERE game_type=?", (g_type,))
        conn.commit()
    return jsonify({"success": True})

# ================== 纯白 AI 控制台前端 ==================
HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>AI 深度预测终端</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; }
        body { background: #f5f7fa; color: #333; min-height: 100vh; padding-bottom: 30px; }
        
        /* 顶部 AI 状态面板 */
        .ai-header { background: #fff; padding: 15px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 10px rgba(0,0,0,0.03); margin-bottom: 15px;}
        .ai-info { display: flex; flex-direction: column; gap: 4px; }
        .ai-model { font-size: 16px; font-weight: bold; color: #1a1a1a; display: flex; align-items: center; gap: 8px;}
        .ai-model span { font-size: 10px; background: #e6f7ff; color: #1890ff; padding: 2px 6px; border-radius: 4px; border: 1px solid #91d5ff;}
        .ai-status { font-size: 12px; color: #888; }
        .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }
        .status-dot.online { background: #52c41a; box-shadow: 0 0 5px #52c41a; }
        .status-dot.offline { background: #ff4d4f; }

        .tabs { display: flex; padding: 0 15px; gap: 10px; margin-bottom: 15px; }
        .tab-btn { flex: 1; background: #fff; border: 1px solid #e0e0e0; color: #666; padding: 12px 0; text-align: center; cursor: pointer; transition: all 0.2s; font-size: 15px; font-weight: bold; border-radius: 8px; }
        .tab-btn.active { border-color: #1890ff; color: #fff; background: #1890ff; box-shadow: 0 4px 10px rgba(24,144,255,0.2); }

        .card { background: #fff; border-radius: 12px; margin: 0 15px 15px 15px; padding: 15px; box-shadow: 0 2px 12px rgba(0,0,0,0.04); }
        .card-title { font-size: 15px; font-weight: bold; color: #333; margin-bottom: 12px; display: flex; align-items: center; }
        .card-title::before { content: ''; display: inline-block; width: 4px; height: 16px; background: #1890ff; border-radius: 2px; margin-right: 8px; }

        .history-scroll { display: flex; overflow-x: auto; gap: 10px; padding-bottom: 5px; }
        .history-scroll::-webkit-scrollbar { height: 4px; }
        .history-scroll::-webkit-scrollbar-thumb { background: #ccc; border-radius: 2px; }
        .h-item { min-width: 75px; background: #fafafa; border: 1px solid #eee; padding: 10px; text-align: center; border-radius: 8px; font-size: 12px; }
        .h-item .nums { color: #333; font-weight: bold; margin: 4px 0; font-size: 14px;}
        .h-item .attr { color: #ff4d4f; font-weight: bold; }

        .pred-box { background: linear-gradient(180deg, #f0f7ff 0%, #fff 100%); border: 1px solid #bae0ff; padding: 25px 20px; text-align: center; }
        .target-period { font-size: 16px; color: #666; margin-bottom: 15px; font-weight: bold; }
        .target-period span { color: #1890ff; font-size: 20px; }
        
        .kill-item { font-size: 28px; font-weight: bold; color: #ff4d4f; margin-bottom: 12px; background: #fff1f0; padding: 10px; border-radius: 8px; border: 1px dashed #ffa39e; }
        .rec-items { font-size: 24px; font-weight: bold; color: #52c41a; margin-bottom: 20px; background: #f6ffed; padding: 10px; border-radius: 8px; border: 1px dashed #b7eb8f; }
        
        .countdown { font-size: 15px; color: #666; margin-bottom: 20px; background: #fafafa; padding: 10px; border-radius: 8px; display: inline-block;}
        .countdown span { font-size: 22px; font-weight: bold; color: #1890ff; }
        
        @keyframes redFlash { 0%, 100% { color: #ff4d4f; opacity: 1; } 50% { color: #cf1322; opacity: 0.5; } }
        .countdown.danger span { animation: redFlash 0.5s infinite; color: #ff4d4f; }

        .analysis { text-align: left; font-size: 14px; line-height: 1.8; color: #333; background: #fcfcfc; padding: 15px; border-radius: 8px; border-left: 3px solid #1890ff; }

        .btn-del { background: #fff; border: 1px solid #ff4d4f; color: #ff4d4f; padding: 6px 12px; cursor: pointer; font-size: 12px; border-radius: 6px; float: right; margin-top: -28px;}
        .btn-del:active { background: #ff4d4f; color: #fff; }

        .record-list { max-height: 400px; overflow-y: auto; }
        .record-item { display: flex; justify-content: space-between; align-items: center; padding: 12px; border-bottom: 1px solid #f0f0f0; font-size: 14px; }
        .record-item:last-child { border-bottom: none; }
        .record-item.win { background: #f6ffed; border-radius: 6px; margin-bottom: 5px; border: 1px solid #d9f7be; }
        .record-item.lose { background: #fff1f0; border-radius: 6px; margin-bottom: 5px; border: 1px solid #ffccc7; }
        
        .r-left { display: flex; flex-direction: column; gap: 6px; }
        .r-period { color: #888; font-size: 12px; font-weight: bold;}
        .r-kill { color: #ff4d4f; font-weight: bold;}
        .r-rec { color: #52c41a; font-weight: bold;}
        .r-actual { color: #d48806; font-weight: bold; }
        .r-status { font-size: 16px; font-weight: bold; text-align: right; }
        .r-status .sub-text { font-size: 12px; color: #888; font-weight: normal; margin-top: 4px;}
    </style>
</head>
<body>
    <!-- 顶部 AI 监控 -->
    <div class="ai-header">
        <div class="ai-info">
            <div class="ai-model">DeepSeek 算力中枢 <span>大模型</span></div>
            <div class="ai-status" id="api-status">
                <span class="status-dot offline"></span> 正在探测接口...
            </div>
        </div>
        <div style="text-align:right; font-size:12px; color:#888;">
            <div>API 握手:</div>
            <div id="api-ping-time" style="font-weight:bold; color:#333;">--:--:--</div>
        </div>
    </div>

    <div class="tabs">
        <div class="tab-btn active" onclick="switchGame('2', this)">加拿大28</div>
        <div class="tab-btn" onclick="switchGame('3', this)">分分28</div>
        <div class="tab-btn" onclick="switchGame('13', this)">比特28</div>
    </div>

    <div class="card">
        <div class="card-title">近 20 期 走势矩阵</div>
        <div class="history-scroll" id="history-box"></div>
    </div>

    <div class="card pred-box" id="pred-box" style="display:none;">
        <div class="target-period">目标拦截期号: <span id="target-period">--</span></div>
        <div class="kill-item">🚫 AI绝杀: <span id="kill-item">--</span></div>
        <div class="rec-items">✅ AI推荐防守: <span id="rec-items">--</span></div>
        <div class="countdown" id="cd-box">距开奖结算: <span id="countdown">--:--</span></div>
        <div class="analysis" id="analysis-text">DeepSeek 正在深度思考推演...</div>
    </div>

    <div class="card">
        <div class="card-title">历史复盘记录 (带实开)</div>
        <button class="btn-del" onclick="clearRecords()">清空记录</button>
        <div class="record-list" id="record-list"></div>
    </div>

    <script>
        const SECRET_KEY = "captain_ai_predict_v5_secure";
        const API_BASE = "/api/v10/sys/ai_sync"; 
        let currentGame = '2';
        let liveData = null;
        let timer = null;

        function getHeaders() {
            const timeStamp = Date.now().toString();
            const sign = md5(timeStamp + SECRET_KEY);
            return { 'X-Req-Time': timeStamp, 'X-Req-Sign': sign };
        }

        function md5(string) {
            function rotateLeft(lValue, iShiftBits) { return (lValue << iShiftBits) | (lValue >>> (32 - iShiftBits)); }
            function addUnsigned(lX, lY) { var lX4, lY4, lX8, lY8, lResult; lX8 = (lX & 0x80000000); lY8 = (lY & 0x80000000); lX4 = (lX & 0x40000000); lY4 = (lY & 0x40000000); lResult = (lX & 0x3FFFFFFF) + (lY & 0x3FFFFFFF); if (lX4 & lY4) { return (lResult ^ 0x80000000 ^ lX8 ^ lY8); } if (lX4 | lY4) { if (lResult & 0x40000000) { return (lResult ^ 0xC0000000 ^ lX8 ^ lY8); } else { return (lResult ^ 0x40000000 ^ lX8 ^ lY8); } } else { return (lResult ^ lX8 ^ lY8); } }
            function F(x, y, z) { return (x & y) | ((~x) & z); }
            function G(x, y, z) { return (x & z) | (y & (~z)); }
            function H(x, y, z) { return (x ^ y ^ z); }
            function I(x, y, z) { return (y ^ (x | (~z))); }
            function FF(a, b, c, d, x, s, ac) { a = addUnsigned(a, addUnsigned(addUnsigned(F(b, c, d), x), ac)); return addUnsigned(rotateLeft(a, s), b); }
            function GG(a, b, c, d, x, s, ac) { a = addUnsigned(a, addUnsigned(addUnsigned(G(b, c, d), x), ac)); return addUnsigned(rotateLeft(a, s), b); }
            function HH(a, b, c, d, x, s, ac) { a = addUnsigned(a, addUnsigned(addUnsigned(H(b, c, d), x), ac)); return addUnsigned(rotateLeft(a, s), b); }
            function II(a, b, c, d, x, s, ac) { a = addUnsigned(a, addUnsigned(addUnsigned(I(b, c, d), x), ac)); return addUnsigned(rotateLeft(a, s), b); }
            function convertToWordArray(string) {
                var lWordCount; var lMessageLength = string.length; var lNumberOfWords_temp1 = lMessageLength + 8; var lNumberOfWords_temp2 = (lNumberOfWords_temp1 - (lNumberOfWords_temp1 % 64)) / 64; var lNumberOfWords = (lNumberOfWords_temp2 + 1) * 16; var lWordArray = Array(lNumberOfWords - 1); var lBytePosition = 0; var lByteCount = 0;
                while (lByteCount < lMessageLength) { lWordCount = (lByteCount - (lByteCount % 4)) / 4; lBytePosition = (lByteCount % 4) * 8; lWordArray[lWordCount] = (lWordArray[lWordCount] | (string.charCodeAt(lByteCount) << lBytePosition)); lByteCount++; }
                lWordCount = (lByteCount - (lByteCount % 4)) / 4; lBytePosition = (lByteCount % 4) * 8; lWordArray[lWordCount] = lWordArray[lWordCount] | (0x80 << lBytePosition); lWordArray[lNumberOfWords - 2] = lMessageLength << 3; lWordArray[lNumberOfWords - 1] = lMessageLength >>> 29; return lWordArray;
            }
            function wordToHex(lValue) { var WordToHexValue = "", WordToHexValue_temp = "", lByte, lCount; for (lCount = 0; lCount <= 3; lCount++) { lByte = (lValue >>> (lCount * 8)) & 255; WordToHexValue_temp = "0" + lByte.toString(16); WordToHexValue = WordToHexValue + WordToHexValue_temp.substr(WordToHexValue_temp.length - 2, 2); } return WordToHexValue; }
            var x = Array(); var k, AA, BB, CC, DD, a, b, c, d; var S11 = 7, S12 = 12, S13 = 17, S14 = 22; var S21 = 5, S22 = 9, S23 = 14, S24 = 20; var S31 = 4, S32 = 11, S33 = 16, S34 = 23; var S41 = 6, S42 = 10, S43 = 15, S44 = 21;
            string = unescape(encodeURIComponent(string)); x = convertToWordArray(string); a = 0x67452301; b = 0xEFCDAB89; c = 0x98BADCFE; d = 0x10325476;
            for (k = 0; k < x.length; k += 16) {
                AA = a; BB = b; CC = c; DD = d;
                a = FF(a, b, c, d, x[k + 0], S11, 0xD76AA478); d = FF(d, a, b, c, x[k + 1], S12, 0xE8C7B756); c = FF(c, d, a, b, x[k + 2], S13, 0x242070DB); b = FF(b, c, d, a, x[k + 3], S14, 0xC1BDCEEE); a = FF(a, b, c, d, x[k + 4], S11, 0xF57C0FAF); d = FF(d, a, b, c, x[k + 5], S12, 0x4787C62A); c = FF(c, d, a, b, x[k + 6], S13, 0xA8304613); b = FF(b, c, d, a, x[k + 7], S14, 0xFD469501);
                a = FF(a, b, c, d, x[k + 8], S11, 0x698098D8); d = FF(d, a, b, c, x[k + 9], S12, 0x8B44F7AF); c = FF(c, d, a, b, x[k + 10], S13, 0xFFFF5BB1); b = FF(b, c, d, a, x[k + 11], S14, 0x895CD7BE); a = FF(a, b, c, d, x[k + 12], S11, 0x6B901122); d = FF(d, a, b, c, x[k + 13], S12, 0xFD987193); c = FF(c, d, a, b, x[k + 14], S13, 0xA679438E); b = FF(b, c, d, a, x[k + 15], S14, 0x49B40821);
                a = GG(a, b, c, d, x[k + 1], S21, 0xF61E2562); d = GG(d, a, b, c, x[k + 6], S22, 0xC040B340); c = GG(c, d, a, b, x[k + 11], S23, 0x265E5A51); b = GG(b, c, d, a, x[k + 0], S24, 0xE9B6C7AA); a = GG(a, b, c, d, x[k + 5], S21, 0xD62F105D); d = GG(d, a, b, c, x[k + 10], S22, 0x2441453); c = GG(c, d, a, b, x[k + 15], S23, 0xD8A1E681); b = GG(b, c, d, a, x[k + 4], S24, 0xE7D3FBC8);
                a = GG(a, b, c, d, x[k + 9], S21, 0x21E1CDE6); d = GG(d, a, b, c, x[k + 14], S22, 0xC33707D6); c = GG(c, d, a, b, x[k + 3], S23, 0xF4D50D87); b = GG(b, c, d, a, x[k + 8], S24, 0x455A14ED); a = GG(a, b, c, d, x[k + 13], S21, 0xA9E3E905); d = GG(d, a, b, c, x[k + 2], S22, 0xFCEFA3F8); c = GG(c, d, a, b, x[k + 7], S23, 0x676F02D9); b = GG(b, c, d, a, x[k + 12], S24, 0x8D2A4C8A);
                a = HH(a, b, c, d, x[k + 5], S31, 0xFFFA3942); d = HH(d, a, b, c, x[k + 8], S32, 0x8771F681); c = HH(c, d, a, b, x[k + 11], S33, 0x6D9D6122); b = HH(b, c, d, a, x[k + 14], S34, 0xFDE5380C); a = HH(a, b, c, d, x[k + 1], S31, 0xA4BEEA44); d = HH(d, a, b, c, x[k + 4], S32, 0x4BDECFA9); c = HH(c, d, a, b, x[k + 7], S33, 0xF6BB4B60); b = HH(b, c, d, a, x[k + 10], S34, 0xBEBFBC70);
                a = HH(a, b, c, d, x[k + 13], S31, 0x289B7EC6); d = HH(d, a, b, c, x[k + 0], S32, 0xEAA127FA); c = HH(c, d, a, b, x[k + 3], S33, 0xD4EF3085); b = HH(b, c, d, a, x[k + 6], S34, 0x4881D05); a = HH(a, b, c, d, x[k + 9], S31, 0xD9D4D039); d = HH(d, a, b, c, x[k + 12], S32, 0xE6DB99E5); c = HH(c, d, a, b, x[k + 15], S33, 0x1FA27CF8); b = HH(b, c, d, a, x[k + 2], S34, 0xC4AC5665);
                a = II(a, b, c, d, x[k + 0], S41, 0xF4292244); d = II(d, a, b, c, x[k + 7], S42, 0x432AFF97); c = II(c, d, a, b, x[k + 14], S43, 0xAB9423A7); b = II(b, c, d, a, x[k + 5], S44, 0xFC93A039); a = II(a, b, c, d, x[k + 12], S41, 0x655B59C3); d = II(d, a, b, c, x[k + 3], S42, 0x8F0CCC92); c = II(c, d, a, b, x[k + 10], S43, 0xFFEFF47D); b = II(b, c, d, a, x[k + 1], S44, 0x85845DD1);
                a = II(a, b, c, d, x[k + 8], S41, 0x6FA87E4F); d = II(d, a, b, c, x[k + 15], S42, 0xFE2CE6E0); c = II(c, d, a, b, x[k + 6], S43, 0xA3014314); b = II(b, c, d, a, x[k + 13], S44, 0x4E0811A1); a = II(a, b, c, d, x[k + 4], S41, 0xF7537E82); d = II(d, a, b, c, x[k + 11], S42, 0xBD3AF235); c = II(c, d, a, b, x[k + 2], S43, 0x2AD7D2BB); b = II(b, c, d, a, x[k + 9], S44, 0xEB86D391);
                a = addUnsigned(a, AA); b = addUnsigned(b, BB); c = addUnsigned(c, CC); d = addUnsigned(d, DD);
            }
            var temp = wordToHex(a) + wordToHex(b) + wordToHex(c) + wordToHex(d);
            return temp.toLowerCase();
        }

        function checkStatus() {
            fetch(`${API_BASE}/status`, { headers: getHeaders() })
            .then(r=>r.json()).then(d => {
                let el = document.getElementById('api-status');
                let pingEl = document.getElementById('api-ping-time');
                if(d.connected) {
                    el.innerHTML = `<span class="status-dot online"></span> 模型已连接 (${d.model})`;
                    pingEl.innerText = d.last_ping;
                } else {
                    el.innerHTML = `<span class="status-dot offline"></span> 接口连接断开/异常`;
                }
            }).catch(e => {});
        }

        function switchGame(type, btn) {
            if(currentGame === type) return;
            currentGame = type;
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('pred-box').style.display = 'none';
            document.getElementById('history-box').innerHTML = '';
            document.getElementById('record-list').innerHTML = '';
            fetchLive();
            fetchRecords();
        }

        function fetchLive() {
            fetch(`${API_BASE}/live/${currentGame}`, { headers: getHeaders() })
            .then(r=>{
                if(r.headers.get('Content-Type').includes('text/html')) return r.text();
                return r.json();
            }).then(d => {
                if(typeof d === 'string') { document.body.innerHTML = d; return; }
                if(!d.period) return;
                liveData = d;
                
                let hHtml = '';
                d.history.forEach(item => {
                    let attr = item.big_small + item.odd_even;
                    hHtml += `
                        <div class="h-item">
                            <div style="color:#888; font-size:12px;">${item.period.slice(-3)}期</div>
                            <div class="nums">${item.nums}</div>
                            <div style="color:#666; font-size:12px;">=${item.total}</div>
                            <div class="attr">${attr}</div>
                        </div>
主办=
});
</html>
                
if(d.current_prediction){
文件。getElementById('pred-box')。风格。显示='块'；
文件。getElementById('target-period')。Inertext=d。current_prediction。周期；
文件。getElementById('kill-item').inertext=d.current_prediction.kill_item；
文件。getElementById('rec-items').inertext=d.current_prediction.commary_items；
文件。getElementById('analysis-text')。inertext=d。current_prediction。分析；
}else if(d.ai_status==="AI演算中"){
文件。getElementById('pred-box')。风格。显示='块'；
文件。getElementById('target-period')。内部文本=d.next_period||"--"；
文件。getElementById('kill-item').inertext="算力读取中..."；
文件。getElementById('rec-items').inertext="等待推导..."；
文件。getElementById('analysis-text').inertext="DeepSeek大模型正在接管盘面，进行深度概率演算与博弈推演，请稍候..."；
                }
                
if(定时器)clearInterval(定时器)；
let left=d.left_time；
让CDBOX=document.getElementById('CD-box')；
让cdSpan=document.getElementById('downstalization')；
                
timer=setInterval(()=>{
if(left<=0){cdSpan.innerText="结算中..."；返回；}
左--；
设m=数学floor(左/60)；
设s=左%60；
cdSpan.inertext='${m。toString().padStart(2，"0")}：${s。toString().padStart(2，"0")}'；
                    
if(left<=10){cdBox.classList.add('danger')；}
else{cdBox.classList.remove('danger')；}
}, 1000);
            });
        }

函数fetchRecords(){
获取("${API_BASE}/records/${currentGame}"，{headers:getHeaders()})
.then(r=>{
if(r.标头。取得('Content-Type').包含('text/html'))return r.text()；
return r.json()；
}).then(data=>{
if(typeof data==='string'){document。身体。innerHTML=数据；返回；}
let box=document.getElementById('record-list')；
if(data.length===0){box.innerHTML='<div style="填充：20px；文本对齐：居中；颜色：#999；">暂无预测记录</div>'；return；}
                
让超文本标记语言="；
data.forEach(p=>{
让cls=p.结果==='win'？'win'：(p.结果==='lose'？'lose'：")；
让图标=p.结果==='赢'？'🀄 命中'：(p.结果==='lose'？'💀 被杀'：'彷徨等待')；
让颜色=p.结果==='win'？'#52c41a'：(p.结果==='损失’？'#ff4d4f'：'#999')；
让actual_display=p.actual_result？'(实开：${p.actual_result})'："；
                    
超文本标记语言+='
<div class="记录项${cls}">
<div class="r-left">
<div class="r-period">期号：${p.period}</div>
<div>杀灭：<span class="r-kill">${p.kill_item}</span>|推荐：<span class="r-rec">${p.rammend_items}</span></div>
</div>
<div class="r-status"style="color：${color}；">
${icon}
<div class="sub-text">${actual_display}</div>
</div>
</div>
`;
                });
box.innerHTML=html；
            });
        }

函数clearRecords(){
if(！ 确认("确定要清空本游戏的预测记录吗？ 此操作无副作用。")) 返回；
fetch('${API_BASE}/delete/${currentGame}'，{方法：'邮件'，标头：getHeaders()})
.then(r=>r.json()).then(d=>{
if(d.success)fetchRecords()；
            });
        }

checkStatus()；
fetchLive()；
fetchRecords()；
        
setInterval(checkStatus，10000)；//每10秒探测一次API存活
setInterval(fetchLive，2000)；
setInterval(fetchRecords，5000)；
</script>
</body>
</html>
"""

如果__姓名__=='__main__'：__name__=='__main__'：App.Runrun(主机='0.0.0.0'，端口=端口'0.0.0.0'，端口=端口，端口=端口：__名称__=='__主要的__'：
port=int(os.environ.get("PORT"，8888))int(os.环境。get("端口"，8888))
应用程序.运行运行(主机='0.0.0.0'，端口=端口'0.0.0.0'，端口=端口，端口=端口
