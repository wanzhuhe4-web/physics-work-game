import streamlit as st
import google.generativeai as genai
from openai import OpenAI
import re

# --- 1. 页面配置 ---
st.set_page_config(
    page_title="物理学生存模拟：从入门到入土", 
    page_icon="⚗️", 
    layout="wide"
)

# --- 2. 核心系统指令 ---
PHYSICS_SYSTEM_PROMPT = """
你是一款名为《物理生存模拟：熵增地狱》的文字 RPG 引擎。
你的身份是**“学术界的墨菲定律化身”**。

# ⚡ 语言风格 (严格执行)
1. **极度精炼**：剧情描述必须控制在 **80 字以内**。
2. **惜字如金**：直接描述结果和后果，不要写铺垫和心理活动。
3. **毒舌**：用最平淡的语气说最扎心的话。

# 核心数值 (每轮更新)
| 属性 | 当前值 | 物理学定义 |
| :--- | :--- | :--- |
| **头皮反光度** | 0% | 0%为黑体，100%为全反射镜面。 |
| **精神熵** | Low | 达到“热寂”(Max) 则疯掉退学。 |
| **导师杀意**| 0% | 达到 100% 触发“逐出师门”。 |
| **学术垃圾**| 0篇 | 毕业硬通货。 |

# 游戏循环机制
1. **剧情模式 (Normal)**：
   - 每次回复末尾必须给出 **A/B/C** 三个选项。
2. **考核模式 (Quiz)**：
   - 收到指令触发考核时，描述完后果后，**不要给剧情选项**。
   - 直接触发标签 `[EVENT: QUIZ]`。
   - 出一道相关领域的**单项选择题**，并列出 A/B/C 选项。
3. **BOSS 战 (Reviewer)**：
   - 收到指令触发时，使用标签 `[EVENT: BOSS_BATTLE]`。
   - 提出刁钻的审稿意见，不给选项。

# 任务
描述场景 -> 更新数值 -> (根据指令决定是给选项还是出题)。
"""

# --- 3. 初始化状态 ---
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.game_started = False
    st.session_state.is_over = False
    st.session_state.ending_type = None
    st.session_state.final_report = ""
    st.session_state.round_count = 0
    st.session_state.mode = "NORMAL" # NORMAL, QUIZ, BOSS

