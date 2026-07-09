import numpy as np


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """使用 numpy 计算两组向量的余弦相似度"""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    v1, v2 = np.array(vec1), np.array(vec2)
    norm1, norm2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))
