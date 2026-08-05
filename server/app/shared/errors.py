"""服务层统一的应用错误。

路由处理器（Phase C-2）通过 ``http_status`` 将这些错误映射为 HTTP 响应。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class AppError(Exception):
    """带有 HTTP 状态提示的基础错误，供 API 层使用。"""

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


class BootstrapNotReadyError(AppError):
    def __init__(self) -> None:
        super().__init__(message="AI 引擎仍在初始化，请稍候", http_status=503)


class WeeklyReportNotFoundError(AppError):
    def __init__(self, *, report_id: int | None = None) -> None:
        message = f"周记 {report_id} 不存在" if report_id is not None else "暂无周记记录"
        super().__init__(message=message, http_status=404)
        self.report_id = report_id


class WeeklyReportExistsError(AppError):
    def __init__(self, message: str = "本周已生成周记") -> None:
        super().__init__(message=message, http_status=409)


class WeeklyReportEmptyError(AppError):
    def __init__(self, message: str = "本周还没有日记或记忆卡片，无法生成周记") -> None:
        super().__init__(message=message, http_status=422)


class ConversationNotFoundError(AppError):
    def __init__(self, *, conversation_id: str | None = None) -> None:
        message = f"会话 {conversation_id} 不存在" if conversation_id else "会话不存在"
        super().__init__(message=message, http_status=404)
        self.conversation_id = conversation_id


class NotFoundError(AppError):
    """由 (resource_type, resource_id) 标识的资源的通用 404 错误。"""

    def __init__(self, *, resource: str, resource_id: str | int) -> None:
        super().__init__(message=f"{resource} {resource_id} 不存在", http_status=404)
        self.resource = resource
        self.resource_id = resource_id


class UnauthorizedError(AppError):
    """认证缺失或无效时抛出（HTTP 401）。"""

    def __init__(self, message: str = "未授权，请登录") -> None:
        super().__init__(message=message, http_status=401)


class ForbiddenError(AppError):
    """用户对资源缺少权限时抛出（HTTP 403）。"""

    def __init__(self, message: str = "无权访问此资源") -> None:
        super().__init__(message=message, http_status=403)


class EmailAlreadyExistsError(AppError):
    """注册已被占用的邮箱时抛出（HTTP 409）。"""

    def __init__(self, email: str = "") -> None:
        msg = f"邮箱 {email} 已注册" if email else "邮箱已注册"
        super().__init__(message=msg, http_status=409)
