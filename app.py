import streamlit as st
import google.generativeai as genai
from openai import OpenAI
import re

# --- 1. 页面配置 ---
st.set_page_config(
    page_title="物理青椒新春渡劫：房贷与KPI", 
    page_icon="💸", 
    layout="wide"
)

# --- 2. 核心系统指令 ---
PHYSICS_SYSTEM_PROMPT = """
你是一款名为《物理学青椒新春渡劫》的文字 RPG 引擎。
你的身份是**“非升即走考核制度的化身”**。
玩家是一名物理学青年教师（青椒），处于 Tenure-track（预聘期）最痛苦的阶段。

# ⚡ 语言风格 (春节凡尔赛版)
1. **财富羞辱**：强调“你虽然是博士，但工资不如送外卖的表弟”。
2. **环境描写**：多描写春节嘈杂、油腻的环境（麻将声、熊孩子），与你内心的高冷物理世界形成反差。
3. **字数控制**：剧情描述控制在 **150 字左右**。

# 核心数值 (每轮必须更新)
| 属性 | 当前值 | 物理学/社会学定义 |
| :--- | :--- | :--- |
| **学术尊严** | 100 | 初始为满。被问“一个月几千块”时大幅下降。 |
| **KPI 进度** | 0% | 达到 100% 才能上岸。 |
| **钱包熵值** | High | 初始为High(钱少)。 |

# 游戏循环机制
1. **剧情模式 (Normal)**：
   - 必须给出 **A/B/C** 选项。
2. **考核模式 (Quiz) -> [标签: QUIZ]**：
   - 触发标签 `[EVENT: QUIZ]`。
   - 场景：亲戚咨询奇葩民科问题。
   - 出一道物理相关的**单选题** (A/B/C)。
3. **BOSS 战 (Reviewer) -> [标签: BOSS]**：
   - 触发标签 `[EVENT: BOSS_BATTLE]`。
   - 场景：银行催款或考核预警。
   - **不给选项**，要求玩家写回复。
4. **结局判定 -> [标签: GAME_OVER]**：
   - 如果 **KPI进度 >= 100%** -> 成功结局 [GAME_OVER: SUCCESS]。
   - 如果 **学术尊严 <= 0** 或 **钱包熵值 reached Max** -> 失败结局 [GAME_OVER: FAILURE]。
   - 如果剧情进行超过 **15轮** -> 强制根据当前状态判定结局。

# 任务
描述窘迫场景 -> 更新数值 -> 根据指令生成标签或选项。
"""

# --- 3. 初始化状态 ---
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.game_started = False
    st.session_state.is_over = False
    st.session_state.ending_type = None
    st.session_state.final_report = ""
    st.session_state.round_count = 0
    st.session_state.mode = "NORMAL"

# --- 4. API 逻辑 (新增 Kimi 支持) ---
def get_ai_response(prompt, backend, temperature):
    try:
        # === Google Gemini ===
        if backend == "Google AI Studio (Gemini)":
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel(model_name="gemini-1.5-flash", system_instruction=PHYSICS_SYSTEM_PROMPT)
            if "gemini_chat" not in st.session_state: st.session_state.gemini_chat = model.start_chat(history=[])
            return st.session_state.gemini_chat.send_message(prompt, generation_config={"temperature": temperature}).text
        
        # === Kimi (Moonshot AI) ===
        elif backend == "Moonshot AI (Kimi)":
            client = OpenAI(
                api_key=st.secrets["MOONSHOT_API_KEY"], 
                base_url="https://api.moonshot.cn/v1"
            )
            full_msgs = [{"role": "system", "content": PHYSICS_SYSTEM_PROMPT}] + st.session_state.messages + [{"role": "user", "content": prompt}]
            return client.chat.completions.create(
                model="kimi-k2.5",  # Kimi 8k 模型
                messages=full_msgs, 
                temperature=temperature
            ).choices[0].message.content

        # === DeepSeek ===
        else: 
            client = OpenAI(
                api_key=st.secrets["DEEPSEEK_API_KEY"], 
                base_url="https://api.deepseek.com"
            )
            full_msgs = [{"role": "system", "content": PHYSICS_SYSTEM_PROMPT}] + st.session_state.messages + [{"role": "user", "content": prompt}]
            return client.chat.completions.create(
                model="deepseek-chat", 
                messages=full_msgs, 
                temperature=temperature
            ).choices[0].message.content

    except Exception as e:
        return f"🚨 API Error: {str(e)}"

