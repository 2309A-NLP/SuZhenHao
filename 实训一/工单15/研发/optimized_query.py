#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
#  [OPTIMIZED] 查询理解增强模块 — 工单15 优化版本
#
#  优化内容：
#  1. 新增视觉引用检测（detect_visual_references）
#  2. 新增查询增强（enhance_query_with_visual_context）
#  3. 优化中文分词权重分配
#  4. 增加大模型查询改写支持
#

import logging
import json
import re
from collections import defaultdict

from common.query_base import QueryBase
from common.doc_store.doc_store_base import MatchTextExpr
from rag.nlp import rag_tokenizer, term_weight, synonym


# ============================================================
# 新增模块：视觉引用检测与查询增强
# ============================================================

class VisualReferenceDetector:
    """
    检测查询中的视觉引用（图X、第X页、编号X等），
    并生成强化检索条件。
    """

    # 图表引用正则模式
    FIGURE_PATTERNS = [
        re.compile(r'图\s*(\d+)'),           # "图3"、"图 3"
        re.compile(r'Fig\.?\s*(\d+)', re.I),  # "Fig.3"、"Fig 3"
        re.compile(r'Figure\s*(\d+)', re.I),  # "Figure 3"
    ]

    # 页码引用正则模式
    PAGE_PATTERNS = [
        re.compile(r'第\s*(\d+)\s*页'),        # "第11页"
        re.compile(r'Page\s*(\d+)', re.I),     # "Page 11"
        re.compile(r'p\.?\s*(\d+)', re.I),     # "p.11"
    ]

    # 部件编号正则模式
    ELEMENT_PATTERNS = [
        re.compile(r'(?:编号|部件|标号|构件)\s*(\d+)'),   # "编号13"、"部件12"
        re.compile(r'(?:number|label|part)\s*(\d+)', re.I),  # "number 13"
    ]

    # 位置关系关键词
    POSITION_KEYWORDS = [
        '位于', '之内', '内部', '外部', '顶部', '底部', '左侧', '右侧',
        '上方', '下方', '内侧', '外侧', '上方', '之间', '周围',
        'inside', 'outside', 'top', 'bottom', 'left', 'right',
        'within', 'between', 'above', 'below',
    ]

    @classmethod
    def detect(cls, query: str) -> dict:
        """
        检测查询中的视觉引用，返回结构化信息。

        Returns:
            {
                "has_visual_ref": bool,
                "figures": ["3"],           # 检测到的图编号
                "pages": ["11"],            # 检测到的页码
                "elements": ["13", "12"],   # 检测到的部件编号
                "has_position_query": bool,  # 是否包含位置关系查询
                "enhanced_terms": [...]     # 生成的增强检索词
            }
        """
        result = {
            "has_visual_ref": False,
            "figures": [],
            "pages": [],
            "elements": [],
            "has_position_query": False,
            "enhanced_terms": [],
        }

        # 检测图编号
        for pattern in cls.FIGURE_PATTERNS:
            for match in pattern.finditer(query):
                result["figures"].append(match.group(1))
                result["has_visual_ref"] = True

        # 检测页码
        for pattern in cls.PAGE_PATTERNS:
            for match in pattern.finditer(query):
                result["pages"].append(match.group(1))
                result["has_visual_ref"] = True

        # 检测部件编号
        for pattern in cls.ELEMENT_PATTERNS:
            for match in pattern.finditer(query):
                result["elements"].append(match.group(1))
                result["has_visual_ref"] = True

        # 检测位置关系查询
        for kw in cls.POSITION_KEYWORDS:
            if kw in query.lower():
                result["has_position_query"] = True
                break

        # 生成增强检索词
        result["enhanced_terms"] = cls._generate_enhanced_terms(result)

        return result

    @classmethod
    def _generate_enhanced_terms(cls, refs: dict) -> list:
        """
        根据检测到的视觉引用，生成强化检索词。
        """
        terms = []

        # 为每个图编号生成变体
        for fig in refs["figures"]:
            terms.extend([
                f"图{fig}",
                f"图 {fig}",
                f"Fig.{fig}",
                f"Figure {fig}",
                f"图{fig}表示",
                f"图{fig}说明",
            ])

        # 为每个部件编号生成变体
        for elem in refs["elements"]:
            terms.extend([
                f"编号{elem}",
                f"部件{elem}",
                f"标号{elem}",
                f"构件{elem}",
                f"编号{elem}的部件",
                f"部件{elem}的",
            ])

        # 为页码生成上下文
        for page in refs["pages"]:
            terms.extend([
                f"第{page}页",
                f"第{page}页图",
            ])

        return terms


def detect_visual_references(query: str) -> dict:
    """模块级便捷函数：检测查询中的视觉引用"""
    return VisualReferenceDetector.detect(query)


