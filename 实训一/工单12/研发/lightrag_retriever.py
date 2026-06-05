"""
LightRAG 检索模块 - 基于知识图谱的双层检索
在 FAISS 向量检索(低层)基础上,增加知识图谱检索(高层),实现双层检索融合。
"""
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import networkx as nx
except ImportError:
    nx = None

from config import (
    FAISS_INDEX_PATH,
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_KEY_2,
    DEEPSEEK_API_BASE,
    DEEPSEEK_API_BASE_2,
    DEEPSEEK_MODEL,
    DEEPSEEK_MODEL_2,
    LIGHTRAG_ENTITY_TYPES,
    LIGHTRAG_GRAPH_PATH,
    LIGHTRAG_HOP,
    LIGHTRAG_RELATION_TYPES,
    LIGHTRAG_TOP_K,
    SIMILARITY_THRESHOLD,
    TOP_K,
    BM25_TOP_K,
)
from llm_agent import DeepSeekLLM


# ═══════════════════════════════════════════════════════════
# 实体抽取 Prompt 模板
# ═══════════════════════════════════════════════════════════

ENTITY_EXTRACTION_PROMPT = """请从以下文本中提取实体和关系。返回 JSON 格式:
{{
  "entities": [{{"name": "实体名", "type": "实体类型", "description": "简短描述"}}],
  "relationships": [{{"source": "源实体", "target": "目标实体", "relation": "关系类型", "description": "关系描述"}}]
}}
文本:{text}
注意:实体名要规范化,去除多余空格和标点。只提取明确的实体和关系,不要猜测。
实体类型只能从以下类型中选择:{entity_types}
关系类型只能从以下类型中选择:{relation_types}"""

QUERY_ANALYSIS_PROMPT = """请分析以下查询,判断查询类型并提取关键词。返回 JSON 格式:
{{
  "query_type": "concrete 或 abstract",
  "entities": ["从查询中提取的实体名"],
  "keywords": ["与查询相关的关键词"],
  "description": "查询的简要描述"
}}
查询:{query}
说明:
- concrete 查询:询问具体的实体、人物、数字、事件等(如"XX公司的营收是多少")
- abstract 查询:询问趋势、对比、总结、概括等(如"哪些公司之间存在竞争关系")"""


# ═══════════════════════════════════════════════════════════
# GraphBuilder - 知识图谱构建
# ═══════════════════════════════════════════════════════════