# --- 5. 核心动作处理 (修复结局判定逻辑) ---
def handle_action(action_text, input_type="ACTION", display_text=None):
    # 1. 记录用户输入
    prefix_map = {
        "ACTION": "【抉择】",
        "QUIZ_ANSWER": "【辟谣】",
        "REBUTTAL": "【卑微求生】"
    }
    user_content = display_text if display_text else f"{prefix_map.get(input_type, '')} {action_text}"
    st.session_state.messages.append({"role": "user", "content": user_content})
    
    if input_type == "ACTION":
        st.session_state.round_count += 1
    
    # 状态重置
    if input_type in ["QUIZ_ANSWER", "REBUTTAL"]:
        st.session_state.mode = "NORMAL"

    # 2. 预判逻辑
    is_quiz_trigger = False
    is_boss_trigger = False
    
    if input_type == "ACTION" and not st.session_state.is_over:
        if st.session_state.round_count > 0:
            if st.session_state.round_count % 7 == 0:
                is_boss_trigger = True
            elif st.session_state.round_count % 3 == 0:
                is_quiz_trigger = True

    # 3. Prompt 构建 (核心修改区域)
    field = st.session_state.get("field", "理论物理")
    prompt = ""
    
    # 通用的结局检查后缀：告诉 AI 每一轮都要检查数值
    game_over_check_instruction = " (⚠️重要：回复前请先检查数值。如果【学术尊严<=0】或【钱包熵值Max】或【KPI>=100%】，请忽略其他指令，直接输出标签 `[GAME_OVER: SUCCESS]` 或 `[GAME_OVER: FAILURE]` 并撰写结局报告。否则继续执行：)"

    if input_type == "QUIZ_ANSWER":
        prompt = f"[ANSWER_QUIZ]: 我选了 {action_text}。请判定科普是否成功。{game_over_check_instruction} 若未结束，请用150字描写亲戚神态，恢复剧情，给出 A/B/C 选项。"
    
    elif input_type == "REBUTTAL":
        prompt = f"[GRADE: REBUTTAL]: {action_text}。请判定死线是否宽限。{game_over_check_instruction} 若未结束，恢复剧情，给出 A/B/C 选项。"
    
    else:
        # 强制轮次结束
        if st.session_state.round_count >= 15:
             prompt = f"{action_text} (系统指令：已达到最大轮次。请根据当前数值，直接生成最终结局。必须使用标签 `[GAME_OVER: SUCCESS]` 或 `[GAME_OVER: FAILURE]`，并给出总结报告。)"
        
        elif is_boss_trigger:
            prompt = f"{action_text} (系统指令：本轮是第 {st.session_state.round_count} 轮。{game_over_check_instruction} 若未结束，触发**生存危机**，使用标签 `[EVENT: BOSS_BATTLE]`，不要给选项。)"
        
        elif is_quiz_trigger:
            prompt = f"{action_text} (系统指令：本轮是第 {st.session_state.round_count} 轮。{game_over_check_instruction} 若未结束，触发**民科对线**，使用标签 `[EVENT: QUIZ]` 并出单选题。)"
        
        else:
            # 常规剧情：必须加上结局检查指令
            prompt = f"{action_text} (系统指令：{game_over_check_instruction} 若未结束，用 150 字描写物理青椒的窘迫，并给出 A/B/C 剧情选项。)"

    # 4. AI 推演
    loading_text = {
        "NORMAL": "正在计算同学的年终奖...",
        "QUIZ": "二大爷正在分享营销号视频...",
        "BOSS": "银行系统正在扣款..."
    }
    
    backend = st.session_state.get("backend_selection", "Google AI Studio (Gemini)")
    temperature = st.session_state.get("temperature_setting", 1.0)

    current_loading = loading_text.get(st.session_state.mode, "Loading...")
    with st.spinner(f"[{backend}] {current_loading}"):
        res = get_ai_response(prompt, backend, temperature)
    
    # 5. 逻辑检测
    # 增加一点鲁棒性：有时候 AI 会忘记冒号，或者大小写不一致
    if "[GAME_OVER" in res: 
        st.session_state.is_over = True
        # 提取报告文本
        clean_report = re.sub(r"\[GAME_OVER.*?\]", "", res).strip()
        st.session_state.final_report = clean_report
        
        if "SUCCESS" in res: st.session_state.ending_type = "SUCCESS"
        else: st.session_state.ending_type = "FAILURE"
    
    elif "[EVENT: BOSS_BATTLE]" in res:
        st.session_state.mode = "BOSS"
    elif "[EVENT: QUIZ]" in res:
        st.session_state.mode = "QUIZ"
    else:
        st.session_state.mode = "NORMAL"
    
    # 清洗文本用于展示
    clean_res = res
    clean_res = re.sub(r"\[GAME_OVER.*?\]", "", clean_res) # 对应的正则也要改宽泛一点
    clean_res = clean_res.replace("[EVENT: BOSS_BATTLE]", "")
    clean_res = clean_res.replace("[EVENT: QUIZ]", "")
    clean_res = clean_res.strip()

    if clean_res:
        st.session_state.messages.append({"role": "assistant", "content": clean_res})

