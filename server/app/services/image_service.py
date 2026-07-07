"""Image processing service — VLM-first with OCR graceful degradation.

Both business scenarios (diary analysis, night-talk chat) share this service.
Routing is by **image content type** (photo / screenshot / document), not by
scenario, because either scenario can receive either kind of image.

Processing flow:
    1. Try VLM (user's vision-capable model) — single call produces both a
       semantic description and extracted text, so we don't need a separate
       OCR engine for the common case.
    2. On VLM failure (model doesn't support images / unavailable), fall back
       to PaddleOCR (optional dependency) for text extraction only.
    3. If PaddleOCR is not installed either, return ``processing_path="skipped"``
       with a notice — never blocks the diary/chat main flow.

This mirrors the project's existing graceful-degradation pattern for Redis /
Neo4j (see ``redis_client.is_redis_available``, ``task_queue`` threading
fallback).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select

from app.infrastructure.models.image_asset import ImageAssetRow
from app.shared.llm import LLMPrompt, VisionCapableLLMClient, build_image_block, message_text

logger = logging.getLogger(__name__)

ContentType = Literal["photo", "screenshot", "document", "unknown"]
ProcessingPath = Literal["vlm", "ocr_fallback", "skipped"]

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

# Per-content-type VLM prompts. A single VLM call yields description + text +
# content_type, collapsing the "multimodal semantics" + "OCR" paths into one.
_VLM_PROMPTS: dict[str, str] = {
    "photo": (
        "请分析这张照片。以 JSON 返回（不要 markdown 代码块）：\n"
        '{"description": "场景/氛围/可能反映的情绪状态(中文,120字内)", '
        '"text": "画面中可见的文字(无则空字符串)", '
        '"content_type": "photo|screenshot|document|unknown"}'
    ),
    "screenshot": (
        "请提取这张截图中的所有文字并以纯文本保留版面结构。以 JSON 返回（不要 markdown 代码块）：\n"
        '{"description": "对视觉元素的简要描述(图表/排版/无则空)", '
        '"text": "图中所有文字(保留换行)", '
        '"content_type": "photo|screenshot|document|unknown"}'
    ),
    "document": (
        "请提取这份文档图片中的所有文字并以 Markdown 格式输出，保留标题/表格/列表结构。"
        "以 JSON 返回（不要 markdown 代码块）：\n"
        '{"description": "文档类型与视觉布局简述", '
        '"text": "Markdown 格式的全文", '
        '"content_type": "photo|screenshot|document|unknown"}'
    ),
    "unknown": (
        "请分析这张图片。以 JSON 返回（不要 markdown 代码块）：\n"
        '{"description": "图片内容/场景/情绪的中文描述(120字内)", '
        '"text": "图中可见的文字(无则空字符串)", '
        '"content_type": "photo|screenshot|document|unknown"}'
    ),
}


@dataclass
class ProcessedImage:
    """Result of processing one image."""

    semantic_description: str
    extracted_text: str
    content_type: ContentType
    processing_path: ProcessingPath
    model_used: str = ""
    token_cost: int = 0
    error: str | None = field(default=None, repr=False)


def classify_content_type(
    *, hint: str | None = None, mime_type: str = "", filename: str = ""
) -> ContentType:
    """Lightweight content-type guesser.

    Priority: explicit ``hint`` → filename heuristic → ``unknown``. The VLM
    refines this on its first call (it returns a ``content_type`` field too).
    """
    if hint in _VLM_PROMPTS:
        return hint  # type: ignore[return-value]
    name = (filename or "").lower()
    if any(k in name for k in ("screenshot", "截图", "screen", "截图")):
        return "screenshot"
    if any(k in name for k in ("doc", "document", "文档", "pdf", "scan", "扫描")):
        return "document"
    if mime_type.startswith("image/"):
        return "photo"
    return "unknown"


class ImageProcessingService:
    """Process uploaded images via VLM, falling back to OCR.

    Stateless aside from the injected ``llm_factory``; safe to instantiate
    per-request or reuse.
    """

    def __init__(self, llm_factory: Any) -> None:
        self._llm_factory = llm_factory

    async def process(
        self,
        image_bytes: bytes,
        mime_type: str,
        *,
        hint: str | None = None,
        filename: str = "",
        max_completion_tokens: int = 1024,
    ) -> ProcessedImage:
        """Process one image: VLM first, OCR fallback, skipped last resort."""
        content_type = classify_content_type(hint=hint, mime_type=mime_type, filename=filename)
        try:
            return await self._process_via_vlm(
                image_bytes, mime_type, content_type, max_completion_tokens
            )
        except Exception as exc:
            logger.warning("VLM image processing failed, trying OCR fallback: %s", exc)
            return self._process_via_ocr(image_bytes, content_type, vlm_error=str(exc))

    async def _process_via_vlm(
        self,
        image_bytes: bytes,
        mime_type: str,
        content_type: ContentType,
        max_completion_tokens: int,
    ) -> ProcessedImage:
        client = self._create_vision_client(max_completion_tokens)
        prompt_text = _VLM_PROMPTS.get(content_type, _VLM_PROMPTS["unknown"])
        block = build_image_block(image_bytes, mime_type, detail="high")
        prompt: LLMPrompt = [
            {"type": "text", "text": prompt_text},
            block,  # type: ignore[list-item]
        ]
        response = await client.ainvoke_with_images(prompt)
        text = message_text(response)
        return _parse_vlm_json(text, content_type, model_used=self._model_name())

    def _create_vision_client(self, max_completion_tokens: int) -> VisionCapableLLMClient:
        """Build a vision client; raises if AI service is not configured.

        Callers wrap this in try/except to trigger OCR fallback — vision
        capability is detected by first-call probing, not a model-name table.
        """
        from app.shared.errors import AIServiceUnavailableError

        try:
            return self._llm_factory.create_vision_client(
                max_completion_tokens=max_completion_tokens
            )
        except AIServiceUnavailableError:
            raise
        except Exception as exc:
            raise RuntimeError(f"vision client unavailable: {exc}") from exc

    def _model_name(self) -> str:
        return getattr(self._llm_factory._settings, "llm_model", "")  # noqa: SLF001

    def _process_via_ocr(
        self, image_bytes: bytes, content_type: ContentType, *, vlm_error: str = ""
    ) -> ProcessedImage:
        """OCR fallback — lazy PaddleOCR import, mirrors Neo4j/Redis pattern."""
        try:  # pragma: no cover — exercised only when paddleocr is installed
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]
        except ImportError:
            logger.info("PaddleOCR not installed; image skipped")
            return ProcessedImage(
                semantic_description="（图像处理能力未启用：模型不支持视觉且未安装 OCR 组件）",
                extracted_text="",
                content_type=content_type,
                processing_path="skipped",
                error=vlm_error or "paddleocr not installed",
            )

        try:  # pragma: no cover
            import io

            from PIL import Image  # type: ignore[import-not-found]

            ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
            result = ocr.ocr(io.BytesIO(image_bytes), cls=True)
            lines: list[str] = []
            for region in result or []:
                for line in region or []:
                    if line and len(line) >= 2:
                        lines.append(str(line[1][0]))
            return ProcessedImage(
                semantic_description="",
                extracted_text="\n".join(lines),
                content_type=content_type,
                processing_path="ocr_fallback",
                model_used="paddleocr",
                error=vlm_error or None,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("PaddleOCR processing failed: %s", exc)
            return ProcessedImage(
                semantic_description="",
                extracted_text="",
                content_type=content_type,
                processing_path="skipped",
                error=f"ocr failed: {exc}",
            )

    async def process_asset(self, session: Any, asset_id: int, user_id: str) -> ProcessedImage:
        """Load an ``ImageAssetRow`` from DB, process it, and write results back."""
        row = session.scalar(
            select(ImageAssetRow).where(
                ImageAssetRow.id == asset_id, ImageAssetRow.user_id == user_id
            )
        )
        if row is None:
            return ProcessedImage(
                semantic_description="",
                extracted_text="",
                content_type="unknown",
                processing_path="skipped",
                error="asset not found",
            )

        image_bytes = _read_asset_file(row, user_id)
        if image_bytes is None:
            row.processing_path = "skipped"
            row.semantic_description = "（图像文件读取失败）"
            row.processed_at = datetime.utcnow()
            session.commit()
            return ProcessedImage(
                semantic_description="（图像文件读取失败）",
                extracted_text="",
                content_type="unknown",
                processing_path="skipped",
                error="file read failed",
            )

        result = await self.process(
            image_bytes,
            row.mime_type,
            hint=None,
            filename=row.original_filename,
        )
        row.semantic_description = result.semantic_description
        row.extracted_text = result.extracted_text
        row.content_type = result.content_type
        row.processing_path = result.processing_path
        row.model_used = result.model_used
        row.processed_at = datetime.utcnow()
        session.commit()
        return result


def _read_asset_file(row: ImageAssetRow, user_id: str) -> bytes | None:
    """Read the stored image bytes from disk (per-user subdirectory)."""
    from pathlib import Path

    from app.config import get_settings

    cfg = get_settings()
    path = Path(cfg.uploads_dir) / (user_id or "_shared") / row.stored_filename
    try:
        return path.read_bytes()
    except Exception as exc:
        logger.warning("Failed to read image asset %s: %s", path, exc)
        return None


def _parse_vlm_json(
    text: str, fallback_type: ContentType, *, model_used: str = ""
) -> ProcessedImage:
    """Parse the VLM's JSON response; degrade gracefully on parse failure."""
    cleaned = text.strip()
    # Strip accidental markdown fences.
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1] if cleaned.count("```") >= 2 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
        return ProcessedImage(
            semantic_description=str(data.get("description", "")).strip(),
            extracted_text=str(data.get("text", "")).strip(),
            content_type=_coerce_type(data.get("content_type"), fallback_type),
            processing_path="vlm",
            model_used=model_used,
        )
    except (json.JSONDecodeError, AttributeError):
        # VLM didn't return valid JSON — use the raw text as description.
        return ProcessedImage(
            semantic_description=cleaned[:500] or "（图像无法解析）",
            extracted_text="",
            content_type=fallback_type,
            processing_path="vlm",
            model_used=model_used,
        )


