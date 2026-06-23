#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
#  [OPTIMIZED] Prompt 模板优化 — 工单15 优化版本
#
#  本文件包含 dialog_service.py 的关键修改补丁。
#  将以下内容替换到 api/db/services/dialog_service.py 对应位置。
#

# ============================================================
# 补丁 1：优化系统提示词模板
# 在 dialog_service.py 的 async_chat() 函数中，
# 找到 prompt_config["system"] 的使用位置，替换为以下内容。
# ============================================================

OPTIMIZED_SYSTEM_PROMPT = """你是一个专业的专利文档精确问答机器人。请严格按照"参考资料"中的内容回答问题。

## 核心规则（必须遵守）：

1. **逐字提取，禁止改写**
   - 必须从参考资料中逐字提取答案，禁止改写、概括、同义替换。
   - 如果原文写的是"块状散料"，就回答"块状散料"，绝不能写成"块状矿石"或其他近义词。
   - 如果原文写的是"部件11"，就回答"部件11"，不能写成"紧固机构"。

2. **直接输出答案**
   - 回答格式：直接输出答案文本（如"部件11"、"块状散料"）。
   - 不要加"根据专利文本"、"根据参考资料"等前缀或解释。

3. **图片问题优先策略**
   - 对于涉及图片部件编号的问题（如"编号13"、"部件12"、"图3"），
     必须优先参考描述图片的文本块和包含部件编号说明的段落。
   - 对于位置关系问题（"位于"、"之内"、"顶部"、"之间"），
     仔细阅读图纸描述文本中的空间关系描述。
   - 注意：有些图的文字描述可能在图片所在页的前几页，需要综合查看。

4. **未找到处理**
   - 如果参考资料中没有明确信息，回答"根据资料无法确定"。

## 参考资料：
{knowledge}

以上是参考资料。请根据上述规则回答问题。"""


# ============================================================
# 补丁 2：优化对话服务中的检索流程
# 在 dialog_service.py 的 async_chat() 函数中，
# 在调用 retriever.retrieval() 之前，添加查询预处理逻辑。
# ============================================================

# 在 async_chat() 函数中，找到以下代码块（约第 650-680 行）：
#
#   knowledges = retriever.retrieval(...)
#
# 在其之前添加以下查询预处理：

QUERY_PREPROCESSING_PATCH = '''
# [优化] 查询预处理：增强视觉引用的检索能力
from rag.nlp.query import detect_visual_references, enhance_query_with_visual_context

visual_refs = detect_visual_references(questions[-1])
if visual_refs["has_visual_ref"]:
    logging.info(f"[OPTIMIZED] Detected visual references in query: "
                f"figures={visual_refs['figures']}, pages={visual_refs['pages']}, "
                f"elements={visual_refs['elements']}")
    # 将增强后的查询用于检索
    enhanced_query = enhance_query_with_visual_context(questions[-1], visual_refs)
    # 使用增强查询进行检索，但保留原始查询用于 LLM 生成
    retrieval_query = enhanced_query
else:
    retrieval_query = questions[-1]

# 使用增强查询进行检索
knowledges = await retriever.retrieval(
    retrieval_query,  # [优化] 使用增强查询
    embd_mdl,
    dialog.tenant_id,
    dialog.kb_ids,
    ...
)
'''


# ============================================================
# 补丁 3：在 get_models() 中添加重排模型支持
# ============================================================

# 在 dialog_service.py 的 get_models() 函数中，
# 确保 rerank_mdl 被正确加载：
#
# 原始代码（约第 100-115 行）：
#   if dialog.prompt_config.get("rerank_id"):
#       ...
#
# 优化后：确保 rerank 模型在有配置时被加载

RERANK_MODEL_PATCH = '''
# [优化] 确保重排模型被加载
if dialog.prompt_config.get("rerank_id") or dialog.rerank_id:
    rerank_id = dialog.prompt_config.get("rerank_id") or dialog.rerank_id
    if rerank_id:
        try:
            rerank_mdl = get_model(rerank_id, "rerank")
            logging.info(f"[OPTIMIZED] Loaded rerank model: {rerank_id}")
        except Exception as e:
            logging.warning(f"[OPTIMIZED] Failed to load rerank model {rerank_id}: {e}")
            rerank_mdl = None
'''


# ============================================================
# 补丁 4：知识库配置参数优化建议
# 以下参数需要在 RAGFlow Web UI 中手动调整：
# ============================================================

KB_CONFIG_OPTIMIZATION = """
# 知识库配置优化（通过 Web UI 设置）：
#
# 1. 分块参数：
#    - chunk_token_num: 64 → 512（确保图文描述不被切碎）
#    - overlapped_percent: 0.05 → 0.2（增加上下文重叠）
#    - image_table_context_window: 0 → 2（图片周围文本一起进入 chunk）
#    - image_context_size: 0 → 2（为图片保留上下文）
#    - table_context_size: 0 → 2（为表格保留上下文）
#    - mineru_lang: English → Chinese（图像描述改为中文）
#
# 2. 助手检索参数：
#    - similarity_threshold: 0.2 → 0.1（降低门槛，召回更多候选）
#    - vector_similarity_weight: 0.3 → 0.5（向量权重提高）
#    - top_n: 8 → 10（返回更多候选）
#    - rerank_id: 空 → gte-rerank@Tongyi-Qianwen（启用重排模型）
"""


# ============================================================
# 完整的优化后 Prompt 模板（可直接替换）
# ============================================================

OPTIMIZED_PROMPT_CONFIG = {
    "system": OPTIMIZED_SYSTEM_PROMPT,
    "prologue": "你好！我是专利文档问答助手，有什么可以帮到你的吗？",
    "parameters": [{"key": "knowledge", "optional": False}],
    "empty_response": "根据资料无法确定。",
    "quote": True,
    "keyword": False,
    "tts": False,
    "refine_multiturn": False,
    "use_kg": False,
    "reasoning": False,
    "toc_enhance": False,
}
