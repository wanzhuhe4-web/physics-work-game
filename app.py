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

# --- 2. 核心系统指令 (200字 沉浸版) ---
PHYSICS_SYSTEM_PROMPT = """
你是一款名为《物理学青椒新春渡劫》的文字 RPG 引擎。
你的身份是**“非升即走考核制度的化身”**。
玩家是一名物理学青年教师（青椒），正处于 Tenure-track（预聘期）最痛苦的阶段。

# ⚡ 语言风格 (春节凡尔赛版 - 沉浸式)
1. **财富羞辱**：通过亲戚的话语，强调“你虽然是博士，但工资不如送外卖的表弟”。
2. **环境描写**：多描写春节嘈杂、油腻的环境（如：满地瓜子皮、震耳欲聋的麻将声、亲戚嘴角的油光），与你内心的高冷物理世界形成反差。
3. **细节描写**：剧情描述控制在 **150 字左右**。不要记流水账，要写出具体的对话和心理活动。

# 核心数值 (每轮必须更新)
| 属性 | 当前值 | 物理学/社会学定义 |
| :--- | :--- | :--- |
| **学术尊严** | 100 | 初始为满。被问“一个月几千块”或被强行科普“水变油”时大幅下降。 |
| **KPI 进度** | 0% | 包含论文/基金/结题。100% 才能通过聘期考核。 |
| **钱包熵值** | High | 初始为High(钱少)。随着发压岁钱、还房贷、随份子，熵值趋向于 Max (破产)。 |
| **发际线** | 0% | 0%为浓密，100%为全反射镜面（受科研压力影响）。 |

# 游戏循环机制
1. **剧情模式 (Normal) -> [标签: 炫富攻击]**：
   - 场景：高中同学聚会（都在金融/互联网大厂）、亲戚攀比大会。
   - 必须给出 **A/B/C** 选项（包含：试图讲理、默默忍受、拿出计算器算房贷）。
2. **考核模式 (Quiz) -> [标签: 民科对线]**：
   - 触发标签 `[EVENT: QUIZ]`。
   - 场景：二大爷/三姑妈咨询奇葩物理问题（如：引力波能不能防辐射？）。
   - 出一道物理相关的**生活/谣言粉碎单选题**。
3. **BOSS 战 (Reviewer) -> [标签: 生存危机]**：
   - 触发标签 `[EVENT: BOSS_BATTLE]`。
   - 场景：收到银行的房贷催款短信，或者人事处的“聘期考核预警”邮件。
   - 提出危机情况，不给选项，要求玩家写**求情信**或**对赌协议**。

# 任务
描述“知识分子在金钱面前的窘迫” -> 更新数值 -> (根据指令决定操作)。
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

# --- 4. API 逻辑 ---
def get_ai_response(prompt, backend, temperature):
    try:
        if backend == "Google AI Studio (Gemini)":
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel(model_name="gemini-2.0-flash", system_instruction=PHYSICS_SYSTEM_PROMPT)
            if "gemini_chat" not in st.session_state: st.session_state.gemini_chat = model.start_chat(history=[])
            return st.session_state.gemini_chat.send_message(prompt, generation_config={"temperature": temperature}).text
        else:
            client = OpenAI(api_key=st.secrets["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
            full_msgs = [{"role": "system", "content": PHYSICS_SYSTEM_PROMPT}] + st.session_state.messages + [{"role": "user", "content": prompt}]
            return client.chat.completions.create(model="deepseek-chat", messages=full_msgs, temperature=temperature).choices[0].message.content
    except Exception as e:
        return f"🚨 API Error: {str(e)}"

# --- 5. 核心动作处理 (修改了字数提示) ---
def handle_action(action_text, input_type="ACTION", display_text=None):
    prefix_map = {
        "ACTION": "【抉择】",
        "QUIZ_ANSWER": "【辟谣】",
        "REBUTTAL": "【卑微求生】"
    }
    user_content = display_text if display_text else f"{prefix_map.get(input_type, '')} {action_text}"
    st.session_state.messages.append({"role": "user", "content": user_content})
    
    if input_type == "ACTION":
        st.session_state.round_count += 1
    
    # 2. 预判逻辑
    is_quiz_round = False
    is_boss_round = False
    
    if input_type == "ACTION" and not st.session_state.is_over:
        if st.session_state.round_count > 0:
            # 缩短周期：第 7 轮 房贷/考核 BOSS 战
            if st.session_state.round_count % 7 == 0:
                is_boss_round = True
            # 每 3 轮 遭遇民科提问
            elif st.session_state.round_count % 3 == 0:
                is_quiz_round = True

    # 3. Prompt 构建
    field = st.session_state.get("field", "理论物理")
    
    if input_type == "QUIZ_ANSWER":
        prompt = f"[ANSWER_QUIZ]: 我选了 {action_text}。请判定我对亲戚的科普是否成功（通常是失败，因为他们只信抖音）。请用150字左右详细描写亲戚的反驳神态，然后恢复剧情，给出 A/B/C 选项。"
    
    elif input_type == "REBUTTAL":
        prompt = f"[GRADE: REBUTTAL]: {action_text}。请判定银行/人事处是否宽限了我的死线，然后恢复剧情，给出 A/B/C 选项。"
    
    else:
        if is_boss_round:
            prompt = f"{action_text} (系统指令：本轮是第 {st.session_state.round_count} 轮。**生存危机**。请触发房贷扣款失败，或者学院通知聘期考核不合格。使用标签 `[EVENT: BOSS_BATTLE]`。**不要**给选项。)"
            st.session_state.mode = "BOSS"
        elif is_quiz_round:
            prompt = f"{action_text} (系统指令：本轮是第 {st.session_state.round_count} 轮。**民科对线**。亲戚提出了基于{field}的荒谬养生/致富理论。请用150字左右生动描写场景，使用标签 `[EVENT: QUIZ]` 并出单选题(A/B/C)。)"
            st.session_state.mode = "QUIZ"
        else:
            prompt = f"{action_text} (请用 150 字左右丰富细腻地描写同学聚会炫富、亲戚问工资等场景，重点描写环境细节和人物神态，强调物理青椒的贫穷，并给出 A/B/C 剧情选项)"
            st.session_state.mode = "NORMAL"

    # 4. AI 推演
    loading_text = {
        "NORMAL": "正在计算同学的年终奖...",
        "QUIZ": "二大爷正在分享营销号视频...",
        "BOSS": "银行系统正在扣款..."
    }
    
    backend = st.session_state.get("backend_selection", "Google AI Studio (Gemini)")
    temperature = st.session_state.get("temperature_setting", 1.0)

    with st.spinner(loading_text.get(st.session_state.mode, "Loading...")):
        res = get_ai_response(prompt, backend, temperature)
    
    # 5. 逻辑检测
    if "[GAME_OVER:" in res:
        st.session_state.is_over = True
        st.session_state.final_report = re.sub(r"\[GAME_OVER:.*?\]", "", res).strip()
        if "SUCCESS" in res: st.session_state.ending_type = "SUCCESS"
        else: st.session_state.ending_type = "FAILURE"
    
    clean_res = res
    clean_res = re.sub(r"\[GAME_OVER:.*?\]", "", clean_res)
    clean_res = clean_res.replace("[EVENT: BOSS_BATTLE]", "")
    clean_res = clean_res.replace("[EVENT: QUIZ]", "")
    clean_res = clean_res.strip()

    if clean_res:
        st.session_state.messages.append({"role": "assistant", "content": clean_res})

# --- 6. 侧边栏 ---
with st.sidebar:
    st.header("📉 青椒生存控制台")
    st.session_state.backend_selection = st.selectbox("算力赞助:", ["DeepSeek", "Google AI Studio (Gemini)"])
    st.divider()
    
    st.session_state.temperature_setting = st.slider(
        "焦虑浓度 (Temperature)", 
        0.0, 1.5, 1.0, 0.1,
        help="0.1: 真实纪录片\n1.0: 黑色幽默\n1.5: 荒诞现实主义"
    )
    
    st.write(f"当前轮次: **{st.session_state.round_count}**")
    
    days_left = 6 - int(st.session_state.round_count / 2)
    st.metric("距离房贷扣款日", f"{days_left} 天", delta="余额不足", delta_color="inverse")
    
    st.divider()
    st.write("🧨 **求生工具箱:**")
    col1, col2 = st.columns(2)
    if col1.button("炫耀博士学位", help="学术尊严 +10，但会被亲戚嘲笑书呆子"):
        handle_action("【系统事件】玩家试图用博士学位压制亲戚。但亲戚表示隔壁二狗初中毕业开路虎。", "ACTION", "【挣扎】我掏出了我的博士毕业证。")
        st.rerun()
    if col2.button("假装接电话", help="躲避一轮攻击，KPI 进度 +2%"):
        handle_action("【系统事件】玩家假装那是某院士打来的紧急电话。", "ACTION", "【逃避】“喂？王院士啊，对对对，那个数据我马上发您！”")
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
    st.markdown(f"> {st.session_state.final_report}")
    if st.button("投胎去金融圈"): st.session_state.clear(); st.rerun()
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
        if rebuttal := st.chat_input("如何解决危机 (借钱/画饼/变卖设备)..."):
            handle_action(rebuttal, "REBUTTAL")
            st.rerun()

    # Mode 2: Quiz (Pseudoscience)
    elif st.session_state.mode == "QUIZ":
        st.caption("面对这些的言论，你决定：")
        
        col_q1, col_q2, col_q3 = st.columns(3)
        with col_q1:
            if st.button("🅰️ ", use_container_width=True): 
                handle_action("A", "QUIZ_ANSWER")
                st.rerun()
        with col_q2:
            if st.button("🅱️ ", use_container_width=True): 
                handle_action("B", "QUIZ_ANSWER")
                st.rerun()
        with col_q3:
            if st.button("©️ ", use_container_width=True): 
                handle_action("C", "QUIZ_ANSWER")
                st.rerun()

    # Mode 3: Normal
    else:
        st.write("🥢 **你的对策：**")
        cols = st.columns(3)
        if cols[0].button("A", use_container_width=True): handle_action("A", "ACTION"); st.rerun()
        if cols[1].button("B", use_container_width=True): handle_action("B", "ACTION"); st.rerun()
        if cols[2].button("C", use_container_width=True): handle_action("C", "ACTION"); st.rerun()
        if prompt := st.chat_input("自定义操作 (例：默默打开知乎搜索‘博士送外卖’)..."):
            handle_action(prompt, "ACTION"); st.rerun()



