"""
知识图谱模块
- 使用LLM从文本中抽取实体关系三元组
- 使用NetworkX构建图结构
- 使用Pyvis生成交互式可视化HTML
"""

import os
import json
import networkx as nx
from pyvis.network import Network
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import MIMO_API_KEY, MIMO_BASE_URL, MIMO_MODEL, KG_TRIPLETS_PER_CHUNK, KG_OUTPUT_DIR, KG_BATCH_SIZE


class KnowledgeGraph:
    def __init__(self):
        self.client = OpenAI(
            api_key=MIMO_API_KEY,
            base_url=MIMO_BASE_URL
        )
        self.graph = nx.DiGraph()
        self.all_triplets = []

    def extract_triplets(self, text: str) -> list:
        """
        使用LLM从文本中抽取实体关系三元组
        返回：[(subject, relation, object), ...]
        """
        prompt = f"""请从以下文本中抽取实体关系三元组。

要求：
1. 每个三元组格式为 (主体, 关系, 客体)
2. 主体和客体是文本中的关键实体（人名、组织、概念、技术等）
3. 关系描述两者之间的联系
4. 最多抽取{KG_TRIPLETS_PER_CHUNK}个三元组
5. 只返回JSON数组，不要其他内容

文本：
{text}

输出格式示例：
[["人工智能", "包含", "深度学习"], ["Transformer", "提出者", "Google"]]

请直接输出JSON数组："""

        try:
            response = self.client.chat.completions.create(
                model=MIMO_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1024
            )
            content = response.choices[0].message.content.strip()
            if "[" in content and "]" in content:
                start = content.index("[")
                end = content.rindex("]") + 1
                triplets = json.loads(content[start:end])
                return [tuple(t) for t in triplets if len(t) == 3]
        except Exception as e:
            print(f"三元组抽取出错: {e}")
        return []

    def extract_triplets_batch(self, chunks: list) -> list:
        """
        批量抽取：将多个chunk合并成一次API调用
        """
        combined_text = "\n\n---分隔---\n\n".join(chunks)
        prompt = f"""请从以下{len(chunks)}段文本中分别抽取实体关系三元组。

要求：
1. 每个三元组格式为 (主体, 关系, 客体)
2. 主体和客体是关键实体
3. 每段最多{KG_TRIPLETS_PER_CHUNK}个三元组
4. 只返回JSON数组，不要其他内容

文本：
{combined_text}

输出格式：
[["实体A", "关系", "实体B"]]

请直接输出JSON数组："""

        try:
            response = self.client.chat.completions.create(
                model=MIMO_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2048
            )
            content = response.choices[0].message.content.strip()
            if "[" in content and "]" in content:
                start = content.index("[")
                end = content.rindex("]") + 1
                triplets = json.loads(content[start:end])
                return [tuple(t) for t in triplets if len(t) == 3]
        except Exception as e:
            print(f"批量抽取出错: {e}")
            # 回退到单条处理
            all_triplets = []
            for chunk in chunks:
                all_triplets.extend(self.extract_triplets(chunk))
            return all_triplets
        return []

    def build_graph_from_chunks(self, chunks: list) -> dict:
        """
        从所有文本块中抽取三元组并构建知识图谱
        使用批量合并 + 并发调用加速
        """
        self.graph.clear()
        self.all_triplets = []

        # 分批处理
        batches = []
        for i in range(0, len(chunks), KG_BATCH_SIZE):
            batches.append(chunks[i:i+KG_BATCH_SIZE])

        print(f"[知识图谱] 共{len(chunks)}个chunk，分为{len(batches)}批处理")

        # 并发调用API（最多3个并发）
        all_triplets = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(self.extract_triplets_batch, batch): i 
                      for i, batch in enumerate(batches)}
            for future in as_completed(futures):
                batch_idx = futures[future]
                try:
                    triplets = future.result()
                    all_triplets.extend(triplets)
                    print(f"  批次 {batch_idx+1}/{len(batches)} 完成，抽取 {len(triplets)} 个三元组")
                except Exception as e:
                    print(f"  批次 {batch_idx+1} 出错: {e}")

        self.all_triplets = all_triplets

        # 构建图
        for sub, rel, obj in all_triplets:
            if not self.graph.has_node(sub):
                self.graph.add_node(sub, label=sub)
            if not self.graph.has_node(obj):
                self.graph.add_node(obj, label=obj)
            self.graph.add_edge(sub, obj, label=rel, title=rel)

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "total_triplets": len(self.all_triplets)
        }

    def generate_html(self, filename: str = "knowledge_graph.html") -> str:
        """
        生成交互式知识图谱HTML文件
        返回：HTML文件路径
        """
        os.makedirs(KG_OUTPUT_DIR, exist_ok=True)
        filepath = os.path.join(KG_OUTPUT_DIR, filename)

        # 创建Pyvis网络
        net = Network(
            height="600px",
            width="100%",
            bgcolor="#1a1a2e",
            font_color="white",
            directed=True,
            notebook=False
        )

        # 配置物理引擎
        net.set_options("""
        {
            "physics": {
                "forceAtlas2Based": {
                    "gravitationalConstant": -100,
                    "centralGravity": 0.01,
                    "springLength": 200,
                    "springConstant": 0.08,
                    "damping": 0.4
                },
                "maxVelocity": 50,
                "solver": "forceAtlas2Based",
                "stabilization": {
                    "enabled": true,
                    "iterations": 1000
                }
            },
            "nodes": {
                "shape": "dot",
                "size": 20,
                "font": {
                    "size": 14,
                    "face": "Microsoft YaHei"
                },
                "borderWidth": 2,
                "shadow": true
            },
            "edges": {
                "font": {
                    "size": 12,
                    "face": "Microsoft YaHei",
                    "align": "middle"
                },
                "arrows": {
                    "to": {
                        "enabled": true,
                        "scaleFactor": 0.5
                    }
                },
                "smooth": {
                    "type": "curvedCW",
                    "roundness": 0.2
                },
                "shadow": true
            }
        }
        """)

        # 颜色池
        colors = [
            "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
            "#9b59b6", "#1abc9c", "#e67e22", "#34495e"
        ]

        # 添加节点
        node_list = list(self.graph.nodes())
        for i, node in enumerate(node_list):
            color = colors[i % len(colors)]
            net.add_node(
                node,
                label=node,
                color=color,
                title=f"实体: {node}"
            )

        # 添加边
        for u, v, data in self.graph.edges(data=True):
            label = data.get("label", "")
            net.add_edge(u, v, label=label, title=label)

        # 生成HTML
        net.save_graph(filepath)

        # 添加中文标题
        with open(filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()
        html_content = html_content.replace(
            '<head>',
            '<head><meta charset="UTF-8"><title>知识图谱</title>'
        )
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return filepath

    def get_triplets_text(self) -> str:
        """返回三元组的文本展示"""
        if not self.all_triplets:
            return "暂无三元组信息"
        lines = []
        for i, (s, r, o) in enumerate(self.all_triplets, 1):
            lines.append(f"{i}. ({s}) ——[{r}]——> ({o})")
        return "\n".join(lines)
