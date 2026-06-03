# 导入操作系统相关功能模块，用于文件路径、环境变量、文件存在性判断等操作
import os
# 导入类型注解工具，用于定义字典、列表、可选参数等类型提示，提升代码可读性和类型检查
from typing import Dict, List, Optional

# 导入LangChain社区的网页加载器，用于从指定URL抓取网页文本内容
from langchain_community.document_loaders import WebBaseLoader
# 导入LangChain的文本分割器，用于将长文本切分为指定大小的文本块，适配向量数据库存储
from langchain_text_splitters import RecursiveCharacterTextSplitter
# 导入Milvus向量数据库客户端，用于连接、创建集合、插入数据、查询等操作
from pymilvus import MilvusClient
# 导入句子转换器模型，用于将文本转换为向量（embedding），实现语义向量化
from sentence_transformers import SentenceTransformer

# 导入自定义的MySQL存储工具类，用于将文档元数据写入MySQL数据库
from mysql_store import MySQLStore
# 导入自定义的角色配置工具，用于获取指定角色的配置信息（如集合名、显示名称）
from role_config import get_role_config

# 从环境变量获取Milvus连接地址，无环境变量时使用默认本地地址
MILVUS_URI = os.getenv("MILVUS_URI", "http://192.168.253.131:19530")
# 从环境变量获取向量模型本地路径，无环境变量时使用指定的本地模型路径
EMBEDDING_MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH", "C:/Users/23672/Desktop/模型/bge-m3")


def _ensure_collection(client: MilvusClient, collection_name: str, dim: int) -> None:
    """
    私有函数：确保Milvus中存在指定的集合，不存在则自动创建
    :param client: Milvus客户端实例
    :param collection_name: 要创建/检查的集合名称
    :param dim: 向量维度（根据向量模型自动确定）
    :return: 无返回值
    """
    # 判断Milvus中是否已存在该集合，存在则直接返回，不执行后续创建逻辑
    if client.has_collection(collection_name):
        return

    # 创建集合schema（数据结构），开启自动生成主键，关闭动态字段（固定字段结构）
    schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
    # 添加主键字段：id，类型为64位整型，设置为主键
    schema.add_field("id", "int64", is_primary=True)
    # 添加标题字段：title，字符串类型，最大长度512字符
    schema.add_field("title", "varchar", max_length=512)
    # 添加内容字段：content，字符串类型，最大长度8192字符
    schema.add_field("content", "varchar", max_length=8192)
    # 添加来源字段：source，字符串类型，最大长度1024字符
    schema.add_field("source", "varchar", max_length=1024)
    # 添加向量字段：dense_vector，浮点型向量，维度为传入的dim值
    schema.add_field("dense_vector", "float_vector", dim=dim)

    # 准备索引参数，用于优化向量数据库的查询效率
    index_params = client.prepare_index_params()
    # 为向量字段添加索引：使用HNSW索引类型，余弦相似度（COSINE）作为距离计算方式
    index_params.add_index("dense_vector", index_type="HNSW", metric_type="COSINE")
    # 根据定义的schema和索引参数，创建Milvus集合
    client.create_collection(collection_name, schema=schema, index_params=index_params)


def _insert_chunks_to_milvus(
        client: MilvusClient,
        collection_name: str,
        embedder: SentenceTransformer,
        chunks: List[Dict[str, str]],
) -> int:
    """
    私有函数：向Milvus插入文本块数据
    :param client: Milvus客户端实例
    :param collection_name: 目标集合名称
    :param embedder: 向量模型实例，用于生成文本向量
    :param chunks: 文本块列表，每个元素是包含content/title/source的字典
    :return: 成功插入的文本块数量
    """
    # 初始化成功插入的计数器，初始值为0
    inserted = 0
    # 遍历所有待插入的文本块
    for chunk in chunks:
        # 获取文本块内容，为空则赋值为空字符串，去除首尾空白字符
        content = (chunk.get("content") or "").strip()
        # 如果内容为空，跳过当前块，不插入数据库
        if not content:
            continue

        # 截取内容长度为7900字符以内，避免超出数据库字段最大长度限制
        content = content[:7900]
        # 获取来源信息，转为字符串并截取1000字符以内
        source = str(chunk.get("source", ""))[:1000]
        # 获取标题信息，转为字符串并截取500字符以内
        title = str(chunk.get("title", ""))[:500]

        # 使用向量模型将文本转换为向量，开启归一化，并转为列表格式
        vec = embedder.encode(content, normalize_embeddings=True).tolist()
        # 向Milvus指定集合插入数据（标题、内容、来源、向量）
        client.insert(
            collection_name,
            {
                "title": title,
                "content": content,
                "source": source,
                "dense_vector": vec,
            },
        )
        # 插入成功，计数器加1
        inserted += 1
    # 返回总插入成功的文本块数量
    return inserted


