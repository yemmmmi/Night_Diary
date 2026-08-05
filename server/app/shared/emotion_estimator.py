"""基于关键词的情绪估计，在整个 AI 管道中共享。

这是轻量级、无 LLM 情绪启发式的唯一真相来源。在 V1 中，相同的关键词评分被
复制粘贴到 ``empathy_agent`` 和 ``crisis_detector`` 两处（坏味 3：重复实现）；
现在它只存在于此处，并按需注入。

评估器是一个可配置的*实例*（没有模块级可变状态）。默认词表和权重复现了 V1
的行为，因此现有的危机检测阈值保持有效。需要不同灵敏度的调用方可以通过构造
函数传入自己的词表/权重。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 否定字符，会翻转其后正向关键词的极性。
# 例如 "不开心" → 负向，"没快乐" → 负向，"不是不开心" → 正向（双重否定）
_NEGATION_CHARS: str = "不没未别无非"

# 默认词表——V1 empathy_agent / crisis_detector 词表的并集，已去重。
# "崩溃"/"绝望" 被视为严重（不仅仅是负向），因此不会在两个层级间重复计数。
_DEFAULT_SEVERE_NEGATIVE: tuple[str, ...] = (
    "想死",
    "不想活",
    "自杀",
    "结束生命",
    "活着没意思",
    "我不想活了",
    "绝望",
    "崩溃",
    "撑不下去",
    "没有希望",
    "生不如死",
    "伤害自己",
    "自残",
    "割腕",
    "跳楼",
)

_DEFAULT_NEGATIVE: tuple[str, ...] = (
    "难过",
    "痛苦",
    "焦虑",
    "抑郁",
    "孤独",
    "害怕",
    "愤怒",
    "失望",
    "无助",
    "悲伤",
    "压抑",
    "烦躁",
    "失眠",
    "哭",
    "受不了",
    "太累了",
)

_DEFAULT_POSITIVE: tuple[str, ...] = (
    "开心",
    "快乐",
    "幸福",
    "感恩",
    "满足",
    "期待",
    "兴奋",
    "温暖",
    "感动",
    "自豪",
    "放松",
    "愉快",
)


@dataclass(frozen=True, slots=True)
class EmotionEstimate:
    """基于关键词的情绪估计结果。"""

    score: float
    """``[-1.0, 1.0]`` 范围内的极性；负向表示痛苦，正向表示良好状态。"""

    label: str
    """``crisis`` / ``negative`` / ``neutral`` / ``positive`` 之一。"""

    matched_severe: tuple[str, ...] = field(default_factory=tuple)
    matched_negative: tuple[str, ...] = field(default_factory=tuple)
    matched_positive: tuple[str, ...] = field(default_factory=tuple)


class EmotionEstimator:
    """使用关键词词表估计文本的情绪极性。

    该启发式刻意保持轻量：它在任何 LLM 调用之前运行，使管道可以短路到
    危机安全路径而无需消耗 token。它*不是*
    :class:`~app.domain.skills.sentiment_skill.SentimentSkill` 中 LLM 情感分析的
    替代品；它是为路由和危机检测提供输入的快速预筛。
    """

    def __init__(
        self,
        *,
        severe_keywords: tuple[str, ...] = _DEFAULT_SEVERE_NEGATIVE,
        negative_keywords: tuple[str, ...] = _DEFAULT_NEGATIVE,
        positive_keywords: tuple[str, ...] = _DEFAULT_POSITIVE,
        severe_weight: float = -0.4,
        negative_weight: float = -0.15,
        positive_weight: float = 0.15,
        crisis_threshold: float = -0.7,
        negative_threshold: float = -0.2,
        positive_threshold: float = 0.2,
    ) -> None:
        self._severe = severe_keywords
        self._negative = negative_keywords
        self._positive = positive_keywords
        self._severe_weight = severe_weight
        self._negative_weight = negative_weight
        self._positive_weight = positive_weight
        self._crisis_threshold = crisis_threshold
        self._negative_threshold = negative_threshold
        self._positive_threshold = positive_threshold

    @property
    def crisis_threshold(self) -> float:
        return self._crisis_threshold

    def estimate(self, text: str) -> EmotionEstimate:
        """返回完整的估计结果（分数 + 标签 + 匹配的关键词）。"""
        if not text:
            return EmotionEstimate(score=0.0, label="neutral")

        matched_severe = tuple(w for w in self._severe if w in text)
        matched_negative = tuple(w for w in self._negative if w in text)
        matched_positive: list[str] = []
        negated_positive: list[str] = []

        # 检测正向关键词之前的否定前缀。
        # 奇数个否定字符 → 极性翻转（正向 → 负向）。
        # 偶数个 → 双重否定恢复正向（例如 "不是不开心"）。
        for w in self._positive:
            start = 0
            while True:
                idx = text.find(w, start)
                if idx == -1:
                    break
                prefix = text[max(0, idx - 3) : idx]
                neg_count = sum(1 for c in prefix if c in _NEGATION_CHARS)
                if neg_count % 2 == 1:
                    negated_positive.append(w)
                else:
                    matched_positive.append(w)
                start = idx + len(w)

        matched_positive_t = tuple(matched_positive)
        negated_positive_t = tuple(negated_positive)

        raw = (
            len(matched_severe) * self._severe_weight
            + len(matched_negative) * self._negative_weight
            + len(matched_positive_t) * self._positive_weight
            # 被否定的正向词计为负向（权重与一般负向相同）。
            + len(negated_positive_t) * self._negative_weight
        )
        score = max(-1.0, min(1.0, raw))

        return EmotionEstimate(
            score=score,
            label=self.label_for(score),
            matched_severe=matched_severe,
            matched_negative=matched_negative,
            matched_positive=matched_positive_t,
        )

    def score(self, text: str) -> float:
        """仅返回 ``[-1.0, 1.0]`` 范围内的极性分数。"""
        return self.estimate(text).score

    def label_for(self, score: float) -> str:
        """将极性分数映射为离散的情绪标签。"""
        if score <= self._crisis_threshold:
            return "crisis"
        if score <= self._negative_threshold:
            return "negative"
        if score >= self._positive_threshold:
            return "positive"
        return "neutral"

    def has_severe_signal(self, text: str) -> bool:
        """文本是否包含任何严重（危机级别）关键词。"""
        return any(word in text for word in self._severe)

    def count_negative_signals(self, text: str) -> int:
        """统计文本中出现的不同一般负向关键词数量。"""
        return sum(1 for word in self._negative if word in text)


# 惰性创建的进程级默认评估器单例。评估器是无状态且轻量的，但共享一个
# 默认实例可以保持内存使用可预测，并提供单一注入点。``_INSTANCE`` 仅是
# 默认配置实例的缓存——它不持有词表/可变评分状态，需要自定义词表/权重的
# 调用方仍然直接构造（或注入）自己的 ``EmotionEstimator``。
_INSTANCE: EmotionEstimator | None = None


def get_emotion_estimator() -> EmotionEstimator:
    """返回共享的默认 :class:`EmotionEstimator` 单例。

    在首次调用时惰性构造默认配置的实例，此后复用。注入此访问器（或其结果），
    而不是在调用点直接调用 ``EmotionEstimator()``，这样替换默认实例就只有
    一个地方——例如用于测试或全局重新配置。
    """
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = EmotionEstimator()
    return _INSTANCE