# --- 6. 侧边栏 ---
with st.sidebar:
    st.header("📉 青椒生存控制台")
    # 更新了下拉菜单，加入 Moonshot AI
    st.session_state.backend_selection = st.selectbox(
        "算力赞助:", 
        ["DeepSeek", "Moonshot AI (Kimi)", "Google AI Studio (Gemini)"]
    )
    st.divider()
    
    st.session_state.temperature_setting = st.slider(
        "焦虑浓度 (Temperature)", 
        0.0, 1.5, 1.0, 0.1,
        help="0.1: 真实纪录片\n1.0: 黑色幽默\n1.5: 荒诞现实主义"
    )
    
    st.write(f"当前轮次: **{st.session_state.round_count}** / 16")
    
    days_left = 6 - int(st.session_state.round_count / 2)
    st.metric("距离房贷扣款日", f"{days_left} 天", delta="余额不足", delta_color="inverse")
    
    st.divider()
    st.write("🧨 **求生工具箱:**")
    col1, col2 = st.columns(2)
    if col1.button("炫耀博士学位"):
        handle_action("【系统事件】玩家试图用博士学位压制亲戚。但亲戚表示隔壁二狗初中毕业开路虎。", "ACTION", "【挣扎】我掏出了我的博士毕业证。")
        st.rerun()
    if col2.button("假装接电话"):
        handle_action("【系统事件】玩家假装那是某院士打来的紧急电话。", "ACTION", "【逃避】“喂？王院士啊，对对对，数据马上发您！”")
        st.rerun()

    st.divider()
    if st.button("破产重开 (Re-roll)", type="primary"):
        st.session_state.clear()
        st.rerun()

# --- 7. 主界面渲染 ---
st.title("💸 物理青椒新春渡劫：房贷与KPI")

# --- 结局 UI ---
if st.session_state.is_over:
    if st.session_state.ending_type == "SUCCESS":
        st.balloons()
        st.success("## 🏆 结局：评上副教授了！")
        st.write("你顶住了房贷压力，本子也中了。亲戚们虽然还是不懂你在干嘛，但听说你工资涨了500块，纷纷竖起大拇指。")
    else:
        st.snow()
        st.error("## 💸 结局：断供离职")
        st.write("房贷断供，考核不合格。你脱下了长衫，去培训机构教初中物理了。")
    
    st.markdown("### 📝 最终报告")
    st.markdown(f"> {st.session_state.final_report}")
    
    if st.button("投胎去金融圈"): 
        st.session_state.clear()
        st.rerun()
    st.stop()