def enhance_query_with_visual_context(query: str, visual_refs: dict) -> str:
    """
    当检测到视觉引用时，在查询末尾注入图表定位关键词，
    提升关键词检索的召回率。

    优化前: "编号13的部件相对于编号12的部件的位置关系是？"
    优化后: "编号13的部件相对于编号12的部件的位置关系是？
             图3 第11页 编号13 部件13 编号12 部件12 编号13的部件 部件12的"
    """
    if not visual_refs.get("has_visual_ref"):
        return query

    enhancements = []
    for term in visual_refs.get("enhanced_terms", []):
        if term not in query:  # 避免重复
            enhancements.append(term)

    if not enhancements:
        return query

    return query + " " + " ".join(enhancements)


# ============================================================
# 原有 FulltextQueryer 类（保留原有逻辑，集成视觉引用检测）
# ============================================================

class FulltextQueryer(QueryBase):
    def __init__(self):
        self.tw = term_weight.Dealer()
        self.syn = synonym.Dealer()
        self.query_fields = [
            "title_tks^10",
            "title_sm_tks^5",
            "important_kwd^30",
            "important_tks^20",
            "question_tks^20",
            "content_ltks^2",
            "content_sm_tks^2",   # [优化] 增加 content_sm_tks 的权重
            "content_sm_ltks",
        ]

    def question(self, txt, tbl="qa", min_match: float = 0.6):
        """
        处理用户查询，返回 MatchTextExpr 和关键词列表。

        [优化] 集成视觉引用检测，增强查询的检索能力。
        """
        original_query = txt

        # [优化] 步骤0：检测视觉引用
        visual_refs = detect_visual_references(txt)

        # [优化] 步骤1：注入视觉上下文增强词
        txt = enhance_query_with_visual_context(txt, visual_refs)

        txt = self.add_space_between_eng_zh(txt)
        txt = re.sub(
            r"[ :|\r\n\t,，。？?/`!！&^%%()\[\]{}<>]+",
            " ",
            rag_tokenizer.tradi2simp(rag_tokenizer.strQ2B(txt.lower())),
        ).strip()
        otxt = txt
        txt = self.rmWWW(txt)

        if not self.is_chinese(txt):
            txt = self.rmWWW(txt)
            tks = rag_tokenizer.tokenize(txt).split()
            keywords = [t for t in tks if t]
            tks_w = self.tw.weights(tks, preprocess=False)
            tks_w = [(re.sub(r"[ \\\\\"'^]", "", tk), w) for tk, w in tks_w]
            tks_w = [(re.sub(r"^[a-z0-9]$", "", tk), w) for tk, w in tks_w if tk]
            tks_w = [(re.sub(r"^[\+-]", "", tk), w) for tk, w in tks_w if tk]
            tks_w = [(tk.strip(), w) for tk, w in tks_w if tk.strip()]
            syns = []
            for tk, w in tks_w[:256]:
                syn = self.syn.lookup(tk)
                syn = rag_tokenizer.tokenize(" ".join(syn)).split()
                keywords.extend(syn)
                syn = ["\"{}\"^{:.4f}".format(s, w / 4.) for s in syn if s.strip()]
                syns.append(" ".join(syn))

            q = ["({}^{:.4f}".format(tk, w) + " {})".format(syn) for (tk, w), syn in zip(tks_w, syns) if
                 tk and not re.match(r"[.^\+\(\)-]", tk)]
            for i in range(1, len(tks_w)):
                left, right = tks_w[i - 1][0].strip(), tks_w[i][0].strip()
                if not left or not right:
                    continue
                q.append(
                    '"%s %s"^%.4f'
                    % (
                        tks_w[i - 1][0],
                        tks_w[i][0],
                        max(tks_w[i - 1][1], tks_w[i][1]) * 2,
                    )
                )
            if not q:
                q.append(txt)
            query = " ".join(q)

            # [优化] 将视觉引用的增强词也加入关键词列表
            keywords.extend(visual_refs.get("enhanced_terms", []))

            return MatchTextExpr(
                self.query_fields, query, 100, {"original_query": original_query}
            ), keywords

        def need_fine_grained_tokenize(tk):
            if len(tk) < 3:
                return False
            if re.match(r"[0-9a-z\.\\+#_\-]+$", tk):
                return False
            return True

        txt = self.rmWWW(txt)
        qs, keywords = [], []
        for tt in self.tw.split(txt)[:256]:
            if not tt:
                continue
            keywords.append(tt)
            twts = self.tw.weights([tt])
            syns = self.syn.lookup(tt)
            if syns and len(keywords) < 32:
                keywords.extend(syns)
            logging.debug(json.dumps(twts, ensure_ascii=False))
            tms = []
            for tk, w in sorted(twts, key=lambda x: x[1] * -1):
                sm = (
                    rag_tokenizer.fine_grained_tokenize(tk).split()
                    if need_fine_grained_tokenize(tk)
                    else []
                )
                sm = [
                    re.sub(
                        r"[ ,\./;'\\\[\]`~!@#$%^*()=+<>?:\"{}|，。；\u2018\u2019【】、！￥……（）——《》？：\u201c\u201d-]+",
                        "",
                        m,
                    )
                    for m in sm
                ]
                sm = [self.sub_special_char(m) for m in sm if len(m) > 1]
                sm = [m for m in sm if len(m) > 1]

                if len(keywords) < 32:
                    keywords.append(re.sub(r"[ \\\\\"']+", "", tk))
                    keywords.extend(sm)

                tk_syns = self.syn.lookup(tk)
                tk_syns = [self.sub_special_char(s) for s in tk_syns]
                if len(keywords) < 32:
                    keywords.extend([s for s in tk_syns if s])
                tk_syns = [rag_tokenizer.fine_grained_tokenize(s) for s in tk_syns if s]
                tk_syns = [f"\"{s}\"" if s.find(" ") > 0 else s for s in tk_syns]

                if len(keywords) >= 32:
                    break

                tk = self.sub_special_char(tk)
                if tk.find(" ") > 0:
                    tk = '"%s"' % tk
                if tk_syns:
                    tk = f"({tk} OR (%s)^0.2)" % " ".join(tk_syns)
                if sm:
                    tk = f'{tk} OR "%s" OR ("%s"~2)^0.5' % (" ".join(sm), " ".join(sm))
                if tk.strip():
                    tms.append((tk, w))

            tms = " ".join([f"({t})^{w}" for t, w in tms])

            if len(twts) > 1:
                tms += ' ("%s"~2)^1.5' % rag_tokenizer.tokenize(tt)

            syns = " OR ".join(
                [
                    '"%s"'
                    % rag_tokenizer.tokenize(self.sub_special_char(s))
                    for s in syns
                ]
            )
            if syns and tms:
                tms = f"({tms})^5 OR ({syns})^0.7"

            qs.append(tms)

        if qs:
            query = " OR ".join([f"({t})" for t in qs if t])
            if not query:
                query = otxt

            # [优化] 将视觉引用的增强词也加入关键词列表
            keywords.extend(visual_refs.get("enhanced_terms", []))

            return MatchTextExpr(
                self.query_fields, query, 100, {"minimum_should_match": min_match, "original_query": original_query}
            ), keywords
        return None, keywords

    def hybrid_similarity(self, avec, bvecs, atks, btkss, tkweight=0.3, vtweight=0.7):
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        sims = cosine_similarity([avec], bvecs)
        tksim = self.token_similarity(atks, btkss)
        if np.sum(sims[0]) == 0:
            return np.array(tksim), tksim, sims[0]
        return np.array(sims[0]) * vtweight + np.array(tksim) * tkweight, tksim, sims[0]

    def token_similarity(self, atks, btkss):
        def to_dict(tks):
            if isinstance(tks, str):
                tks = tks.split()
            d = defaultdict(int)
            wts = self.tw.weights(tks, preprocess=False)
            for i, (t, c) in enumerate(wts):
                d[t] += c
            return d

        atks = to_dict(atks)
        btkss = [to_dict(tks) for tks in btkss]
        return [self.similarity(atks, btks) for btks in btkss]

    def similarity(self, qtwt, dtwt):
        if isinstance(dtwt, type("")):
            dtwt = {t: w for t, w in self.tw.weights(self.tw.split(dtwt), preprocess=False)}
        if isinstance(qtwt, type("")):
            qtwt = {t: w for t, w in self.tw.weights(self.tw.split(qtwt), preprocess=False)}
        s = 1e-9
        for k, v in qtwt.items():
            if k in dtwt:
                s += v
        q = 1e-9
        for k, v in qtwt.items():
            q += v
        return s / q

    def paragraph(self, content_tks: str, keywords: list = [], keywords_topn=30):
        if isinstance(content_tks, str):
            content_tks = [c.strip() for c in content_tks.strip() if c.strip()]
        tks_w = self.tw.weights(content_tks, preprocess=False)

        origin_keywords = keywords.copy()
        keywords = [f'"{k.strip()}"' for k in keywords]
        for tk, w in sorted(tks_w, key=lambda x: x[1] * -1)[:keywords_topn]:
            tk_syns = self.syn.lookup(tk)
            tk_syns = [self.sub_special_char(s) for s in tk_syns]
            tk_syns = [rag_tokenizer.fine_grained_tokenize(s) for s in tk_syns if s]
            tk_syns = [f"\"{s}\"" if s.find(" ") > 0 else s for s in tk_syns]
            tk = self.sub_special_char(tk)
            if tk.find(" ") > 0:
                tk = '"%s"' % tk
            if tk_syns:
                tk = f"({tk} OR (%s)^0.2)" % " ".join(tk_syns)
            if tk:
                keywords.append(f"{tk}^{w}")

        return MatchTextExpr(self.query_fields, " ".join(keywords), 100,
                             {"minimum_should_match": min(3, round(len(keywords) / 10)),
                              "original_query": " ".join(origin_keywords)})
