"""导出 reranker 训练对（query, passage, label）。

从 SQLite 导出两类数据：
1. 日记内部正负样本：同一篇日记的 chunk 互为正样本（query=首句/标题），
   跨日记的 chunk 互为负样本。label ∈ {0, 1}。
2.（可选）FeedbackRow 弱监督：用户点赞的回复所基于的检索片段标 1，
   踩的标 0。需要 analysis_id 关联链路完整。

用法：
    python -m scripts.finetune.export_reranker_pairs --db path/to/night_diary.db --out data.jsonl
    python -m scripts.finetune.export_reranker_pairs --db path/to/night_diary.db --out data.jsonl --with-feedback --neg-ratio 4
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger("export_reranker_pairs")

# 复用项目的中文分块逻辑，保证训练数据与索引时一致
_CN_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "：", "，", ".", "!", "?", ":", ",", " ", ""]


def split_chunks(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    """简化版中文分块，与项目 ChunkSplitter 默认参数对齐。"""
    if not text or len(text.strip()) < 20:
        return []
    if len(text) < chunk_size:
        return [text.strip()]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # 尝试在分隔符处断句
        if end < len(text):
            best_sep = -1
            for sep in _CN_SEPARATORS:
                idx = text.rfind(sep, start, end)
                if idx > best_sep:
                    best_sep = idx + len(sep)
            if best_sep > start + 50:  # 确保块不会太小
                end = best_sep
        chunk = text[start:end].strip()
        if len(chunk) >= 50:
            chunks.append(chunk)
        start = end - overlap if end - overlap > start else end
    return chunks


def make_query(content: str) -> str:
    """从日记正文生成查询语句：取首句或前 80 字。

    真实场景中，query 来自 QueryUnderstander 改写后的检索词，
    但训练阶段用首句近似即可——reranker 学的是 (query, passage) 语义相关性，
    而非 query 生成质量。
    """
    if not content:
        return ""
    # 取第一个句号前的内容，否则取前 80 字
    for sep in ["。", "！", "？", "\n"]:
        idx = content.find(sep)
        if 10 < idx < 120:
            return content[: idx + 1].strip()
    return content[:80].strip()


def export_diary_pairs(
    conn: sqlite3.Connection,
    *,
    neg_ratio: int = 4,
    user_id: str | None = None,
) -> list[dict]:
    """从 diary_entries 导出正负样本对。

    正样本：同篇日记的 (首句query, 任意chunk) → label=1
    负样本：跨日记的 (query, 其他日记chunk) → label=0
    """
    cur = conn.cursor()
    if user_id:
        cur.execute(
            "SELECT id, content FROM diary_entries WHERE content IS NOT NULL AND LENGTH(content) > 50 AND user_id = ?",
            (user_id,),
        )
    else:
        cur.execute(
            "SELECT id, content FROM diary_entries WHERE content IS NOT NULL AND LENGTH(content) > 50"
        )

    diaries = cur.fetchall()
    logger.info("读取到 %d 篇日记", len(diaries))

    if len(diaries) < 2:
        logger.warning("日记数量不足 2 篇，无法生成负样本")
        return []

    # 预处理：每篇日记生成 query + chunks
    diary_data = []
    for diary_id, content in diaries:
        query = make_query(content)
        chunks = split_chunks(content)
        if query and chunks:
            diary_data.append({"diary_id": diary_id, "query": query, "chunks": chunks})

    if len(diary_data) < 2:
        logger.warning("有效日记（含 chunk）不足 2 篇")
        return []

    pairs: list[dict] = []

    # 正样本：同篇日记
    for d in diary_data:
        for chunk in d["chunks"]:
            pairs.append({"query": d["query"], "passage": chunk, "label": 1})

    # 负样本：跨日记采样
    pos_count = len(pairs)
    neg_target = pos_count * neg_ratio
    all_chunks = [(d["diary_id"], chunk) for d in diary_data for chunk in d["chunks"]]
    random.seed(42)

    neg_added = 0
    attempts = 0
    max_attempts = neg_target * 10
    while neg_added < neg_target and attempts < max_attempts:
        # 随机选一篇日记的 query，配另一篇的 chunk
        q_diary = random.choice(diary_data)
        c_diary_id, chunk = random.choice(all_chunks)
        if c_diary_id != q_diary["diary_id"]:
            pairs.append({"query": q_diary["query"], "passage": chunk, "label": 0})
            neg_added += 1
        attempts += 1

    logger.info("生成正样本 %d 条，负样本 %d 条", pos_count, neg_added)
    return pairs


def export_feedback_pairs(
    conn: sqlite3.Connection,
    *,
    user_id: str | None = None,
) -> list[dict]:
    """从 FeedbackRow 导出弱监督对。

    链路：feedback(diary_id, feedback_type) → diary_entries(content)
    正样本：feedback_type='positive' 的日记 → (首句query, chunk) label=1
    负样本：feedback_type='negative' 的日记 → (首句query, chunk) label=0
    """
    cur = conn.cursor()
    if user_id:
        cur.execute(
            """
            SELECT f.feedback_type, d.content
            FROM feedback f
            JOIN diary_entries d ON f.diary_id = d.id
            WHERE f.diary_id IS NOT NULL
              AND f.feedback_type IN ('positive', 'negative')
              AND d.content IS NOT NULL
              AND LENGTH(d.content) > 50
              AND d.user_id = ?
            """,
            (user_id,),
        )
    else:
        cur.execute(
            """
            SELECT f.feedback_type, d.content
            FROM feedback f
            JOIN diary_entries d ON f.diary_id = d.id
            WHERE f.diary_id IS NOT NULL
              AND f.feedback_type IN ('positive', 'negative')
              AND d.content IS NOT NULL
              AND LENGTH(d.content) > 50
            """
        )

    rows = cur.fetchall()
    logger.info("读取到 %d 条反馈记录", len(rows))

    pairs: list[dict] = []
    for feedback_type, content in rows:
        query = make_query(content)
        chunks = split_chunks(content)
        if not query or not chunks:
            continue
        label = 1 if feedback_type == "positive" else 0
        for chunk in chunks[:3]:  # 每篇最多 3 个 chunk，避免正负失衡
            pairs.append({"query": query, "passage": chunk, "label": label})

    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 reranker 训练对")
    parser.add_argument(
        "--db",
        required=True,
        help="SQLite 数据库路径（如 %%APPDATA%%/night-diary/night_diary.db）",
    )
    parser.add_argument("--out", required=True, help="输出 JSONL 文件路径")
    parser.add_argument("--neg-ratio", type=int, default=4, help="负样本比例（默认 4:1）")
    parser.add_argument("--with-feedback", action="store_true", help="合并 FeedbackRow 弱监督数据")
    parser.add_argument("--user-id", default=None, help="仅导出指定用户的数据（多租户隔离）")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="训练集比例")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    db_path = Path(args.db)
    if not db_path.exists():
        logger.error("数据库文件不存在: %s", db_path)
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        pairs = export_diary_pairs(
            conn, neg_ratio=args.neg_ratio, user_id=args.user_id
        )
        if args.with_feedback:
            fb_pairs = export_feedback_pairs(conn, user_id=args.user_id)
            logger.info("反馈弱监督对 %d 条", len(fb_pairs))
            pairs.extend(fb_pairs)

        if not pairs:
            logger.error("未导出任何训练对，请检查数据库是否有日记数据")
            return 1

        # 打乱并按比例切分
        random.seed(42)
        random.shuffle(pairs)
        split = int(len(pairs) * args.train_ratio)
        train_pairs = pairs[:split]
        val_pairs = pairs[split:]

        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 训练集和验证集分别写入
        train_path = out_path.with_suffix(".train.jsonl")
        val_path = out_path.with_suffix(".val.jsonl")

        with open(train_path, "w", encoding="utf-8") as f:
            for p in train_pairs:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")

        with open(val_path, "w", encoding="utf-8") as f:
            for p in val_pairs:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")

        logger.info(
            "导出完成: 训练集 %d 条 → %s | 验证集 %d 条 → %s",
            len(train_pairs),
            train_path,
            len(val_pairs),
            val_path,
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
