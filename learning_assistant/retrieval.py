import re
import math
from collections import Counter
from functools import lru_cache


def split_text(text: str, chunk_size: int = 700, overlap: int = 120) -> list[str]:
    """按字符窗口分段，并尽量在句末或换行处结束。"""
    if chunk_size <= 0 or not 0 <= overlap < chunk_size:
        raise ValueError("分段参数要求 0 <= overlap < chunk_size。")
    # 行首空白是Python语义的一部分，不折叠空格或制表符。
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not cleaned:
        return []

    chunks = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        if end < len(cleaned):
            search_from = start + chunk_size // 2
            break_positions = [
                cleaned.rfind(separator, search_from, end)
                for separator in ("\n", "。", "！", "？", "；", ". ")
            ]
            best_break = max(break_positions)
            if best_break > start:
                end = best_break + 1

        chunk = cleaned[start:end].strip("\n")
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return chunks

def build_course_chunks(pages: list[dict]) -> list[dict]:
    """把页面转为可检索片段，并继承文件名、页码和提取方式。"""
    chunks = []
    for page in pages:
        for part_number, text in enumerate(split_text(page["text"]), start=1):
            chunks.append(
                {
                    "chunk_id": len(chunks) + 1,
                    "document_id": page.get("document_id", page["file_name"]),
                    "file_name": page["file_name"],
                    "page_number": page["page_number"],
                    "part_number": part_number,
                    "text": text,
                    "extraction_method": page["extraction_method"],
                }
            )
    return chunks

def tokenize_for_search(text: str) -> list[str]:
    """同时保留 Python/英文词、数字、中文单字和中文双字词。"""
    lowered = text.lower()
    tokens = re.findall(r"[a-z_][a-z0-9_.]*|\d+(?:\.\d+)?", lowered)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", lowered)
    for run in chinese_runs:
        tokens.extend(run)
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tokens

@lru_cache(maxsize=4)
def _build_index(texts: tuple[str, ...]):
    documents = [tokenize_for_search(text) for text in texts]
    document_frequency = Counter()
    for document in documents:
        document_frequency.update(set(document))
    return documents, document_frequency, [Counter(doc) for doc in documents]


def search_course_chunks(
    query: str, chunks: list[dict], top_k: int = 5
) -> list[dict]:
    """使用 BM25 对课程片段排序，不依赖外部模型或网络。"""
    if not query.strip() or not chunks:
        return []

    documents, document_frequency, counters = _build_index(tuple(chunk["text"] for chunk in chunks))
    query_tokens = tokenize_for_search(query)
    if not query_tokens:
        return []

    document_count = len(documents)
    average_length = sum(map(len, documents)) / max(document_count, 1)
    k1, b = 1.5, 0.75
    ranked = []
    for chunk, document, frequencies in zip(chunks, documents, counters):
        score = 0.0
        for token in query_tokens:
            frequency = frequencies[token]
            if frequency == 0:
                continue
            doc_frequency = document_frequency[token]
            inverse_frequency = math.log(
                1 + (document_count - doc_frequency + 0.5) / (doc_frequency + 0.5)
            )
            denominator = frequency + k1 * (
                1 - b + b * len(document) / max(average_length, 1)
            )
            score += inverse_frequency * frequency * (k1 + 1) / denominator

        if query.lower() in chunk["text"].lower():
            score += 3.0
        if score > 0:
            ranked.append({**chunk, "score": score})

    return sorted(ranked, key=lambda item: item["score"], reverse=True)[:top_k]