def _coerce_type(value: Any, fallback: ContentType) -> ContentType:
    if value in ("photo", "screenshot", "document", "unknown"):
        return value  # type: ignore[return-value]
    return fallback


def _process_asset_sync(
    session_factory: Any,
    llm_factory: Any,
    user_id: str,
    asset_id: int,
) -> None:
    """Task-queue entry point: process one asset in a background thread.

    Best-effort: never raises (matches ``entity_extractor._run_extraction_sync``
    and the ``task_queue._run_safe`` contract).
    """
    try:
        service = ImageProcessingService(llm_factory)
        with session_factory() as session:
            asyncio.run(service.process_asset(session, asset_id, user_id))
    except Exception as exc:
        logger.warning("Image asset %s processing failed (best-effort): %s", asset_id, exc)


def schedule_image_processing(
    container: Any,
    *,
    user_id: str,
    asset_id: int,
) -> None:
    """Fire-and-forget: enqueue image processing. Never blocks, never raises."""
    from app.infrastructure.task_queue import enqueue_task

    session_factory = getattr(container, "session_factory", None)
    llm_factory = getattr(container, "llm_factory", None)
    if session_factory is None or llm_factory is None:
        logger.warning("Cannot schedule image processing: container missing deps")
        return
    enqueue_task(_process_asset_sync, session_factory, llm_factory, user_id, asset_id)


