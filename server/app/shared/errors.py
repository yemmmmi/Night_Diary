"""Unified application errors for the service layer.

Route handlers (Phase C-2) map these to HTTP responses via ``http_status``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class AppError(Exception):
    """Base error with an HTTP status hint for the API layer."""

    message: str
    http_status: int = 400

    def __str__(self) -> str:
        return self.message


class ValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, http_status=422)


class DiaryNotFoundError(AppError):
    def __init__(self, *, diary_id: int) -> None:
        super().__init__(message=f"日记 {diary_id} 不存在", http_status=404)
        self.diary_id = diary_id


class DiaryAlreadyExistsError(AppError):
    def __init__(self, message: str = "该日记已有分析记录") -> None:
        super().__init__(message=message, http_status=409)


class AnalysisNotFoundError(AppError):
    def __init__(self, *, diary_id: int | None = None, analysis_id: int | None = None) -> None:
        if diary_id is not None:
            message = f"日记 {diary_id} 尚无分析记录"
        elif analysis_id is not None:
            message = f"分析记录 {analysis_id} 不存在"
        else:
            message = "分析记录不存在"
        super().__init__(message=message, http_status=404)
        self.diary_id = diary_id
        self.analysis_id = analysis_id


class AnalysisUnchangedError(AppError):
    def __init__(self) -> None:
        super().__init__(message="日记内容未变化，无需重新分析", http_status=409)


class TagNotFoundError(AppError):
    def __init__(self, *, tag_id: int) -> None:
        super().__init__(message=f"标签 {tag_id} 不存在", http_status=404)
        self.tag_id = tag_id


class TagConflictError(AppError):
    def __init__(self, message: str = "标签名已存在") -> None:
        super().__init__(message=message, http_status=409)


class ModelProviderNotFoundError(AppError):
    def __init__(self, *, model_id: int) -> None:
        super().__init__(message=f"模型配置 {model_id} 不存在", http_status=404)
        self.model_id = model_id


class AIServiceUnavailableError(AppError):
    def __init__(self, message: str = "AI 服务未配置或不可用") -> None:
        super().__init__(message=message, http_status=503)
