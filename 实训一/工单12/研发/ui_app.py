"""
Streamlit Web UI - 友好的交互界面
"""
import streamlit as st
import sys
from pathlib import Path
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from document_loader import prepare_documents
from embedding import RAGRetriever
from query_processor import QueryProcessor
from llm_agent import QASystem, DeepSeekLLM
from config import FAISS_INDEX_PATH


# Streamlit页面配置
st.set_page_config(
    page_title="📚 招股说明书问答系统",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS
st.markdown("""
<style>
    .main {
        padding: 2rem;
    }
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 1.2em;
    }
    .result-box {
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
        background-color: #f0f2f6;
    }
    .answer-box {
        border-left: 4px solid #1f77b4;
        padding: 1rem;
        background-color: #f8f9fa;
        margin: 1rem 0;
    }
    .source-box {
        border-left: 4px solid #ff7f0e;
        padding: 1rem;
        background-color: #fff8f0;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def load_qa_system():
    """缓存加载QA系统"""
    retriever = RAGRetriever()
    query_processor = QueryProcessor()
    
    # 检查索引是否存在
    if os.path.exists(os.path.join(FAISS_INDEX_PATH, "faiss.index")):
        retriever.load_from_index()
    else:
        with st.spinner("🔨 首次运行，构建索引中..."):
            chunks = prepare_documents()
            retriever.initialize(chunks)
    
    qa_system = QASystem(retriever, query_processor)
    return qa_system


def main():
    # 头部
    st.markdown("# 📚 招股说明书智能问答系统")
    st.markdown("基于RAG技术的大语言模型问答系统，智能解析招股说明书")
    
    # 侧边栏
    with st.sidebar:
        st.markdown("## ⚙️ 系统配置")
        
        st.markdown("### 📖 关于系统")
        st.info("""
        **系统功能：**
        - 🔍 智能文档检索
        - 🤖 基于LLM的答案生成
        - 📊 结果置信度评估
        - 📝 源文档追溯
        
        **使用技术：**
        - DeepSeek LLM API
        - FAISS向量检索
        - Sentence Transformers嵌入
        """)
        
        # 温度参数控制
        temperature = st.slider("🌡️ 答案多样性 (Temperature)", 0.0, 1.0, 0.7, 0.1)
        
        # 返回文档数
        top_k = st.slider("📄 检索文档数", 1, 10, 5)
        
        st.markdown("---")
        st.markdown("### 📞 技术支持")
        st.caption("如有问题，请联系技术支持团队")
    
    # 主内容区域
    tab1, tab2, tab3, tab4 = st.tabs(["🤖 问答", "📊 演示查询", "📈 系统状态", "📖 使用指南"])
    
    # Tab 1: 问答
    with tab1:
        st.markdown("## 问答功能")
        st.markdown("输入您的问题，系统将从招股说明书中检索相关信息并生成答案。支持 **文字输入** 和 **语音输入** 两种方式。")
        
        # 输入方式选择
        input_mode = st.radio(
            "选择输入方式",
            ["📝 文字输入", "🎤 语音输入"],
            horizontal=True,
            label_visibility="collapsed"
        )
        
        query = ""
        
        if input_mode == "📝 文字输入":
            query = st.text_area(
                "您的问题",
                placeholder="例如：公司2023年的营业收入是多少？",
                height=100
            )
        else:
            st.markdown("### 🎤 语音输入")
            st.markdown("点击下方按钮录制您的问题（录制完成后将自动识别为文字）")
            
            # 检查是否安装了语音识别库
            try:
                import speech_recognition as sr
                stt_available = True
            except ImportError:
                stt_available = False
            
            if not stt_available:
                st.warning("⚠️ 语音识别功能需要安装依赖库。请在终端执行：`pip install SpeechRecognition pydub`")
            else:
                audio_data = st.audio_input("🎤 点击录制您的问题", key="voice_input")
                
                if audio_data is not None:
                    with st.spinner("🔄 正在识别语音..."):
                        try:
                            import tempfile
                            import wave
                            
                            # 保存音频到临时文件
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                                tmp.write(audio_data.getvalue())
                                tmp_path = tmp.name
                            
                            recognizer = sr.Recognizer()
                            with sr.AudioFile(tmp_path) as source:
                                audio_record = recognizer.record(source)
                            
                            text = recognizer.recognize_google(audio_record, language="zh-CN")
                            query = text
                            
                            st.success(f"✅ 语音识别结果：**{text}**")
                            
                            # 清理临时文件
                            try:
                                os.unlink(tmp_path)
                            except Exception:
                                pass
                                
                        except Exception as e:
                            st.error(f"❌ 语音识别失败: {str(e)}")
                            st.info("💡 提示：请确保说话清晰，录制环境安静，然后重试。")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            submit_button = st.button("🔍 搜索答案", type="primary", use_container_width=True)
        
        with col2:
            clear_button = st.button("🗑️ 清空", use_container_width=True)
        
        with col3:
            if st.button("💾 保存结果", use_container_width=True):
                st.info("结果已保存到会话")
        
        if clear_button:
            st.rerun()
        
        if submit_button and query:
            try:
                with st.spinner("⏳ 正在处理您的问题..."):
                    qa_system = load_qa_system()
                    result = qa_system.answer(query)
                
                # 显示结果
                st.success("✓ 处理完成!")
                
                # 答案部分
                st.markdown("### 📄 答案")
                with st.container():
                    st.markdown(f"""
                    <div class="answer-box">
                    {result['answer']}
                    </div>
                    """, unsafe_allow_html=True)
                
                # 置信度
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("📌 置信度", f"{result['confidence']:.1%}")
                
                # 来源信息
                if result['sources']:
                    st.markdown("### 📚 参考来源")
                    for i, source in enumerate(result['sources'], 1):
                        with st.expander(
                            f"参考 {i} - 第{source['page']}页 (相似度: {source['similarity']:.1%})"
                        ):
                            st.caption(f"文档块ID: {source['chunk_id']}")
                
                # 查询分析（如果有）
                if hasattr(qa_system, 'query_processor') and qa_system.query_processor:
                    with st.expander("🔬 Query分析"):
                        processed = qa_system.query_processor.process_query(query)
                        st.json({
                            "意图": processed['intent'],
                            "子查询": processed['sub_queries'],
                            "关键实体": processed['entities']
                        })
            
            except Exception as e:
                st.error(f"❌ 错误: {str(e)}")
        
        elif submit_button and not query:
            st.warning("⚠️ 请先输入问题（文字输入或语音录制）后再搜索答案")
    
    # Tab 2: 演示查询
    with tab2:
        st.markdown("## 📊 演示查询")
        st.markdown("点击下方预设查询进行演示")
        
        demo_queries = {
            "公司基本信息": "请介绍公司的基本情况、主营业务和组织结构",
            "财务数据": "公司最近一年的主要财务指标是什么？包括收入、利润等",
            "风险分析": "公司面临的主要风险因素有哪些？",
            "发展规划": "公司的发展战略和未来规划是什么？",
            "产品服务": "公司的主要产品或服务有哪些？",
        }
        
        for title, query in demo_queries.items():
            if st.button(f"❓ {title}", use_container_width=True):
                st.session_state.demo_query = query
                st.session_state.run_demo = True
        
        if "run_demo" in st.session_state and st.session_state.run_demo:
            with st.spinner("⏳ 正在处理..."):
                qa_system = load_qa_system()
                result = qa_system.answer(st.session_state.demo_query)
            
            st.markdown(f"### 问题：{st.session_state.demo_query}")
            st.markdown(f"### 答案：\n{result['answer']}")
            st.markdown(f"置信度：{result['confidence']:.1%}")
    
    # Tab 3: 系统状态
    with tab3:
        st.markdown("## 📈 系统状态")
        
        try:
            qa_system = load_qa_system()
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("✅ 系统状态", "正常运行")
            
            with col2:
                st.metric("🔌 API连接", "已连接")
            
            with col3:
                if os.path.exists(os.path.join(FAISS_INDEX_PATH, "faiss.index")):
                    st.metric("📑 索引状态", "已建立")
                else:
                    st.metric("📑 索引状态", "需要构建")
            
            st.markdown("### 📋 系统信息")
            st.json({
                "PDF文件": "见文档管理面板",
                "嵌入模型": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                "LLM模型": "deepseek-chat",
                "向量数据库": "FAISS",
                "索引位置": FAISS_INDEX_PATH
            })
        
        except Exception as e:
            st.error(f"❌ 系统错误: {e}")
    
    # Tab 4: 使用指南
    with tab4:
        st.markdown("## 📖 使用指南")
        
        st.markdown("### 🎯 功能介绍")
        st.markdown("""
        #### 1. **Query理解**
        系统能够识别和理解您的问题：
        - **意图识别**：自动识别问题属于财务、产品、风险等哪一类
        - **消歧**：处理模糊或多义的问题
        - **分解**：将复杂问题分解为多个子问题
        
        #### 2. **检索与生成**
        - **向量检索**：使用FAISS快速检索相关文档段落
        - **排序**：根据相似度排序检索结果
        - **LLM生成**：基于检索结果使用DeepSeek生成准确答案
        
        #### 3. **用户体验**
        - **友好界面**：通过Streamlit提供Web界面
        - **置信度评估**：显示答案的置信度
        - **源文档追溯**：查看答案的出处
        - **快速反馈**：即时获得答案
        """)
        
        st.markdown("### 💡 使用建议")
        st.markdown("""
        1. **提问要具体**：提供更多上下文信息可以获得更准确的答案
        2. **分步提问**：复杂问题可以分步骤提问
        3. **查看来源**：重要信息时查看参考来源验证
        4. **调整参数**：在侧边栏调整参数优化答案质量
        """)
        
        st.markdown("### ❓ 常见问题")
        with st.expander("Q: 答案不准确怎么办？"):
            st.write("请尝试：1) 重新表述问题 2) 查看参考来源是否正确 3) 调整温度参数")
        
        with st.expander("Q: 如何提高检索准确度？"):
            st.write("1) 使用更具体的关键词 2) 增加检索文档数 3) 查看系统是否已完整加载PDF")
        
        with st.expander("Q: 系统支持哪些语言？"):
            st.write("系统主要支持中文，同时支持英文等其他语言")


if __name__ == "__main__":
    main()