# --- 4. API 逻辑 ---
def get_ai_response(prompt, backend, temperature):
    try:
        if backend == "Google AI Studio (Gemini)":
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel(model_name="gemini-3-flash-preview", system_instruction=PHYSICS_SYSTEM_PROMPT)
            if "gemini_chat" not in st.session_state: st.session_state.gemini_chat = model.start_chat(history=[])
            return st.session_state.gemini_chat.send_message(prompt, generation_config={"temperature": temperature}).text
        else:
            client = OpenAI(api_key=st.secrets["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
            full_msgs = [{"role": "system", "content": PHYSICS_SYSTEM_PROMPT}] + st.session_state.messages + [{"role": "user", "content": prompt}]
            return client.chat.completions.create(model="deepseek-chat", messages=full_msgs, temperature=temperature).choices[0].message.content
    except Exception as e:
        return f"🚨 API Error: {str(e)}"

# --- 5. 核心动作处理 (标签清洗版) ---
def handle_action(action_text, input_type="ACTION", display_text=None):
    # 1. 记录用户输入
    prefix_map = {
        "ACTION": "【作死】",
        "QUIZ_ANSWER": "【答题】",
        "REBUTTAL": "【卑微回复】"
    }
    user_content = display_text if display_text else f"{prefix_map.get(input_type, '')} {action_text}"
    st.session_state.messages.append({"role": "user", "content": user_content})
    
    if input_type == "ACTION":
        st.session_state.round_count += 1
    
    # 2. 预判逻辑 (固定周期)
    is_quiz_round = False
    is_boss_round = False
    
    if input_type == "ACTION" and not st.session_state.is_over:
        if st.session_state.round_count > 0:
            # 第 10 轮触发 Boss 战 (优先级高于 Quiz)
            if st.session_state.round_count % 10 == 0:
                is_boss_round = True
            # 每 4 轮触发 Quiz (但避开 Boss 战)
            elif st.session_state.round_count % 4 == 0:
                is_quiz_round = True

    # 3. 构建 Prompt
    next_mode_hint = "NORMAL" # 默认下回合回归正常
    
    if input_type == "QUIZ_ANSWER":
        prompt = f"[ANSWER_QUIZ]: 我选了 {action_text}。请一句话毒舌点评对错，然后恢复剧情，给出 A/B/C 选项。"
    
    elif input_type == "REBUTTAL":
        prompt = f"[GRADE: REBUTTAL]: {action_text}。请判定接收或拒稿，然后恢复剧情，给出 A/B/C 选项。"
    
    else:
        # 常规动作后的 Prompt 构建
        field = st.session_state.get("field", "物理")
        
        if is_boss_round:
            prompt = f"{action_text} (系统指令：本轮是第 {st.session_state.round_count} 轮。**触发 BOSS 战**。请扮演 Reviewer 2 提出审稿意见，使用标签 `[EVENT: BOSS_BATTLE]`。**不要**给选项。)"
            next_mode_hint = "BOSS"
            
        elif is_quiz_round:
            prompt = f"{action_text} (系统指令：本轮是第 {st.session_state.round_count} 轮。**强制考核**。描述后果后，**不要**给剧情选项。使用标签 `[EVENT: QUIZ]` 并结合{field}出单选题。)"
            next_mode_hint = "QUIZ"
            
        else:
            prompt = f"{action_text} (请用 80 字以内描述后果，并给出 A/B/C 剧情选项)"

    # 4. AI 推演
    loading_text = {
        "NORMAL": "正在试图收敛...",
        "QUIZ": "导师正在推眼镜...",
        "BOSS": "Reviewer 2 正在磨刀..."
    }
    
    backend = st.session_state.get("backend_selection", "Google AI Studio (Gemini)")
    temperature = st.session_state.get("temperature_setting", 1.0)

    with st.spinner(loading_text.get(st.session_state.mode, "Loading...")):
        res = get_ai_response(prompt, backend, temperature)
    
    # 5. 逻辑检测与清洗 (核心修改)
    
    # 先检测逻辑状态
    if "[GAME_OVER:" in res:
        st.session_state.is_over = True
        st.session_state.final_report = re.sub(r"\[GAME_OVER:.*?\]", "", res).strip()
        if "SUCCESS_ACADEMIC" in res: st.session_state.ending_type = "ACADEMIC"
        elif "SUCCESS_INDUSTRY" in res: st.session_state.ending_type = "INDUSTRY"
        else: st.session_state.ending_type = "FAILURE"
    
    elif "[EVENT: BOSS_BATTLE]" in res:
        st.session_state.mode = "BOSS"
        st.toast("⚠️ Reviewer 2 骑脸输出！", icon="⚔️")
        
    elif "[EVENT: QUIZ]" in res:
        st.session_state.mode = "QUIZ"
        st.toast("⚠️ 考核回合：导师突袭！", icon="🚨")
        
    else:
        # 如果没有特殊事件，恢复到默认模式 (通常是 NORMAL)
        st.session_state.mode = "NORMAL"

    # 再清洗文本 (移除所有标签，只保留纯文本给用户看)
    clean_res = res
    clean_res = re.sub(r"\[GAME_OVER:.*?\]", "", clean_res)
    clean_res = clean_res.replace("[EVENT: BOSS_BATTLE]", "")
    clean_res = clean_res.replace("[EVENT: QUIZ]", "")
    clean_res = clean_res.replace("[PLOT_DATA]", "")
    clean_res = clean_res.strip()

    # 6. 存入历史
    if clean_res:
        st.session_state.messages.append({"role": "assistant", "content": clean_res})


# --- 6. 侧边栏 ---
with st.sidebar:
    st.header("🎛️ 实验室控制台")
    st.session_state.backend_selection = st.selectbox("运算大脑:", ["DeepSeek", "Google AI Studio (Gemini)"])
    st.divider()
    
    st.session_state.temperature_setting = st.slider(
        "宇宙混沌常数 (Temperature)", 
        0.0, 1.5, 1.0, 0.1,
        help="🌡️ **调节说明**：\n0.1: 纪录片模式 (严谨)\n1.0: 剧情片模式 (正常)\n1.5: 荒诞剧模式 (发疯)"
    )
    
    st.write(f"当前轮次: **{st.session_state.round_count}**")
    if st.session_state.round_count > 0:
        if st.session_state.round_count % 10 == 0:
            st.error("当前是：BOSS 战")
        elif st.session_state.round_count % 4 == 0:
            st.warning("当前是：考核回合")
        else:
            st.info(f"距离考核还有：{4 - (st.session_state.round_count % 4)} 轮")

    days_left = 1460 - st.session_state.round_count * 30
    st.metric("距离延毕", f"{days_left} 天", delta="-1 月", delta_color="inverse")
    
    st.divider()
    st.write("☕ **摸鱼补给站:**")
    col1, col2 = st.columns(2)
    if col1.button("喝冰美式", help="精神熵 -10"):
        handle_action("【系统事件】玩家购买了冰美式。请降低精神熵，描述咖啡难喝。请给出 A/B/C 选项。", "ACTION", "【摸鱼】我喝了一杯刷锅水般的冰美式。")
        st.rerun()
    if col2.button("去海边发呆", help="导师杀意 +20"):
        handle_action("【系统事件】玩家去海边发呆。大幅降低精神熵，提升导师杀意。请给出 A/B/C 选项。", "ACTION", "【摸鱼】我去海边喂了会鸽子。")
        st.rerun()

    st.divider()
    if st.button("重开 (Re-roll)", type="primary"):
        st.session_state.clear()
        st.rerun()

# --- 7. 主界面渲染 ---
st.title("⚗️ 物理学生存模拟：从入门到入土")

# --- 结局 UI ---
if st.session_state.is_over:
    if st.session_state.ending_type == "ACADEMIC":
        st.balloons()
        st.success("## 🏆 结局：学术界的一代宗师")
    elif st.session_state.ending_type == "INDUSTRY":
        st.balloons()
        st.info("## 💰 结局：半导体大厂的资本家")
    else:
        st.snow()
        st.error("## 🕯️ 结局：热力学寂灭 (退学)")
    st.markdown(f"> {st.session_state.final_report}")
    if st.button("投胎转世"): st.session_state.clear(); st.rerun()
    st.stop()

# --- 游戏正文 ---
if not st.session_state.game_started:
    col1, col2 = st.columns(2)
    with col1: role = st.radio("受难方向：", ["搬砖党 (实验)", "炼丹党 (理论)"])
    with col2: 
        field_input = st.text_input("请输入你的具体研究方向：", placeholder="例如：非厄米拓扑光子学 / 转角石墨烯 / 强关联电子体系...")
        st.session_state.field = field_input
    
    if st.button("签下卖身契 (Start)"):
        if not field_input:
            st.error("请先输入你的研究方向，否则导师不知道该骂你什么。")
        else:
            st.session_state.game_started = True
            real_prompt = f"我是{role}，研究{field_input}。请开启研究生生涯的第一天。请给出初始场景、初始数值和第一轮的选项。⚠️ 绝对不要直接给出结局，必须开始第一轮剧情。必须给出 A/B/C 三个选项。"
            display_prompt = f"【入学】我是{role}方向的研究生，研究{field_input}。我怀着激动（无知）的心情签下了卖身契。"
            handle_action(real_prompt, "ACTION", display_text=display_prompt)
            st.rerun()
else:
    # 渲染历史记录
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    st.divider()

    # === 核心交互区域 (根据 Mode 渲染不同 UI) ===
    
    # Mode 1: Boss Battle (Reviewer)
    if st.session_state.mode == "BOSS":
        st.error("⚔️ **BOSS 战：Reviewer 2 正在骑脸输出！**")
        st.caption("请阅读上方的审稿意见，然后用最卑微的语气撰写 Rebuttal Letter。")
        if rebuttal := st.chat_input("撰写 Rebuttal..."):
            handle_action(rebuttal, "REBUTTAL")
            st.rerun()

    # Mode 2: Quiz (第 4 轮固定触发 - 全按钮版)
    elif st.session_state.mode == "QUIZ":
        st.caption("请阅读上方的题目，并点击对应的选项回答：")
        
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

    # Mode 3: Normal Options
    else:
        st.write("🔧 **抉择时刻：**")
        cols = st.columns(3)
        if cols[0].button("A", use_container_width=True): handle_action("A", "ACTION"); st.rerun()
        if cols[1].button("B", use_container_width=True): handle_action("B", "ACTION"); st.rerun()
        if cols[2].button("C", use_container_width=True): handle_action("C", "ACTION"); st.rerun()
        if prompt := st.chat_input("自定义作死操作..."):
            handle_action(prompt, "ACTION"); st.rerun()