# --- 游戏正文 ---
if not st.session_state.game_started:
    st.markdown("""
    ### 👋 欢迎来到“非升即走”的春节
    你，一名光荣的物理学**青年教师（青椒）**。
    此时此刻，你回到了老家。这里没有人在意你的 H-index，他们只关心你的**年终奖**和**开什么车**。
    更糟糕的是，**房贷扣款日**就在大年初三。
    """)
    
    col1, col2 = st.columns(2)
    with col1: role = st.radio("你的角色：", ["海归博后 (自信满满)", "土博讲师 (如履薄冰)"])
    with col2: 
        field_input = st.text_input("研究方向 (决定亲戚的误解程度)：", placeholder="例如：超弦理论 / 暗物质 / 纳米材料...")
        st.session_state.field = field_input
    
    if st.button("面对疾风 (Start)"):
        if not field_input:
            st.error("请输入方向，不然二大爷不知道该怎么用‘量子力学’教训你。")
        else:
            st.session_state.game_started = True
            real_prompt = f"我是{role}，研究{field_input}。今天是腊月二十八。请开启春节。初始数值：学术尊严100，KPI 0%，钱包熵值 High。给出被亲戚问工资、或者同学聚会炫富的场景。绝对不要提结婚相亲。必须给出 A/B/C 三个选项。"
            display_prompt = f"【回乡】我是{role}，研究{field_input}。我穿着优衣库打折款羽绒服，看着开着宝马回村的发小，陷入了沉思。"
            handle_action(real_prompt, "ACTION", display_text=display_prompt)
            st.rerun()
else:
    # 渲染历史
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    st.divider()

    # === 交互区域 ===
    
    # Mode 1: Boss Battle (Financial Crisis)
    if st.session_state.mode == "BOSS":
        st.error("🚨 **生存危机：房贷/考核 警报！**")
        st.caption("银行卡余额不足，或者人事处要求签署延期考核协议。")
        if rebuttal := st.chat_input("如何解决危机 (借钱/画饼/变卖设备)...", key="boss_input"):
            handle_action(rebuttal, "REBUTTAL")
            st.rerun()

    # Mode 2: Quiz (Pseudoscience)
    elif st.session_state.mode == "QUIZ":
        st.warning("🧩 **民科亲戚发起了攻击！**")
        st.caption("请根据 AI 描述的题目选择策略：")
        
        # === 修复：通用按钮，适应动态剧情 ===
        col_q1, col_q2, col_q3 = st.columns(3)
        with col_q1:
            if st.button("🅰️ 选项 A", use_container_width=True): 
                handle_action("A", "QUIZ_ANSWER")
                st.rerun()
        with col_q2:
            if st.button("🅱️ 选项 B", use_container_width=True): 
                handle_action("B", "QUIZ_ANSWER")
                st.rerun()
        with col_q3:
            if st.button("©️ 选项 C", use_container_width=True): 
                handle_action("C", "QUIZ_ANSWER")
                st.rerun()

    # Mode 3: Normal
    else:
        st.write("🥢 **你的对策：**")
        cols = st.columns(3)
        if cols[0].button("A", use_container_width=True): handle_action("A", "ACTION"); st.rerun()
        if cols[1].button("B", use_container_width=True): handle_action("B", "ACTION"); st.rerun()
        if cols[2].button("C", use_container_width=True): handle_action("C", "ACTION"); st.rerun()
        if prompt := st.chat_input("自定义操作 (例：默默打开知乎搜索‘博士送外卖’)...", key="normal_input"):
            handle_action(prompt, "ACTION"); st.rerun()