def _write_to_mysql(
        mysql_store: MySQLStore,
        role_code: str,
        sources: List[str],
        source_type: str = "url",
) -> None:
    """
    私有函数：将文档的元数据写入MySQL数据库
    :param mysql_store: MySQL存储工具实例
    :param role_code: 角色编码
    :param sources: 数据源列表（URL/PDF路径）
    :param source_type: 数据源类型，默认为url，可选pdf
    :return: 无返回值
    """
    # 捕获执行过程中的异常，避免程序崩溃
    try:
        # 使用MySQL工具的连接方法，建立数据库连接（上下文管理器自动关闭连接）
        with mysql_store._connect() as conn:
            # 创建数据库游标，用于执行SQL语句
            with conn.cursor() as cur:
                # 遍历所有数据源，逐个写入元数据
                for source in sources:
                    # 生成文档唯一编码：角色编码+数据源类型+数据源标识，截取120字符以内
                    doc_code = f"{role_code}:{source_type}:{os.path.basename(source) if source_type == 'pdf' else source}"[
                               :120]
                    # 生成文档标题：PDF用文件名，网页用角色配置的显示名称
                    title = os.path.basename(source) if source_type == 'pdf' else get_role_config(role_code)[
                        "display_name"]

                    # 执行插入SQL语句，存在主键冲突则执行更新操作
                    cur.execute(
                        """
                        INSERT INTO kb_documents (doc_code, title, source, category, version, status, updated_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY
                        UPDATE
                            title =
                        VALUES (title), source =
                        VALUES (source), category =
                        VALUES (category), version =
                        VALUES (version), status =
                        VALUES (status), updated_by =
                        VALUES (updated_by)
                        """,
                        (
                            # 文档编码，截取120字符
                            doc_code[:120],
                            # 文档标题，截取500字符
                            title[:500],
                            # 数据源地址/路径，截取256字符
                            source[:256],
                            # 分类（角色编码），截取128字符
                            role_code[:128],
                            # 文档版本，固定为v1
                            "v1",
                            # 文档状态，固定为active（启用）
                            "active",
                            # 更新人，固定为builder
                            "builder",
                        ),
                    )
    # 捕获所有异常，打印错误信息
    except Exception as e:
        print(f"[KB] 写入 MySQL 文档元信息失败: {e}")


