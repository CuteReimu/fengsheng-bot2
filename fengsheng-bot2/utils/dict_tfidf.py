"""基于 TF-IDF 的文本相似度计算"""
import math
import re

import jieba

from . import db

_KEY_TF_PREFIX = "dict:tf:"
_KEY_DF_PREFIX = "dict:df:"
_KEY_N = "dict:n"

_PUNCT_RE = re.compile(r"^[\s\W]+$")


def _cut_words(text: str) -> list[str]:
    """对文本进行分词，过滤掉纯标点/空白词"""
    raw = jieba.cut(text, cut_all=False)
    return [w for w in raw if not _PUNCT_RE.match(w)]


def add_into_dict(text: str) -> None:
    """当收到用户文字聊天时调用，统计词频用于 TF-IDF"""
    words = _cut_words(text)
    if not words:
        return
    local_count: dict[str, int] = {}
    for w in words:
        local_count[w] = local_count.get(w, 0) + 1

    n_str, ok = db.get(_KEY_N)
    n = int(n_str) if ok else 0
    db.set_value(_KEY_N, str(n + 1))

    for w, cnt in local_count.items():
        # 更新 tf（全局词频）
        tf_key = _KEY_TF_PREFIX + w
        tf_str, ok = db.get(tf_key)
        tf = int(tf_str) if ok else 0
        db.set_value(tf_key, str(tf + cnt))

        # 更新 df（文档频率），每个词每篇文档只计一次
        df_key = _KEY_DF_PREFIX + w
        df_str, ok = db.get(df_key)
        df_val = int(df_str) if ok else 0
        db.set_value(df_key, str(df_val + 1))


def _get_word_weight(word: str, doc_word_count: dict[str, int], n: int) -> float:
    """获取一个词的 TF-IDF 权重: W = tf * log(n / df)"""
    tf = doc_word_count.get(word, 0)
    if tf == 0:
        return 0.0
    df_str, ok = db.get(_KEY_DF_PREFIX + word)
    df = float(int(df_str)) if ok else 0.0
    return tf * math.log(max(n, 1) / max(df, 0.1))


def get_text_relativity(text1: str, text2: str) -> float:
    """获取两个文本的余弦相似度"""
    words1 = _cut_words(text1)
    words2 = _cut_words(text2)
    if not words1 or not words2:
        return 0.0

    count1: dict[str, int] = {}
    for w in words1:
        count1[w] = count1.get(w, 0) + 1
    count2: dict[str, int] = {}
    for w in words2:
        count2[w] = count2.get(w, 0) + 1

    n_str, ok = db.get(_KEY_N)
    n = int(n_str) if ok else 1
    if n == 0:
        n = 1

    vocab = set(count1.keys()) | set(count2.keys())
    dot = norm1 = norm2 = 0.0
    for w in vocab:
        w1 = _get_word_weight(w, count1, n)
        w2 = _get_word_weight(w, count2, n)
        dot += w1 * w2
        norm1 += w1 * w1
        norm2 += w2 * w2

    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (math.sqrt(norm1) * math.sqrt(norm2))


def get_familiar_value(m: dict[str, str], key: str) -> str:
    """从词条字典中模糊查找最匹配的值"""
    if key in m:
        return m[key]
    cache: list[tuple[str, float]] = []
    for k in m:
        v = get_text_relativity(k, key)
        if v >= 0.65:
            cache.append((k, v))
    cache.sort(key=lambda x: x[1], reverse=True)
    if (
        (len(cache) > 0 and cache[0][1] >= 0.9)
        or (len(cache) > 1 and cache[1][1] >= 0.8)
        or len(cache) > 2
    ):
        return m[cache[0][0]]
    return ""