def build_image_context(
    db: Any,
    asset_ids: list[int],
    *,
    user_id: str,
) -> str:
    """Resolve attached image assets into a text context string for the LLM.

    Loads each ``ImageAssetRow`` (user-scoped) and concatenates its
    ``semantic_description`` + ``extracted_text``. Pending assets (still being
    processed) are noted as such so the model knows the image exists. Returns
    an empty string when there are no usable assets.
    """
    if not asset_ids:
        return ""
    rows = (
        db.execute(
            select(ImageAssetRow).where(
                ImageAssetRow.id.in_(asset_ids), ImageAssetRow.user_id == user_id
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return ""
    parts: list[str] = []
    # Preserve the caller's ordering.
    row_by_id = {r.id: r for r in rows}
    for idx, aid in enumerate(asset_ids, 1):
        row = row_by_id.get(aid)
        if row is None:
            continue
        desc = (row.semantic_description or "").strip()
        text = (row.extracted_text or "").strip()
        if row.processing_path == "pending":
            parts.append(f"[附图{idx}: 处理中]")
            continue
        chunks = [f"[附图{idx}"]
        if desc:
            chunks.append(f"图像描述: {desc}")
        if text:
            chunks.append(f"图中文字: {text}")
        if not desc and not text:
            chunks.append("图像内容: （无可用信息）")
        parts.append("; ".join(chunks) + "]")
    return "\n".join(parts)


__all__ = [
    "ContentType",
    "ImageProcessingService",
    "ProcessedImage",
    "ProcessingPath",
    "build_image_context",
    "classify_content_type",
    "schedule_image_processing",
]
