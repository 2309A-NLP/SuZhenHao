# 导入数值计算库，用于数值相关操作（本代码中未直接使用，但保留导入）
import numpy as np
# 导入计数器工具，用于统计查询词的词频
from collections import Counter
# 导入数学库，用于计算对数等数学运算
import math


# 定义BM25类，用于文本检索的相关性打分算法
class BM25(object):
    # 构造函数：初始化BM25模型参数
    def __init__(self, docs, k1=1.3, k2=1.5, b=0.75, topk=10):
        # 存储传入的文档字典（key：文档ID，value：分词后的文档词列表）
        self.docs = docs
        # 计算并存储文档总数量
        self.Numdocs = len(docs)
        # 计算并存储所有文档的平均长度
        self.avg_doclen = sum([len(doc) for doc in docs.values()]) / self.Numdocs
        # 计算并存储每个文档的词频（TF）
        self.tf = self.calculate_tf()
        # 计算并存储每个词的逆文档频率（IDF）
        self.idf = self.calculate_idf()
        # BM25算法参数k1：控制文档词频饱和度
        self.k1 = k1
        # BM25算法参数k2：控制查询词频饱和度
        self.k2 = k2
        # BM25算法参数b：控制文档长度对权重的影响
        self.b = b
        # 检索时返回的Top-K结果数量，默认返回前10个最相关文档
        self.topk = topk

    # 计算IDF（逆文档频率）：衡量词的重要性，稀有词权重更高
    def calculate_idf(self):
        # 初始化空字典，存储每个词出现在多少个文档中
        idf = {}
        # 遍历所有文档
        for doc in self.docs.values():
            # 遍历当前文档的**去重后**的词
            for word in set(doc):
                # 统计包含该词的文档数量，不存在则默认为0，再加1
                idf[word] = idf.get(word, 0) + 1
        # 遍历每个词及其文档频率，计算最终IDF值
        for word, freq in idf.items():
            # 标准BM25的IDF计算公式：log((总文档数-包含该词的文档数+0.5)/(包含该词的文档数+0.5))
            idf[word] = math.log((self.Numdocs - freq + 0.5) / (freq + 0.5))
        # 返回所有词的IDF值字典
        return idf

    # 计算TF（词频）：统计每个文档中每个词出现的次数
    def calculate_tf(self):
        # 初始化空字典，存储每个文档的词频
        tf = {}
        # 遍历每个文档ID和文档内容
        for id, doc in self.docs.items():
            # 临时字典，存储当前文档的词频
            temp = {}
            # 遍历当前文档的每个词
            for word in doc:
                # 统计词频，不存在则默认为0，再加1
                temp[word] = temp.get(word, 0) + 1
            # 将当前文档的词频存入总TF字典
            tf[id] = temp
        # 返回所有文档的词频字典
        return tf

    # 计算单个文档与查询的BM25相关性得分
    def get_score(self, index, query):
        # 初始化总得分为0
        score = 0.0
        # 获取当前文档的长度
        doclen = len(self.docs[index])
        # 统计查询中每个词的出现次数
        qf = Counter(query)
        # 遍历查询中的每一个词
        for q in query:
            # 如果当前词不在目标文档中，跳过，不贡献分数
            if q not in self.tf[index]:
                continue
            # BM25核心打分公式，累加每个查询词的贡献得分
            score += self.idf[q] * (self.tf[index][q] * (self.k1 + 1) / (
                    self.tf[index][q] + self.k1 * (1 - self.b + self.b * doclen / self.avg_doclen))) * (
                             qf[q] * (self.k2 + 1) / (qf[q] + self.k2))
        # 返回当前文档与查询的最终相关性得分
        return score

    # 对外查询接口：输入查询，返回Top-K相关的文档ID列表
    def query(self, query):
        # 初始化空列表，存储（文档ID，得分）元组
        score_list = []
        # 遍历所有文档ID
        for index in self.docs.keys():
            # 计算当前文档与查询的得分，并添加到列表
            score_list.append((index, self.get_score(index, query)))
        # 按得分**降序**排序（负号表示从高到低）
        score_list.sort(key=lambda x: (-x[1]))

        # 提取排序后前Top-K个文档的ID，返回结果列表
        return [item[0] for item in score_list[:self.topk]]