def build_role_knowledge_base(
        role_code: str,
        urls: Optional[List[str]] = None,
        pdf_files: Optional[List[str]] = None,
        pdf_method: str = "auto",
) -> Dict:
    """
    核心函数：为指定角色构建专属知识库，支持网页/PDF两种数据源导入
    支持两种数据源：
    1. URL网页导入：从指定URL抓取内容
    2. PDF文件导入：从本地PDF文件解析内容

    :param role_code: 角色编码（如lawyer/doctor）
    :param urls: URL列表（可选，用于网页导入）
    :param pdf_files: PDF文件路径列表（可选，用于PDF导入）
    :param pdf_method: PDF解析方法，可选auto/pymupdf等
    :return: 构建结果统计字典
    """
    # 如果urls为None，赋值为空列表，避免空指针异常
    urls = urls or []
    # 如果pdf_files为None，赋值为空列表
    pdf_files = pdf_files or []

    # 判断：urls和pdf_files同时为空，抛出参数错误异常
    if not urls and not pdf_files:
        raise ValueError("urls 和 pdf_files 不能同时为空")

    # 根据角色编码，获取该角色的完整配置信息
    role = get_role_config(role_code)
    # 初始化MySQL存储工具实例
    mysql_store = MySQLStore()
    # 初始化Milvus客户端，连接指定地址的向量数据库
    client = MilvusClient(uri=MILVUS_URI)
    # 初始化向量模型，使用CPU设备运行（无GPU兼容）
    embedder = SentenceTransformer(EMBEDDING_MODEL_PATH, device="cpu")
    # 生成一个测试向量，用于获取向量模型的维度大小
    sample_vec = embedder.encode("hello", normalize_embeddings=True).tolist()
    # 确保Milvus中存在该角色对应的集合，传入向量维度
    _ensure_collection(client, role["milvus_collection"], len(sample_vec))

    # 初始化总插入文本块计数器
    total_inserted = 0
    # 初始化所有数据源列表
    all_sources = []

    # 判断：如果传入了URL列表，执行网页导入逻辑
    if urls:
        # 初始化网页加载器，传入URL列表
        loader = WebBaseLoader(web_paths=urls)
        # 加载网页，获取原始文档对象
        docs = loader.load()
        # 初始化文本分割器：块大小800字符，重叠120字符（保证语义连贯性）
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
        # 将长文档切分为小文本块
        langchain_chunks = splitter.split_documents(docs)

        # 初始化自定义格式的文本块列表
        chunks = []
        # 遍历LangChain格式的文本块，转换为自定义格式
        for chunk in langchain_chunks:
            chunks.append({
                # 文本内容
                "content": chunk.page_content,
                # 标题：优先用元数据中的title，无则用角色显示名称
                "title": chunk.metadata.get("title") or role["display_name"],
                # 来源：从元数据中获取
                "source": chunk.metadata.get("source") or "",
            })

        # 调用函数，将网页文本块插入Milvus
        inserted = _insert_chunks_to_milvus(client, role["milvus_collection"], embedder, chunks)
        # 累加到总计数器
        total_inserted += inserted
        # 将URL添加到所有数据源列表
        all_sources.extend(urls)
        # 将网页元数据写入MySQL
        _write_to_mysql(mysql_store, role_code, urls, "url")

    # 判断：如果传入了PDF文件列表，执行PDF导入逻辑
    if pdf_files:
        # 动态导入自定义的PDF解析工具
        from pdf_loader import parse_pdf

        # 遍历所有PDF文件路径
        for pdf_path in pdf_files:
            # 判断本地文件是否存在，不存在则打印提示并跳过
            if not os.path.exists(pdf_path):
                print(f"[KB] PDF文件不存在，跳过: {pdf_path}")
                continue

            # 捕获PDF解析/插入过程中的异常
            try:
                # 调用解析函数，将PDF转换为文本块
                chunks = parse_pdf(pdf_path, method=pdf_method)
                # 将PDF文本块插入Milvus
                inserted = _insert_chunks_to_milvus(client, role["milvus_collection"], embedder, chunks)
                # 累加到总计数器
                total_inserted += inserted
                # 将PDF路径添加到所有数据源列表
                all_sources.append(pdf_path)
                # 将PDF元数据写入MySQL
                _write_to_mysql(mysql_store, role_code, [pdf_path], "pdf")
                # 打印PDF处理成功信息
                print(f"[KB] 成功处理PDF: {pdf_path}, 生成 {inserted} 个块")
            # 捕获异常，打印错误信息
            except Exception as e:
                print(f"[KB] 处理PDF失败 {pdf_path}: {e}")

    # 返回知识库构建的完整统计结果
    return {
        "role_code": role_code,
        "collection_name": role["milvus_collection"],
        "source_count": len(all_sources),
        "chunk_count": total_inserted,
        "sources": all_sources,
    }


# 主程序入口：当脚本直接运行时执行测试逻辑
if __name__ == "__main__":
    # 定义测试用的URL（百度首页）
    demo_urls = ["https://baike.baidu.com"]
    # 打印测试标题
    print("=== 测试URL导入 ===")
    # 调用核心函数，为lawyer角色构建知识库，传入测试URL
    print(build_role_knowledge_base("lawyer", urls=demo_urls))

    # 打印测试标题
    print("\n=== 测试PDF导入 ===")
    # 定义测试用的PDF文件路径
    test_pdf_path = "test.pdf"
    # 判断PDF文件是否存在
    if os.path.exists(test_pdf_path):
        # 存在则为doctor角色构建知识库，导入PDF
        print(build_role_knowledge_base("doctor", pdf_files=[test_pdf_path], pdf_method="auto"))
    else:
        # 不存在则打印提示信息
        print(f"测试PDF文件不存在: {test_pdf_path}")