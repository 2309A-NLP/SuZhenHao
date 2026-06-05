"""
🦞 智能文档问答系统 - 极简风格 v3
支持深色/浅色模式切换
"""

import os
import sys
import streamlit as st
import streamlit.components.v1 as components

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from config import UPLOAD_DIR, KG_OUTPUT_DIR, KG_MAX_CHUNKS
from pdf_processor import PDFProcessor
from rag_chain import RAGChain
from knowledge_graph import KnowledgeGraph

# ========== 页面配置 ==========
st.set_page_config(
    page_title="🦞 智能文档问答",
    page_icon="🦞",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ========== 初始化 ==========
if 'theme' not in st.session_state:
    st.session_state.theme = "dark"
if 'pdf_processor' not in st.session_state:
    st.session_state.pdf_processor = PDFProcessor()
if 'rag_chain' not in st.session_state:
    st.session_state.rag_chain = RAGChain(st.session_state.pdf_processor)
if 'knowledge_graph' not in st.session_state:
    st.session_state.knowledge_graph = KnowledgeGraph()
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'pdf_loaded' not in st.session_state:
    st.session_state.pdf_loaded = False
if 'kg_built' not in st.session_state:
    st.session_state.kg_built = False

# ========== 主题配色 ==========
if st.session_state.theme == "dark":
    C = {
        "bg": "#0d0d0d", "bg2": "#111", "bg3": "#1a1a1a", "bg4": "#2f2f2f",
        "border": "#2a2a2a", "border2": "#333", "border3": "#222",
        "text": "#ececec", "text2": "#ccc", "text3": "#8e8ea0", "text4": "#666", "text5": "#555",
        "accent": "#7c3aed", "green": "#10b981", "yellow": "#f59e0b",
        "tab_bg": "#111", "tab_active": "#2a2a2a", "tab_active_text": "#fff",
        "input_bg": "#1a1a1a", "input_border": "#333",
        "card_bg": "#1a1a1a", "card_border": "#2a2a2a",
        "bubble_user_bg": "#2f2f2f", "bubble_user_text": "#ececec",
        "source_bg": "#151515", "source_border": "#222",
    }
else:
    C = {
        "bg": "#ffffff", "bg2": "#f7f7f8", "bg3": "#ffffff", "bg4": "#e8e8e8",
        "border": "#e5e5e5", "border2": "#d0d0d0", "border3": "#eee",
        "text": "#1a1a1a", "text2": "#333", "text3": "#666", "text4": "#888", "text5": "#999",
        "accent": "#7c3aed", "green": "#10b981", "yellow": "#f59e0b",
        "tab_bg": "#f0f0f0", "tab_active": "#fff", "tab_active_text": "#1a1a1a",
        "input_bg": "#fff", "input_border": "#d0d0d0",
        "card_bg": "#fff", "card_border": "#e5e5e5",
        "bubble_user_bg": "#f0f0f0", "bubble_user_text": "#1a1a1a",
        "source_bg": "#f7f7f8", "source_border": "#eee",
    }

# ========== CSS ==========
st.markdown(f"""
<style>
    /* ===== 强制覆盖所有背景 ===== */
    html, body,
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stHeader"],
    [data-testid="stDecoration"],
    section.main,
    .main .block-container {{
        background-color: {C['bg']} !important;
        color: {C['text']} !important;
    }}

    * {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }}
    #MainMenu, footer, header {{visibility: hidden;}}

    /* 主内容区 */
    .main .block-container {{
        max-width: 780px;
        padding: 40px 24px 100px 24px;
    }}

    /* ===== 侧边栏 ===== */
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div,
    [data-testid="stSidebar"] > div > div {{
        background-color: {C['bg2']} !important;
    }}
    [data-testid="stSidebar"] {{
        border-right: 1px solid {C['border']} !important;
        width: 300px !important;
    }}
    [data-testid="stSidebar"] .stButton > button {{
        width: 100% !important;
        height: 40px !important;
        border-radius: 8px !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        background: {C['bg4']} !important;
        color: {C['text2']} !important;
        border: 1px solid {C['border2']} !important;
    }}
    [data-testid="stSidebar"] .stButton > button:hover {{
        background: {C['border2']} !important;
        border-color: {C['text4']} !important;
    }}
    [data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4 {{
        color: {C['text2']} !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    [data-testid="stSidebar"] hr {{
        border-color: {C['border3']} !important;
        margin: 14px 0 !important;
    }}
    [data-testid="stSidebar"] .stFileUploader {{
        border: 1px dashed {C['border2']} !important;
        border-radius: 8px !important;
        padding: 12px !important;
        background: {C['bg3']} !important;
    }}

    /* ===== 欢迎 ===== */
    .welcome {{
        text-align: center;
        padding: 60px 0 24px 0;
    }}
    .welcome h1 {{
        font-size: 32px;
        font-weight: 700;
        color: {C['text']};
        margin-bottom: 8px;
    }}
    .welcome p {{
        color: {C['text3']};
        font-size: 15px;
    }}

    /* ===== 功能卡片 ===== */
    .cards {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
        max-width: 500px;
        margin: 28px auto 0 auto;
    }}
    .card {{
        background: {C['card_bg']};
        border: 1px solid {C['card_border']};
        border-radius: 10px;
        padding: 18px 16px;
        transition: border-color 0.2s;
    }}
    .card:hover {{
        border-color: {C['text4']};
    }}
    .card-icon {{ font-size: 20px; margin-bottom: 6px; }}
    .card-title {{ color: {C['text']}; font-size: 14px; font-weight: 600; margin-bottom: 4px; }}
    .card-desc {{ color: {C['text4']}; font-size: 12px; }}

    /* ===== 对话 ===== */
    .bubble-user {{
        background: {C['bubble_user_bg']};
        border-radius: 18px;
        padding: 14px 18px;
        color: {C['bubble_user_text']};
        font-size: 15px;
        line-height: 1.6;
        max-width: 75%;
        margin-left: auto;
        margin-bottom: 16px;
    }}
    .bubble-bot {{
        color: {C['text2']};
        font-size: 15px;
        line-height: 1.75;
        padding: 8px 0 20px 0;
        margin-bottom: 16px;
        border-bottom: 1px solid {C['border3']};
    }}
    .bot-label {{
        font-size: 12px;
        font-weight: 600;
        color: {C['text3']};
        margin-bottom: 6px;
        letter-spacing: 0.5px;
    }}

    /* ===== 来源 ===== */
    .source-box {{
        background: {C['source_bg']};
        border: 1px solid {C['source_border']};
        border-left: 3px solid {C['text4']};
        border-radius: 6px;
        padding: 10px 14px;
        margin: 6px 0;
        font-size: 13px;
        color: {C['text4']};
        line-height: 1.5;
    }}

    /* ===== 知识图谱 ===== */
    .kg-stats {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 10px;
        margin: 20px 0;
    }}
    .kg-stat {{
        text-align: center;
        background: {C['card_bg']};
        border: 1px solid {C['card_border']};
        border-radius: 10px;
        padding: 18px 12px;
    }}
    .kg-num {{ font-size: 28px; font-weight: 700; color: {C['accent']}; }}
    .kg-label {{ font-size: 12px; color: {C['text4']}; margin-top: 4px; }}

    /* ===== Tab ===== */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0;
        background: {C['tab_bg']};
        border-radius: 8px;
        padding: 3px;
    }}
    .stTabs [data-baseweb="tab"] {{
        color: {C['text4']};
        border-radius: 6px;
        font-size: 14px;
        font-weight: 500;
        padding: 10px 0;
        flex: 1;
        text-align: center;
    }}
    .stTabs [aria-selected="true"] {{
        color: {C['tab_active_text']} !important;
        background: {C['tab_active']} !important;
    }}
    .stTabs [data-baseweb="tab-border"],
    .stTabs [data-baseweb="tab-highlight"] {{
        display: none !important;
    }}

    /* ===== 输入框 ===== */
    .stChatInput textarea {{
        background: {C['input_bg']} !important;
        border: 1px solid {C['input_border']} !important;
        border-radius: 12px !important;
        color: {C['text']} !important;
        font-size: 15px !important;
    }}
    .stChatInput textarea:focus {{
        border-color: {C['text4']} !important;
        box-shadow: none !important;
    }}
    .stChatInput textarea::placeholder {{
        color: {C['text4']} !important;
    }}

    /* ===== 全局文字覆盖 ===== */
    .stMarkdown, .stMarkdown p, .stMarkdown li,
    label, span, p,
    [data-testid="stMarkdownContainer"],
    [data-testid="stMarkdownContainer"] p {{
        color: {C['text']} !important;
    }}

    /* 提示框 */
    .stAlert {{
        background-color: {C['bg3']} !important;
        border: 1px solid {C['border']} !important;
        border-radius: 8px !important;
    }}
    .stAlert p {{ color: {C['text2']} !important; }}

    /* Spinner */
    .stSpinner > div {{ border-top-color: {C['accent']} !important; }}

    /* Expander */
    details {{
        background: {C['bg3']} !important;
        border: 1px solid {C['border']} !important;
        border-radius: 8px !important;
    }}
    details summary {{ color: {C['text2']} !important; }}
    details > div {{ background: {C['bg3']} !important; }}

    /* ===== 状态 ===== */
    .status {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        color: {C['text3']};
        margin-bottom: 8px;
    }}
    .dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
    }}
    .dot-ok {{ background: {C['green']}; }}
    .dot-off {{ background: {C['yellow']}; }}
</style>
""", unsafe_allow_html=True)


# ========== 侧边栏 ==========
with st.sidebar:
    # 主题切换
    theme_icon = "🌙" if st.session_state.theme == "dark" else "☀️"
    theme_text = "深色模式" if st.session_state.theme == "dark" else "浅色模式"
    if st.button(f"{theme_icon}  {theme_text}", use_container_width=True, key="theme_btn"):
        st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
        st.rerun()

    st.markdown("### 控制面板")
    st.divider()

    # 状态
    if st.session_state.pdf_loaded:
        st.markdown(f'<div class="status"><span class="dot dot-ok"></span> 文档已加载</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="status"><span class="dot dot-off"></span> 未加载文档</div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### 上传文档")

    uploaded_file = st.file_uploader("选择PDF", type=["pdf"], label_visibility="collapsed")

    if uploaded_file is not None:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        pdf_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
        with open(pdf_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        if st.button("处理文档", use_container_width=True):
            with st.spinner("处理中..."):
                result = st.session_state.pdf_processor.process_pdf(pdf_path)
                if "error" in result:
                    st.error(result["error"])
                else:
                    st.session_state.pdf_loaded = True
                    st.success(f"完成 · {result['total_chars']}字 · {result['total_chunks']}块")

    st.divider()
    st.markdown("### 知识图谱")

    if st.session_state.pdf_loaded:
        if st.button("构建图谱", use_container_width=True):
            with st.spinner("抽取实体关系..."):
                chunks = st.session_state.pdf_processor.all_chunks
                max_chunks = min(len(chunks), KG_MAX_CHUNKS)
                stats = st.session_state.knowledge_graph.build_graph_from_chunks(chunks[:max_chunks])
                st.session_state.kg_built = True
                st.success(f"完成 · {stats['total_nodes']}节点 · {stats['total_edges']}边")
    else:
        st.caption("请先上传文档")

    st.divider()

    if st.button("清除对话", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.rag_chain.clear_history()
        st.rerun()


# ========== 主内容 ==========
tab_chat, tab_kg = st.tabs(["对话", "知识图谱"])

# ----- 对话 -----
with tab_chat:
    if not st.session_state.chat_history:
        st.markdown(f"""
        <div class="welcome">
            <h1>有什么可以帮你的？</h1>
            <p>上传PDF文档，开始智能问答</p>
        </div>
        <div class="cards">
            <div class="card">
                <div class="card-icon">📄</div>
                <div class="card-title">文档问答</div>
                <div class="card-desc">上传PDF，精准回答</div>
            </div>
            <div class="card">
                <div class="card-icon">🌐</div>
                <div class="card-title">中英文支持</div>
                <div class="card-desc">自动识别语言</div>
            </div>
            <div class="card">
                <div class="card-icon">🕸️</div>
                <div class="card-title">知识图谱</div>
                <div class="card-desc">抽取实体关系</div>
            </div>
            <div class="card">
                <div class="card-icon">📚</div>
                <div class="card-title">来源追溯</div>
                <div class="card-desc">附带参考来源</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        for role, content in st.session_state.chat_history:
            if role == "user":
                st.markdown(f'<div class="bubble-user">{content}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'''
                <div class="bubble-bot">
                    <div class="bot-label">🦞 ASSISTANT</div>
                    {content}
                </div>
                ''', unsafe_allow_html=True)

    user_input = st.chat_input("输入你的问题...")

    if user_input:
        st.session_state.chat_history.append(("user", user_input))

        if not st.session_state.pdf_loaded:
            answer = "请先在左侧上传并处理PDF文档后再提问 📄"
            sources = []
        else:
            with st.spinner(""):
                result = st.session_state.rag_chain.generate_answer(user_input)
                answer = result["answer"]
                sources = result["sources"]

        st.session_state.chat_history.append(("assistant", answer))
        st.rerun()


# ----- 知识图谱 -----
with tab_kg:
    if not st.session_state.kg_built:
        st.markdown(f"""
        <div class="welcome">
            <h1>🕸️ 知识图谱</h1>
            <p>上传PDF并构建图谱后查看</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        kg = st.session_state.knowledge_graph

        st.markdown(f"""
        <div class="kg-stats">
            <div class="kg-stat">
                <div class="kg-num">{kg.graph.number_of_nodes()}</div>
                <div class="kg-label">实体节点</div>
            </div>
            <div class="kg-stat">
                <div class="kg-num">{kg.graph.number_of_edges()}</div>
                <div class="kg-label">关系边</div>
            </div>
            <div class="kg-stat">
                <div class="kg-num">{len(kg.all_triplets)}</div>
                <div class="kg-label">三元组</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("查看三元组"):
            st.text(kg.get_triplets_text())

        html_path = kg.generate_html()
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        components.html(html_content, height=600, scrolling=True)

        if st.button("重新构建"):
            with st.spinner("重建中..."):
                chunks = st.session_state.pdf_processor.all_chunks
                max_chunks = min(len(chunks), KG_MAX_CHUNKS)
                kg.build_graph_from_chunks(chunks[:max_chunks])
                st.rerun()

# 启动方式
# conda activate nlp_2
# streamlit run app.py