class GraphBuilder:
    """知识图谱构建器:从文档 chunks 中抽取实体和关系,构建 NetworkX 图。"""

    def __init__(self, batch_size: int = 10, max_workers: int = 4):
        if nx is None:
            raise ImportError("请安装 networkx: pip install networkx")
        self.graph = nx.Graph()
        # 使用 DEEPSEEK_API_KEY_2(图构建专用 Key),和问答分流;未配则回退到主 Key
        graph_api_key = DEEPSEEK_API_KEY_2 or DEEPSEEK_API_KEY
        graph_api_base = DEEPSEEK_API_BASE_2 if DEEPSEEK_API_KEY_2 else DEEPSEEK_API_BASE
        graph_model = DEEPSEEK_MODEL_2 if DEEPSEEK_API_KEY_2 else DEEPSEEK_MODEL
        self.llm = DeepSeekLLM(api_key=graph_api_key, api_base=graph_api_base, model=graph_model)
        self.batch_size = batch_size
        self.max_workers = max_workers
        print(f"[GraphBuilder] 初始化完成(batch_size={batch_size}, max_workers={max_workers})")

    def _is_valuable_chunk(self, text: str) -> bool:
        """判断文本块是否值得抽取实体(跳过纯数字、表格、页眉页脚等)。"""
        text = text.strip()
        if len(text) < 30:
            return False
        # 纯数字/金额表格
        if re.match(r'^[\d\s,,.%、/::]+$', text):
            return False
        # 中文字符占比过低(可能是表格数据)
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        if len(text) > 0 and chinese_chars / len(text) < 0.15:
            return False
        return True

    def build_from_chunks(self, chunks: List[Dict]) -> nx.Graph:
        """从文档 chunks 批量并发构建知识图谱。"""
        print(f"\n[GraphBuilder] 开始从 {len(chunks)} 个文本块构建知识图谱...")

        # 过滤空文本块和低价值块
        valid_chunks = [
            chunk for chunk in chunks
            if self._is_valuable_chunk(chunk.get("content", ""))
        ]
        print(f"[GraphBuilder] 有效文本块: {len(valid_chunks)}/{len(chunks)}(跳过 {len(chunks) - len(valid_chunks)} 个低价值块)")

        # 分批:每 batch_size 个 chunk 合并为一个 LLM 调用
        batches = []
        for i in range(0, len(valid_chunks), self.batch_size):
            batch = valid_chunks[i:i + self.batch_size]
            batches.append(batch)
        print(f"[GraphBuilder] 分为 {len(batches)} 个批次(每批 {self.batch_size} 个块),并发 workers={self.max_workers}")

        # 并发处理批次(带限流)
        results = [None] * len(batches)
        completed_count = 0

        def process_batch(args):
            batch_idx, batch = args
            combined_parts = []
            for j, chunk in enumerate(batch):
                text = chunk.get("content", "")[:1000]
                combined_parts.append(f"--- 文本段 {j + 1} ---\n{text}")
            combined_text = "\n\n".join(combined_parts)
            entities, relationships = self._extract_entities(combined_text, {})
            return batch_idx, entities, relationships

        # 分批提交,每批间隔 1s,避免瞬时并发过高
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for idx, batch in enumerate(batches):
                future = executor.submit(process_batch, (idx, batch))
                futures[future] = idx
                if (idx + 1) % self.max_workers == 0:
                    time.sleep(1.0)  # 每提交一批 workers 数量的任务后暂停 1s

            for future in as_completed(futures):
                try:
                    batch_idx, entities, relationships = future.result()
                    results[batch_idx] = (entities, relationships)
                except Exception as exc:
                    print(f"  [并发] 批次处理异常: {exc}")
                    results[futures[future]] = ([], [])

                completed_count += 1
                if completed_count % 10 == 0 or completed_count == len(batches):
                    print(f"[GraphBuilder] 进度: {completed_count}/{len(batches)} 批 "
                          f"({completed_count * self.batch_size}/{len(valid_chunks)} 块), "
                          f"节点: {self.graph.number_of_nodes()}, 边: {self.graph.number_of_edges()}")

        # 批量合并到图中（先收集再统一加锁写入）
        total_entities = 0
        total_relations = 0
        merged_batches = 0
        for batch_idx, (entities, relationships) in enumerate(results):
            if entities is None:
                continue
            if entities or relationships:
                merged_batches += 1
                print(f"  [合并] 批次 {batch_idx}: 实体 {len(entities)} 个, 关系 {len(relationships)} 个")
            for entity in entities:
                self._add_entity(entity)
            for rel in relationships:
                self._add_relationship(rel)
            total_entities += len(entities)
            total_relations += len(relationships)

        print(f"[GraphBuilder] 合并完成: {merged_batches} 个有效批次，" 
              f"抽取实体 {total_entities} 个, 关系 {total_relations} 条")
        print(f"[GraphBuilder] 图构建完成: {self.graph.number_of_nodes()} 个节点, " 
              f"{self.graph.number_of_edges()} 条边")

        # 保存图
        self._save_graph()
        return self.graph

    def _extract_entities(self, text: str, chunk: Dict, max_retries: int = 3) -> Tuple[List[Dict], List[Dict]]:
        """调用 LLM 从文本中抽取实体和关系(含重试机制)。"""
        max_len = 5000
        if len(text) > max_len:
            text = text[:max_len]

        prompt = ENTITY_EXTRACTION_PROMPT.format(
            text=text,
            entity_types="、".join(LIGHTRAG_ENTITY_TYPES),
            relation_types="、".join(LIGHTRAG_RELATION_TYPES),
        )

        for attempt in range(max_retries):
            try:
                time.sleep(0.5)  # 每次调用前等待 0.5s,分散请求
                response = self.llm.generate(prompt, max_tokens=3000, temperature=0.1)
                # 空响应也触发重试
                if not response or not response.strip():
                    print(f"  [空响应] API 返回空内容,重试 ({attempt + 1}/{max_retries})...")
                    time.sleep((2 ** attempt) * 2)
                    continue
                entities, relationships = self._parse_extraction_response(response)
                return entities, relationships
            except Exception as exc:
                error_msg = str(exc)
                if "Too many requests" in error_msg or "429" in error_msg:
                    wait_time = (2 ** attempt) * 5  # 5s, 10s, 20s
                    print(f"  [限流] 等待 {wait_time}s 后重试 ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                elif "Read timed out" in error_msg or "timeout" in error_msg.lower():
                    wait_time = (2 ** attempt) * 3  # 3s, 6s, 12s
                    print(f"  [超时] 等待 {wait_time}s 后重试 ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    print(f"  [抽取] LLM 调用失败: {exc}")
                    return [], []

        print(f"  [抽取] 重试 {max_retries} 次仍失败,跳过")
        return [], []

    def _parse_extraction_response(self, response: str) -> Tuple[List[Dict], List[Dict]]:
        """解析 LLM 返回的实体抽取结果,支持多种格式容错。"""
        entities = []
        relationships = []

        # 尝试直接解析 JSON
        data = self._try_parse_json(response)
        if data is None:
            print("  [解析] JSON 解析失败,尝试正则提取...")
            print(f"  [调试] LLM 原始返回(前500字): {response[:500]}")
            return entities, relationships

        # 提取实体
        raw_entities = data.get("entities", [])
        for ent in raw_entities:
            if isinstance(ent, dict) and ent.get("name"):
                name = str(ent["name"]).strip()
                etype = str(ent.get("type", "未知")).strip()
                desc = str(ent.get("description", "")).strip()
                if name and len(name) <= 50:  # 过滤异常长的实体名
                    entities.append({"name": name, "type": etype, "description": desc})

        # 提取关系
        raw_rels = data.get("relationships", [])
        for rel in raw_rels:
            if isinstance(rel, dict) and rel.get("source") and rel.get("target"):
                source = str(rel["source"]).strip()
                target = str(rel["target"]).strip()
                relation = str(rel.get("relation", "相关")).strip()
                desc = str(rel.get("description", "")).strip()
                if source and target and len(source) <= 50 and len(target) <= 50:
                    relationships.append({
                        "source": source,
                        "target": target,
                        "relation": relation,
                        "description": desc,
                    })

        return entities, relationships

    def _try_parse_json(self, text: str) -> Optional[dict]:
        """尝试从文本中解析 JSON,支持多种容错方式。"""
        if not text or not text.strip():
            return None

        # 方式1:直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 方式2:提取 ```json ... ``` 代码块
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
                print(f"  [调试] 方式2解析成功,实体数: {len(result.get('entities', []))}")
                return result
            except json.JSONDecodeError as e:
                print(f"  [调试] 方式2 JSON 解析错误: {e}")
                print(f"  [调试] 提取内容(前200字): {json_match.group(1)[:200]}")
        else:
            # 方式2没匹配到,看看有没有 ```json
            if "```json" in text:
                print(f"  [调试] 发现 ```json 但正则未匹配,响应长度: {len(text)}")
                print(f"  [调试] 响应末尾(后100字): {text[-100:]}")
            else:
                print(f"  [调试] 响应中无 ```json 标记,长度: {len(text)}")

        # 方式3:提取 ```json 开头的代码块(没有结尾 ``` 的情况,LLM 输出被截断)
        json_start_match = re.search(r"```json\s*(.*)", text, re.DOTALL)
        if json_start_match:
            content = json_start_match.group(1).strip()
            # 去掉末尾可能残留的 ```
            content = re.sub(r"\s*```\s*$", "", content)
            try:
                result = json.loads(content)
                print(f"  [调试] 方式3解析成功,实体数: {len(result.get('entities', []))}")
                return result
            except json.JSONDecodeError:
                # 尝试补全截断的 JSON
                for closing in ["}}]}", "}}]", "}}", "}"]:
                    try:
                        result = json.loads(content + closing)
                        print(f"  [调试] 方式3补全解析成功(补'{closing}'),实体数: {len(result.get('entities', []))}")
                        return result
                    except json.JSONDecodeError:
                        continue

        # 方式4:提取第一个 { ... } 块
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # 方式5:尝试修复常见 JSON 格式问题(尾逗号等)
        cleaned = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        return None

    def _add_entity(self, entity: Dict):
        """添加实体节点到图中,相同实体名(忽略大小写)合并。"""
        name = entity["name"]
        name_lower = name.lower()

        # 查找已有的同名节点(忽略大小写)
        existing_node = None
        for node in self.graph.nodes():
            if node.lower() == name_lower:
                existing_node = node
                break

        if existing_node:
            # 合并:更新描述
            node_data = self.graph.nodes[existing_node]
            existing_desc = node_data.get("description", "")
            new_desc = entity.get("description", "")
            if new_desc and new_desc not in existing_desc:
                node_data["description"] = f"{existing_desc}; {new_desc}" if existing_desc else new_desc
            # 更新类型(如果原来是未知)
            if node_data.get("type", "未知") == "未知" and entity.get("type", "未知") != "未知":
                node_data["type"] = entity["type"]
            # 增加出现次数
            node_data["count"] = node_data.get("count", 1) + 1
        else:
            self.graph.add_node(
                name,
                type=entity.get("type", "未知"),
                description=entity.get("description", ""),
                count=1,
            )

    def _add_relationship(self, rel: Dict):
        """添加关系边到图中。"""
        source = rel["source"]
        target = rel["target"]

        # 确保源和目标节点存在
        source_node = self._find_node(source)
        target_node = self._find_node(target)

        if source_node is None or target_node is None:
            # 节点不存在,先创建
            if source_node is None:
                self.graph.add_node(source, type="未知", description="", count=1)
                source_node = source
            if target_node is None:
                self.graph.add_node(target, type="未知", description="", count=1)
                target_node = target

        # 添加或更新边
        if self.graph.has_edge(source_node, target_node):
            # 边已存在,更新关系描述
            edge_data = self.graph[source_node][target_node]
            existing_desc = edge_data.get("description", "")
            new_desc = rel.get("description", "")
            if new_desc and new_desc not in existing_desc:
                edge_data["description"] = f"{existing_desc}; {new_desc}" if existing_desc else new_desc
            # 增加权重
            edge_data["weight"] = edge_data.get("weight", 1) + 1
        else:
            self.graph.add_edge(
                source_node,
                target_node,
                relation=rel.get("relation", "相关"),
                description=rel.get("description", ""),
                weight=1,
            )

    def _find_node(self, name: str) -> Optional[str]:
        """在图中查找节点(忽略大小写),返回实际节点名。"""
        name_lower = name.lower()
        for node in self.graph.nodes():
            if node.lower() == name_lower:
                return node
        return None

    def _save_graph(self):
        """将图保存为 JSON 文件。"""
        os.makedirs(os.path.dirname(LIGHTRAG_GRAPH_PATH) or ".", exist_ok=True)

        graph_data = {
            "nodes": [],
            "edges": [],
        }

        for node, data in self.graph.nodes(data=True):
            graph_data["nodes"].append({
                "name": node,
                "type": data.get("type", "未知"),
                "description": data.get("description", ""),
                "count": data.get("count", 1),
            })

        for source, target, data in self.graph.edges(data=True):
            graph_data["edges"].append({
                "source": source,
                "target": target,
                "relation": data.get("relation", "相关"),
                "description": data.get("description", ""),
                "weight": data.get("weight", 1),
            })

        with open(LIGHTRAG_GRAPH_PATH, "w", encoding="utf-8") as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)

        print(f"[GraphBuilder] 图已保存到 {LIGHTRAG_GRAPH_PATH}")


# ═══════════════════════════════════════════════════════════
# GraphRetriever - 知识图谱检索
# ═══════════════════════════════════════════════════════════

class GraphRetriever:
    """知识图谱检索器:根据查询在图中查找相关实体和关系。"""

    def __init__(self):
        if nx is None:
            raise ImportError("请安装 networkx: pip install networkx")
        self.graph = nx.Graph()
        # 使用 DEEPSEEK_API_KEY_2(图构建专用 Key);未配则回退到主 Key
        graph_api_key = DEEPSEEK_API_KEY_2 or DEEPSEEK_API_KEY
        graph_api_base = DEEPSEEK_API_BASE_2 if DEEPSEEK_API_KEY_2 else DEEPSEEK_API_BASE
        graph_model = DEEPSEEK_MODEL_2 if DEEPSEEK_API_KEY_2 else DEEPSEEK_MODEL
        self.llm = DeepSeekLLM(api_key=graph_api_key, api_base=graph_api_base, model=graph_model)
        self.node_profiles: Dict[str, str] = {}  # 实体名 -> 描述 profile
        print("[GraphRetriever] 初始化完成")

    def load_graph(self):
        """从 JSON 文件加载知识图谱。"""
        if not os.path.exists(LIGHTRAG_GRAPH_PATH):
            raise FileNotFoundError(f"知识图谱文件不存在: {LIGHTRAG_GRAPH_PATH}")

        print(f"[GraphRetriever] 加载知识图谱: {LIGHTRAG_GRAPH_PATH}")
        with open(LIGHTRAG_GRAPH_PATH, "r", encoding="utf-8") as f:
            graph_data = json.load(f)

        # 构建 NetworkX 图
        self.graph = nx.Graph()

        for node_data in graph_data.get("nodes", []):
            name = node_data["name"]
            self.graph.add_node(
                name,
                type=node_data.get("type", "未知"),
                description=node_data.get("description", ""),
                count=node_data.get("count", 1),
            )
            # 构建 profile
            desc = node_data.get("description", "")
            etype = node_data.get("type", "未知")
            self.node_profiles[name] = f"[{etype}] {name}: {desc}" if desc else f"[{etype}] {name}"

        for edge_data in graph_data.get("edges", []):
            self.graph.add_edge(
                edge_data["source"],
                edge_data["target"],
                relation=edge_data.get("relation", "相关"),
                description=edge_data.get("description", ""),
                weight=edge_data.get("weight", 1),
            )

        print(f"[GraphRetriever] 图加载完成: {self.graph.number_of_nodes()} 个节点, "
              f"{self.graph.number_of_edges()} 条边")

    def retrieve(self, query: str, k: int = LIGHTRAG_TOP_K, hop: int = LIGHTRAG_HOP) -> List[Dict]:
        """根据查询在知识图谱中检索相关信息。"""
        print(f"\n[GraphRetriever] 查询: {query[:50]}...")

        # 1. 分析查询类型
        query_info = self._analyze_query(query)
        query_type = query_info.get("query_type", "concrete")
        entities = query_info.get("entities", [])
        keywords = query_info.get("keywords", [])
        print(f"  [查询分析] 类型: {query_type}, 实体: {entities}, 关键词: {keywords}")

        # 2. 根据查询类型选择检索策略
        if query_type == "concrete":
            results = self._concrete_retrieve(entities, keywords, k, hop)
        else:
            results = self._abstract_retrieve(entities, keywords, k, hop)

        print(f"  [检索结果] 返回 {len(results)} 条结果")
        return results

    def _analyze_query(self, query: str) -> Dict:
        """调用 LLM 分析查询类型和提取关键词。"""
        prompt = QUERY_ANALYSIS_PROMPT.format(query=query)

        try:
            response = self.llm.generate(prompt, max_tokens=300, temperature=0.1)
            data = self._try_parse_json(response)
            if data:
                return data
        except Exception as exc:
            print(f"  [查询分析] LLM 调用失败: {exc}")

        # 兜底:简单关键词提取
        return {
            "query_type": "concrete",
            "entities": [query],
            "keywords": list(set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]+", query))),
            "description": query,
        }

    def _concrete_retrieve(self, entities: List[str], keywords: List[str], k: int, hop: int) -> List[Dict]:
        """具体查询检索:查找匹配的实体节点,取其 1-2 跳邻居。"""
        results = []
        visited_entities = set()

        # 查找匹配的实体节点
        matched_nodes = self._find_matching_nodes(entities + keywords)
        print(f"  [具体检索] 匹配到 {len(matched_nodes)} 个节点: {matched_nodes[:5]}")

        for node in matched_nodes:
            if node in visited_entities:
                continue
            visited_entities.add(node)

            # 获取节点信息
            node_data = self.graph.nodes[node]
            node_profile = self.node_profiles.get(node, "")
            results.append({
                "content": node_profile,
                "source": f"知识图谱-实体: {node}",
                "page": "图谱",
                "chunk_id": f"graph_entity_{node}",
                "similarity": 1.0,
                "distance": 0.0,
                "retrieval_method": "lightrag_graph",
            })

            # 获取 1-hop 邻居
            if hop >= 1:
                neighbors_1 = list(self.graph.neighbors(node))
                for neighbor in neighbors_1[:k]:
                    if neighbor not in visited_entities:
                        visited_entities.add(neighbor)
                        edge_data = self.graph[node][neighbor]
                        neighbor_profile = self.node_profiles.get(neighbor, "")
                        relation_desc = edge_data.get("description", "")
                        relation_type = edge_data.get("relation", "相关")

                        content = (
                            f"{node_profile}\n"
                            f"  --[{relation_type}]--> {neighbor_profile}\n"
                            f"  关系描述: {relation_desc}"
                        )
                        results.append({
                            "content": content,
                            "source": f"知识图谱-关系: {node} → {neighbor}",
                            "page": "图谱",
                            "chunk_id": f"graph_rel_{node}_{neighbor}",
                            "similarity": 0.9,
                            "distance": 0.1,
                            "retrieval_method": "lightrag_graph",
                        })

            # 获取 2-hop 邻居
            if hop >= 2:
                neighbors_1 = list(self.graph.neighbors(node))
                for n1 in neighbors_1[:3]:  # 限制 1-hop 数量
                    neighbors_2 = list(self.graph.neighbors(n1))
                    for n2 in neighbors_2[:2]:  # 每个 1-hop 最多取 2 个 2-hop
                        if n2 not in visited_entities and n2 != node:
                            visited_entities.add(n2)
                            n2_profile = self.node_profiles.get(n2, "")
                            content = (
                                f"起点: {node_profile}\n"
                                f"中间: {self.node_profiles.get(n1, n1)}\n"
                                f"终点: {n2_profile}"
                            )
                            results.append({
                                "content": content,
                                "source": f"知识图谱-路径: {node} → {n1} → {n2}",
                                "page": "图谱",
                                "chunk_id": f"graph_path_{node}_{n1}_{n2}",
                                "similarity": 0.7,
                                "distance": 0.3,
                                "retrieval_method": "lightrag_graph",
                            })

        return results[:k]

    def _abstract_retrieve(self, entities: List[str], keywords: List[str], k: int, hop: int) -> List[Dict]:
        """抽象查询检索:匹配图中的主题/关系模式,返回相关子图的摘要。"""
        results = []

        # 1. 查找所有匹配关键词的节点
        matched_nodes = self._find_matching_nodes(entities + keywords)
        print(f"  [抽象检索] 匹配到 {len(matched_nodes)} 个节点")

        if not matched_nodes:
            # 如果没有匹配节点,返回图的整体摘要
            summary = self._get_graph_summary()
            results.append({
                "content": summary,
                "source": "知识图谱-全局摘要",
                "page": "图谱",
                "chunk_id": "graph_summary",
                "similarity": 0.5,
                "distance": 0.5,
                "retrieval_method": "lightrag_graph",
            })
            return results

        # 2. 提取匹配节点相关的子图
        subgraph_nodes = set(matched_nodes)
        for node in matched_nodes:
            # 扩展 1-hop
            neighbors = list(self.graph.neighbors(node))
            subgraph_nodes.update(neighbors[:3])

        # 3. 生成子图摘要
        subgraph = self.graph.subgraph(subgraph_nodes)
        summary_parts = []

        # 节点信息
        for node in subgraph.nodes():
            profile = self.node_profiles.get(node, "")
            if profile:
                summary_parts.append(profile)

        # 关系信息
        for source, target, data in subgraph.edges(data=True):
            relation = data.get("relation", "相关")
            desc = data.get("description", "")
            summary_parts.append(f"{source} --[{relation}]--> {target}: {desc}")

        content = "知识图谱相关信息:\n" + "\n".join(summary_parts[:20])  # 限制长度
        results.append({
            "content": content,
            "source": "知识图谱-子图摘要",
            "page": "图谱",
            "chunk_id": "graph_subgraph",
            "similarity": 0.8,
            "distance": 0.2,
            "retrieval_method": "lightrag_graph",
        })

        return results[:k]

    def _find_matching_nodes(self, terms: List[str]) -> List[str]:
        """在图中查找匹配的节点(模糊匹配,忽略大小写)。"""
        matched = []
        terms_lower = [t.lower() for t in terms if t]

        for node in self.graph.nodes():
            node_lower = node.lower()
            for term in terms_lower:
                if term in node_lower or node_lower in term:
                    matched.append(node)
                    break

        # 按节点的出现次数排序
        matched.sort(key=lambda n: self.graph.nodes[n].get("count", 1), reverse=True)
        return matched

    def _get_graph_summary(self) -> str:
        """生成知识图谱的全局摘要。"""
        nodes = list(self.graph.nodes(data=True))
        edges = list(self.graph.edges(data=True))

        # 按类型统计节点
        type_counts = {}
        for _, data in nodes:
            t = data.get("type", "未知")
            type_counts[t] = type_counts.get(t, 0) + 1

        # 按关系类型统计边
        rel_counts = {}
        for _, _, data in edges:
            r = data.get("relation", "相关")
            rel_counts[r] = rel_counts.get(r, 0) + 1

        parts = [
            f"知识图谱包含 {len(nodes)} 个实体节点,{len(edges)} 条关系边。",
            f"实体类型分布:{', '.join(f'{t}({c})' for t, c in type_counts.items())}",
            f"关系类型分布:{', '.join(f'{r}({c})' for r, c in rel_counts.items())}",
        ]

        # 列出高频实体
        top_nodes = sorted(nodes, key=lambda x: x[1].get("count", 1), reverse=True)[:10]
        if top_nodes:
            parts.append("高频实体:" + "、".join(n[0] for n in top_nodes))

        return "\n".join(parts)

    def _try_parse_json(self, text: str) -> Optional[dict]:
        """尝试从文本中解析 JSON。"""
        # 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 提取代码块
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 提取 { ... }
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None


# ═══════════════════════════════════════════════════════════
# LightRAGRetriever - 统一入口(双层检索融合)
# ═══════════════════════════════════════════════════════════

class LightRAGRetriever:
    """LightRAG 统一检索器:组合 FAISS 向量检索(低层)和知识图谱检索(高层)。
    使用 RRF 融合两层结果。"""

    def __init__(self):
        self.graph_builder = None
        self.graph_retriever = None
        self.vector_retriever = None  # FAISSRetriever 或 LocalRetriever
        self.embedding_manager = None
        self.chunks: List[Dict] = []
        print("[LightRAGRetriever] 初始化完成")

    def initialize(self, chunks: List[Dict]):
        """构建 FAISS 向量索引 + 知识图谱。"""
        from embedding import EmbeddingManager, FAISSRetriever, LocalRetriever
        import faiss as _faiss

        self.chunks = chunks

        # 1. 构建向量索引(低层)
        print("\n[LightRAGRetriever] 构建向量索引(低层)...")
        self.embedding_manager = EmbeddingManager()
        embeddings = self.embedding_manager.embed_texts(chunks)

        if _faiss is not None:
            self.vector_retriever = FAISSRetriever()
            self.vector_retriever.build_index(chunks, embeddings)
        else:
            self.vector_retriever = LocalRetriever()
            self.vector_retriever.build_index(chunks, embeddings)
            print("⚠️  未安装 faiss-cpu,向量检索使用本地模式")

        # 2. 构建知识图谱(高层)
        print("\n[LightRAGRetriever] 构建知识图谱(高层)...")
        self.graph_builder = GraphBuilder()
        self.graph_builder.build_from_chunks(chunks)

        # 初始化图检索器
        self.graph_retriever = GraphRetriever()
        self.graph_retriever.load_graph()

        print(f"\n[LightRAGRetriever] 初始化完成")

    def load_from_index(self):
        """从磁盘加载已有索引和图。"""
        from embedding import EmbeddingManager, FAISSRetriever, LocalRetriever
        import faiss as _faiss

        # 1. 加载向量索引
        print("[LightRAGRetriever] 加载向量索引...")
        self.embedding_manager = EmbeddingManager()
        if _faiss is not None:
            self.vector_retriever = FAISSRetriever()
            try:
                self.vector_retriever.load_index()
            except Exception:
                self.vector_retriever = LocalRetriever()
                self.vector_retriever.load_index()
        else:
            self.vector_retriever = LocalRetriever()
            self.vector_retriever.load_index()

        if isinstance(self.vector_retriever, LocalRetriever) and self.vector_retriever.embeddings is None and self.vector_retriever.chunks:
            self.vector_retriever.embeddings = self.embedding_manager.embed_texts(self.vector_retriever.chunks)

        self.chunks = getattr(self.vector_retriever, 'chunks', [])

        # 2. 加载知识图谱
        print("[LightRAGRetriever] 加载知识图谱...")
        self.graph_retriever = GraphRetriever()
        self.graph_retriever.load_graph()

        print(f"[LightRAGRetriever] 加载完成")

    def retrieve(self, query: str, k: int = TOP_K) -> List[Dict]:
        """双层检索融合:FAISS 向量检索 + 知识图谱检索 → RRF 融合。"""
        print(f"\n[LightRAGRetriever] 双层检索: {query[:50]}...")

        # 1. 低层:FAISS 向量检索
        query_embedding = self.embedding_manager.get_embedding(query)
        vector_results = self.vector_retriever.retrieve(query_embedding, k=BM25_TOP_K, threshold=0.01)
        print(f"  [低层-向量] 召回 {len(vector_results)} 个结果")

        # 2. 高层:知识图谱检索
        graph_results = self.graph_retriever.retrieve(query, k=LIGHTRAG_TOP_K)
        print(f"  [高层-图谱] 召回 {len(graph_results)} 个结果")

        # 3. RRF 融合
        fused_results = self._rrf_fusion(vector_results, graph_results)
        print(f"  [RRF融合] 融合后 {len(fused_results)} 个结果")

        return fused_results[:k]

    def _rrf_fusion(self, vector_results: List[Dict], graph_results: List[Dict], rrf_k: int = 60) -> List[Dict]:
        """Reciprocal Rank Fusion 融合向量检索和图谱检索结果。"""
        doc_scores: Dict[str, float] = {}
        doc_map: Dict[str, Dict] = {}

        # 向量检索结果打分
        for rank, doc in enumerate(vector_results):
            doc_id = self._get_doc_id(doc)
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + 1.0 / (rrf_k + rank + 1)
            doc_map[doc_id] = doc

        # 图谱检索结果打分
        for rank, doc in enumerate(graph_results):
            doc_id = self._get_doc_id(doc)
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + 1.0 / (rrf_k + rank + 1)
            doc_map[doc_id] = doc

        # 按 RRF 分数排序
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for doc_id, rrf_score in sorted_docs:
            doc = doc_map[doc_id].copy()
            doc["rrf_score"] = rrf_score
            doc["retrieval_method"] = "lightrag"
            results.append(doc)

        return results

    def _get_doc_id(self, doc: Dict) -> str:
        """生成文档唯一标识。"""
        chunk_id = doc.get("chunk_id", "")
        source = doc.get("source", "")
        page = doc.get("page", "")
        return f"{chunk_id}_{source}_{page}"


if __name__ == "__main__":
    print("LightRAG 检索模块测试")
    print(f"图谱路径: {LIGHTRAG_GRAPH_PATH}")
    print(f"实体类型: {LIGHTRAG_ENTITY_TYPES}")
    print(f"关系类型: {LIGHTRAG_RELATION_TYPES}")
