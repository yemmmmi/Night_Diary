#!/usr/bin/env python3
"""开发者模式数据链路测试数据生成脚本。

通过 httpx 同步调用运行中的 API 服务，为 5 个账号生成日记 / 对话 /
多轮对话测试数据，并在完成后验证记忆库状态。每条数据生成 POST 请求
附加 ``X-Trace-Id`` 和 ``X-Developer-Mode`` 请求头，触发后端
PipelineTrace 全链路追踪。

用法::

    python seed_dev_traces.py [--base-url URL] [--dry-run] [--user x] [--skip-memory-check]

示例::

    # 打印用例清单，不调用 API
    python seed_dev_traces.py --dry-run

    # 只生成用户 a 的数据
    python seed_dev_traces.py --user a

    # 指定 API 地址并跳过记忆验证
    python seed_dev_traces.py --base-url http://192.168.1.100:8000 --skip-memory-check
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx

# ── 常量 ──────────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_PASSWORD = "123456"
REQUEST_TIMEOUT = 300.0  # LLM 调用可能较慢，给 5 分钟

# 日期映射
DATE_A = {
    "Day1": "2026-07-04",
    "Day2": "2026-07-05",
    "Day3": "2026-07-06",
    "Day4": "2026-07-07",
}
DATE_C = {"Day1": "2026-07-06", "Day2": "2026-07-07"}
DATE_D = {"Day1": "2026-07-07"}
DATE_E = {"Day1": "2026-07-07"}

# 测试账号
ACCOUNTS: list[dict[str, str]] = [
    {"key": "a", "email": "a@dev.test", "nickname": "Alice", "desc": "日记重度用户"},
    {"key": "b", "email": "b@dev.test", "nickname": "Bob", "desc": "对话重度用户"},
    {"key": "c", "email": "c@dev.test", "nickname": "Carol", "desc": "混合用户"},
    {"key": "d", "email": "d@dev.test", "nickname": "Dave", "desc": "边界/危机场景"},
    {"key": "e", "email": "e@dev.test", "nickname": "Eve", "desc": "轻度用户"},
]

# ── 日记测试用例 (24 条) ─────────────────────────────────────────────

DIARY_CASES: list[dict[str, Any]] = [
    # ── 用户 A (Alice) — 12 条，日期跨 4 天触发画像生成 ──
    {
        "user": "a", "id": "A-D1", "name": "极简记录",
        "date": DATE_A["Day1"], "content": "今天吃了火锅。", "preset": None,
    },
    {
        "user": "a", "id": "A-D2", "name": "日常三件事",
        "date": DATE_A["Day1"],
        "content": "今天吃了火锅，看了部电影，挺开心的一天。", "preset": None,
    },
    {
        "user": "a", "id": "A-D3", "name": "周末游记",
        "date": DATE_A["Day1"],
        "content": (
            "今天和朋友去公园散步，天气很好。中午吃了日料，下午逛了书店，"
            "买了一本小说。晚上回家做了顿饭，看了会电视就睡了。"
        ),
        "preset": None,
    },
    {
        "user": "a", "id": "A-D4", "name": "工作压力倾诉-Day1",
        "date": DATE_A["Day1"],
        "content": (
            "最近工作压力好大，每天加班到很晚，感觉快要撑不住了。"
            "老板总是给我安排做不完的任务，同事也不配合，真的很崩溃很累。"
        ),
        "preset": None,
    },
    {
        "user": "a", "id": "A-D5", "name": "工作压力-Day2",
        "date": DATE_A["Day2"],
        "content": (
            "今天又加班了，老板还是给一堆任务，同事不配合，好累好崩溃。"
            "工作压力太大了。"
        ),
        "preset": None,
    },
    {
        "user": "a", "id": "A-D6", "name": "和妈妈吵架-Day1",
        "date": DATE_A["Day1"],
        "content": (
            "上周和妈妈大吵了一架，当时说了很多气话。这几天一直很后悔，"
            "想起之前也发生过类似的事情，每次都是不欢而散。"
            "今天终于鼓起勇气给她打了电话，没想到她也在等我。"
            "我们聊了很久，把心里话都说开了。"
        ),
        "preset": None,
    },
    {
        "user": "a", "id": "A-D7", "name": "工作压力-Day3",
        "date": DATE_A["Day3"],
        "content": (
            "今天又被领导批评了，工作压力真的太大了。每天加班，"
            "感觉快撑不住了，好崩溃好累。"
        ),
        "preset": None,
    },
    {
        "user": "a", "id": "A-D8", "name": "和妈妈-Day2",
        "date": DATE_A["Day2"],
        "content": (
            "今天给妈妈打了电话，上次吵架的事还是放不下。"
            "之前也吵过，但每次都和好了。"
        ),
        "preset": None,
    },
    {
        "user": "a", "id": "A-D9", "name": "运动记录",
        "date": DATE_A["Day3"],
        "content": "今天跑了五公里，感觉状态不错。", "preset": None,
    },
    {
        "user": "a", "id": "A-D10", "name": "和妈妈-Day3",
        "date": DATE_A["Day3"],
        "content": (
            "今天又想起和妈妈的事，之前每次吵架都是这样，过了几天就好了。"
            "这次也想通了。"
        ),
        "preset": None,
    },
    {
        "user": "a", "id": "A-D11", "name": "风格预设-warm",
        "date": DATE_A["Day4"],
        "content": "今天终于把论文交了，如释重负。晚上和同学庆祝了一下，喝了两杯。",
        "preset": "warm",
    },
    {
        "user": "a", "id": "A-D12", "name": "风格预设-pragmatic",
        "date": DATE_A["Day4"],
        "content": "今天终于把论文交了，如释重负。晚上和同学庆祝了一下，喝了两杯。",
        "preset": "pragmatic",
    },
    # ── 用户 C (Carol) — 6 条，日期跨 2 天 ──
    {
        "user": "c", "id": "C-D1", "name": "短篇开心",
        "date": DATE_C["Day1"],
        "content": "今天天气很好，心情也不错，去公园晒了太阳。", "preset": None,
    },
    {
        "user": "c", "id": "C-D2", "name": "工作烦恼",
        "date": DATE_C["Day1"],
        "content": (
            "今天被领导批评了，心里很难受。觉得自己已经很努力了，"
            "但总是达不到要求。好累好崩溃。"
        ),
        "preset": None,
    },
    {
        "user": "c", "id": "C-D3", "name": "和朋友矛盾",
        "date": DATE_C["Day1"],
        "content": (
            "上周和朋友发生了矛盾，当时很生气说了一些过分的话。"
            "这几天一直在想这件事，之前我们也吵过架，但每次都和好了。"
            "这次不太一样，她一直没回我消息。我有点担心我们的友情是不是要结束了。"
        ),
        "preset": None,
    },
    {
        "user": "c", "id": "C-D4", "name": "读书感悟",
        "date": DATE_C["Day2"],
        "content": (
            "今天读完了那本书，作者对幸福的定义很有意思。"
            "他说幸福不是拥有更多，而是想要更少。"
            "这让我想起上次和老师聊过的话题，当时觉得很有道理，现在有了更深的理解。"
        ),
        "preset": None,
    },
    {
        "user": "c", "id": "C-D5", "name": "日常碎碎念",
        "date": DATE_C["Day2"],
        "content": (
            "今天买了杯咖啡，路上看到一只很可爱的猫。下午开了个长会，"
            "晚饭吃了麻辣烫。平凡但充实的一天。"
        ),
        "preset": None,
    },
    {
        "user": "c", "id": "C-D6", "name": "风格预设-calm",
        "date": DATE_C["Day2"],
        "content": "最近在学画画，虽然画得不好但很享受过程。今天画了一幅水彩小景。",
        "preset": "calm",
    },
    # ── 用户 D (Dave) — 4 条 ──
    {
        "user": "d", "id": "D-D1", "name": "轻度危机",
        "date": DATE_D["Day1"],
        "content": "今天感觉很绝望，什么都做不好，活着没什么意思。", "preset": None,
    },
    {
        "user": "d", "id": "D-D2", "name": "重度危机",
        "date": DATE_D["Day1"],
        "content": (
            "真的不想活了，感觉自己是个废物，想结束这一切。"
            "自残的念头一直挥之不去。"
        ),
        "preset": None,
    },
    {
        "user": "d", "id": "D-D3", "name": "超长日记",
        "date": DATE_D["Day1"],
        "content": (
            "最近一直在思考很多问题。上周和朋友聊天时，他说人应该学会放下过去。"
            "这让我想起上次和家人的矛盾，之前也发生过类似的事情，每次都很纠结。"
            "今天终于想通了，其实很多烦恼都是自己给自己设的限。"
            "回想起这段时间的经历，焦虑和抑郁的情绪一直困扰着我，失眠也成了家常便饭。"
            "好累好崩溃，感觉每天都在机械地重复。"
            "但是今天散步的时候，看着路边的花开了，突然觉得生活还是有很多美好的瞬间。"
            "也许我不需要把所有事情都想清楚，只需要过好每一天就够了。"
            "之前总是太执着于结果，反而忽略了过程中的风景。"
            "上次和老师聊过之后，他说的对，人生不是考试，没有标准答案。"
            "今天把这些写下来，感觉心里轻松了很多。希望明天的自己也能保持这份平静。"
        ),
        "preset": None,
    },
    {
        "user": "d", "id": "D-D4", "name": "单字日记",
        "date": DATE_D["Day1"],
        "content": "累。", "preset": None,
    },
    # ── 用户 E (Eve) — 2 条 ──
    {
        "user": "e", "id": "E-D1", "name": "简单日常",
        "date": DATE_E["Day1"],
        "content": "今天去超市买了点东西，做了顿晚饭。", "preset": None,
    },
    {
        "user": "e", "id": "E-D2", "name": "心情记录",
        "date": DATE_E["Day1"],
        "content": "今天心情不太好，有点焦虑，但说不上来为什么。", "preset": None,
    },
]

# ── 对话测试用例 (24 条) ─────────────────────────────────────────────

CHAT_CASES: list[dict[str, Any]] = [
    # ── 用户 B (Bob) — 12 条 ──
    {
        "user": "b", "id": "B-C1", "name": "早安闲聊",
        "content": "早安！今天天气真好。", "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "b", "id": "B-C2", "name": "晚安闲聊",
        "content": "晚安，今天过得很充实。", "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "b", "id": "B-C3", "name": "情绪宣泄-工作",
        "content": "今天被领导批评了，心里特别难受，感觉做什么都不对，好崩溃好累。",
        "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "b", "id": "B-C4", "name": "情绪宣泄-感情",
        "content": "和男朋友吵架了，心里好痛苦好绝望，不知道该怎么办才好。",
        "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "b", "id": "B-C5", "name": "回顾查询",
        "content": "我上次说的那个项目后来怎么样了？", "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "b", "id": "B-C6", "name": "回顾日记",
        "content": "上周我写的日记里提到了加班的事，后来怎样了？",
        "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "b", "id": "B-C7", "name": "建议寻求-失眠",
        "content": "最近总是失眠，不知道该怎么办，有什么好的建议吗？",
        "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "b", "id": "B-C8", "name": "建议寻求-人际",
        "content": "如何和同事相处？为什么总觉得融入不了团队？帮我分析一下。",
        "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "b", "id": "B-C9", "name": "实体查询-妈妈",
        "content": "我妈妈最近怎么样了？", "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "b", "id": "B-C10", "name": "实体查询-朋友",
        "content": "我朋友最近怎么了？好像不太开心。", "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "b", "id": "B-C11", "name": "多任务拆分",
        "content": "帮我查一下上周的日记然后分析一下情绪趋势。", "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "b", "id": "B-C12", "name": "多任务复杂",
        "content": "先帮我回顾上次的内容，接着总结一下最近的情绪，最后给我一些建议。",
        "diary_ids": [], "auto_retrieve": True,
    },
    # ── 用户 C (Carol) — 6 条 ──
    {
        "user": "c", "id": "C-C1", "name": "打招呼",
        "content": "你好呀，今天想和你聊聊天。", "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "c", "id": "C-C2", "name": "情绪倾诉",
        "content": "今天好累好崩溃，工作太多了做不完。", "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "c", "id": "C-C3", "name": "RAG查询",
        "content": "我上次写的日记里提到了和朋友的矛盾，后来怎么样了？",
        # diary_ids 引用 C-D3 创建后返回的 ID（运行时解析）
        "diary_ids": ["C-D3"], "auto_retrieve": True,
    },
    {
        "user": "c", "id": "C-C4", "name": "建议",
        "content": "最近压力大，如何缓解焦虑？有什么建议吗？", "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "c", "id": "C-C5", "name": "实体",
        "content": "我爸爸最近怎么样了？上次和他聊天感觉他不太开心。",
        "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "c", "id": "C-C6", "name": "auto_retrieve=False",
        "content": "我上次说的那件事，帮我回忆一下。", "diary_ids": [], "auto_retrieve": False,
    },
    # ── 用户 D (Dave) — 4 条 ──
    {
        "user": "d", "id": "D-C1", "name": "危机短路-轻度",
        "content": "感觉自己撑不下去了，不想活了。", "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "d", "id": "D-C2", "name": "危机短路-重度",
        "content": "我想自杀，活着没有意义，想结束这一切。", "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "d", "id": "D-C3", "name": "超长消息",
        "content": (
            "最近一直在想很多事情。工作上遇到了瓶颈，每天加班到很晚，"
            "感觉快要撑不住了。老板总是给我安排做不完的任务，同事也不配合，"
            "真的很崩溃很累。上次的绩效考核也不理想，感觉自己已经很努力了，"
            "但总是达不到要求。回家后也不开心，和家人的关系有些紧张。"
            "上周和妈妈大吵了一架，当时说了很多气话。这几天一直很后悔，"
            "想起之前也发生过类似的事情，每次都是不欢而散。"
            "焦虑和抑郁的情绪一直困扰着我，失眠也成了家常便饭。"
            "不知道该怎么办，感觉每天都在机械地重复。"
            "但是今天散步的时候，看着路边的花开了，突然觉得生活还是有很多美好的瞬间。"
            "也许我不需要把所有事情都想清楚，只需要过好每一天就够了。"
            "之前总是太执着于结果，反而忽略了过程中的风景。"
            "上次和老师聊过之后，他说的对，人生不是考试，没有标准答案。"
            "今天把这些写下来，感觉心里轻松了很多。希望明天的自己也能保持这份平静。"
            "最近在尝试冥想和运动，好像有一点点效果。失眠的情况也有所好转，"
            "虽然偶尔还是会翻来覆去。工作上的事情也在慢慢理清头绪，也许没有那么糟糕。"
            "和朋友聊了之后发现大家都有类似的困扰，不是只有我一个人在挣扎。"
            "这让我感觉好了一些。也许人就是这样，在跌跌撞撞中慢慢前行的吧。"
        ),
        "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "d", "id": "D-C4", "name": "单字消息",
        "content": "嗯。", "diary_ids": [], "auto_retrieve": True,
    },
    # ── 用户 E (Eve) — 2 条 ──
    {
        "user": "e", "id": "E-C1", "name": "简单问候",
        "content": "你好", "diary_ids": [], "auto_retrieve": True,
    },
    {
        "user": "e", "id": "E-C2", "name": "简单情绪",
        "content": "今天有点不开心", "diary_ids": [], "auto_retrieve": True,
    },
]

# ── 多轮对话用例 (3 组) ──────────────────────────────────────────────

MULTI_TURN_CASES: list[dict[str, Any]] = [
    {
        "user": "b", "id": "MT-1", "name": "多轮-工作压力",
        "messages": [
            "你好，今天想和你聊聊",
            "最近工作压力很大，感觉有点焦虑和崩溃",
            "我上次说过和同事的矛盾，后来我们和好了",
        ],
    },
    {
        "user": "b", "id": "MT-2", "name": "多轮-失眠",
        "messages": [
            "早安！",
            "最近总是失眠，怎么办才好",
            "上次你给的建议我试了，好像有点效果",
            "谢谢你，感觉好多了",
        ],
    },
    {
        "user": "c", "id": "MT-3", "name": "多轮-日记回顾",
        "messages": [
            "帮我查一下上周的日记然后总结一下心情",
            "我妈妈最近怎么样了？",
            "好的，谢谢你的建议",
        ],
    },
]


# ── 数据类 ────────────────────────────────────────────────────────────


@dataclass
class CaseResult:
    """单条用例的执行结果。"""

    case_id: str
    name: str
    trace_id: str
    status: str  # "ok" | "error"
    detail: str = ""

    def __str__(self) -> str:
        icon = "OK" if self.status == "ok" else "ERR"
        trace_short = self.trace_id[:12] if self.trace_id else "-"
        return f"  [{icon}] {self.case_id:<8} {self.name:<20} trace={trace_short}  {self.detail}"


@dataclass
class MemorySummary:
    """记忆验证摘要。"""

    episodic_count: int = 0
    sources: dict[str, int] = field(default_factory=dict)
    profile_built: bool = False
    recurring_topics: list[str] = field(default_factory=list)
    dominant_emotion: str = "N/A"

    def __str__(self) -> str:
        sources_str = ", ".join(f"{k}={v}" for k, v in sorted(self.sources.items()))
        topics_str = ", ".join(self.recurring_topics) if self.recurring_topics else "(空)"
        return (
            f"  episodic_count : {self.episodic_count}\n"
            f"  sources         : {sources_str or '(空)'}\n"
            f"  profile_built   : {self.profile_built}\n"
            f"  recurring_topics: {topics_str}\n"
            f"  dominant_emotion: {self.dominant_emotion}"
        )


# ── 核心类 ────────────────────────────────────────────────────────────


class DevTraceSeeder:
    """开发者模式测试数据种子器。

    使用 httpx 同步客户端调用 API，为每个账号生成日记 / 对话 / 多轮对话
    测试数据，每条 POST 请求附带 ``X-Trace-Id`` 和 ``X-Developer-Mode``
    请求头以触发后端全链路追踪。
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        dry_run: bool = False,
        user_filter: str | None = None,
        skip_memory_check: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self.user_filter = user_filter
        self.skip_memory_check = skip_memory_check
        self.client = httpx.Client(base_url=self.base_url, timeout=REQUEST_TIMEOUT)
        self.results: dict[str, list[CaseResult]] = defaultdict(list)
        # case_id → diary_id（用于 C-C3 引用 C-D3）
        self._diary_id_map: dict[str, int] = {}

    # ── 请求头辅助 ──

    @staticmethod
    def _trace_headers() -> dict[str, str]:
        """生成带唯一 trace_id 的开发者模式请求头。"""
        return {
            "X-Trace-Id": str(uuid4()),
            "X-Developer-Mode": "true",
        }

    @staticmethod
    def _auth_headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _data_headers(self, token: str) -> dict[str, str]:
        """数据生成 POST 请求头 = 认证 + trace。"""
        return {**self._auth_headers(token), **self._trace_headers()}

    # ── 认证 ──

    def ensure_user(self, email: str, password: str, nickname: str) -> str:
        """先尝试注册，失败则登录，返回 access_token。

        注册端点返回 ``UserResponse``（不含 token），因此无论注册成功
        与否都需要调用登录端点获取 JWT。
        """
        # 1. 尝试注册
        try:
            resp = self.client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": password, "nickname": nickname},
            )
            if resp.status_code == 201:
                print(f"  [register] {email} 注册成功")
            else:
                # 409 / 400 / 422 等都视为「已存在或验证问题」，继续登录
                print(
                    f"  [register] {email} 状态 {resp.status_code}，"
                    f"尝试登录"
                )
        except httpx.RequestError as exc:
            print(f"  [register] {email} 请求异常: {exc}")

        # 2. 登录获取 token（form-urlencoded）
        resp = self.client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": password},
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"登录失败 [{resp.status_code}]: {resp.text[:300]}"
            )
        token = resp.json()["access_token"]
        print(f"  [login] {email} 登录成功")
        return token

    # ── 日记 ──

    def seed_diary(self, token: str, case: dict[str, Any]) -> CaseResult:
        """创建日记 → 触发分析，返回结果。

        POST /api/v1/diary/entries 创建日记（带 trace 头）
        POST /api/v1/analysis/{diary_id} 触发分析（带 trace 头）
        """
        # ── 创建日记 ──
        diary_trace_id = str(uuid4())
        diary_headers = {
            **self._auth_headers(token),
            "X-Trace-Id": diary_trace_id,
            "X-Developer-Mode": "true",
        }
        try:
            resp = self.client.post(
                "/api/v1/diary/entries",
                json={"content": case["content"], "date": case["date"]},
                headers=diary_headers,
            )
        except httpx.RequestError as exc:
            return CaseResult(case["id"], case["name"], diary_trace_id, "error", f"日记请求异常: {exc}")

        if resp.status_code != 201:
            return CaseResult(
                case["id"], case["name"], diary_trace_id, "error",
                f"日记创建失败 [{resp.status_code}]: {resp.text[:200]}",
            )

        diary_id = resp.json()["id"]
        self._diary_id_map[case["id"]] = diary_id

        # ── 触发分析 ──
        analysis_trace_id = str(uuid4())
        analysis_headers = {
            **self._auth_headers(token),
            "X-Trace-Id": analysis_trace_id,
            "X-Developer-Mode": "true",
        }
        preset = case.get("preset")
        body: dict[str, Any] = {} if preset is None else {"replier_preset": preset}
        try:
            resp = self.client.post(
                f"/api/v1/analysis/{diary_id}",
                json=body,
                headers=analysis_headers,
            )
        except httpx.RequestError as exc:
            return CaseResult(
                case["id"], case["name"], analysis_trace_id, "error",
                f"分析请求异常: {exc}",
            )

        if resp.status_code == 201:
            return CaseResult(
                case["id"], case["name"], analysis_trace_id, "ok",
                f"diary_id={diary_id}",
            )
        return CaseResult(
            case["id"], case["name"], analysis_trace_id, "error",
            f"分析失败 [{resp.status_code}]: {resp.text[:200]}",
        )

    # ── 单轮对话 ──

    def seed_chat(self, token: str, case: dict[str, Any]) -> CaseResult:
        """创建会话 → 发送消息，返回结果。

        POST /api/v1/conversations 创建会话（带 trace 头）
        POST /api/v1/conversations/{id}/messages 发送消息（带 trace 头）
        """
        # ── 创建会话 ──
        conv_trace_id = str(uuid4())
        conv_headers = {
            **self._auth_headers(token),
            "X-Trace-Id": conv_trace_id,
            "X-Developer-Mode": "true",
        }
        try:
            resp = self.client.post("/api/v1/conversations", headers=conv_headers)
        except httpx.RequestError as exc:
            return CaseResult(case["id"], case["name"], conv_trace_id, "error", f"会话请求异常: {exc}")

        if resp.status_code != 201:
            return CaseResult(
                case["id"], case["name"], conv_trace_id, "error",
                f"会话创建失败 [{resp.status_code}]: {resp.text[:200]}",
            )

        conversation_id = resp.json()["id"]

        # ── 发送消息 ──
        msg_trace_id = str(uuid4())
        msg_headers = {
            **self._auth_headers(token),
            "X-Trace-Id": msg_trace_id,
            "X-Developer-Mode": "true",
        }

        # 解析 diary_ids 引用（C-C3 → C-D3 的实际 ID）
        resolved_ids = self._resolve_diary_ids(case.get("diary_ids", []))

        payload = {
            "content": case["content"],
            "diary_ids": resolved_ids,
            "auto_retrieve": case.get("auto_retrieve", True),
        }
        try:
            resp = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json=payload,
                headers=msg_headers,
            )
        except httpx.RequestError as exc:
            return CaseResult(
                case["id"], case["name"], msg_trace_id, "error",
                f"消息请求异常: {exc}",
            )

        if resp.status_code == 201:
            return CaseResult(
                case["id"], case["name"], msg_trace_id, "ok",
                f"conv={conversation_id[:8]}",
            )
        return CaseResult(
            case["id"], case["name"], msg_trace_id, "error",
            f"消息失败 [{resp.status_code}]: {resp.text[:200]}",
        )

    # ── 多轮对话 ──

    def seed_multi_turn(
        self, token: str, case: dict[str, Any]
    ) -> list[CaseResult]:
        """创建 1 个会话 → 连续发多条消息，每条独立 trace_id。

        返回每条消息对应的 CaseResult 列表。
        """
        results: list[CaseResult] = []

        # ── 创建会话 ──
        conv_trace_id = str(uuid4())
        conv_headers = {
            **self._auth_headers(token),
            "X-Trace-Id": conv_trace_id,
            "X-Developer-Mode": "true",
        }
        try:
            resp = self.client.post("/api/v1/conversations", headers=conv_headers)
        except httpx.RequestError as exc:
            results.append(CaseResult(
                case["id"], case["name"], conv_trace_id, "error", f"会话请求异常: {exc}",
            ))
            return results

        if resp.status_code != 201:
            results.append(CaseResult(
                case["id"], case["name"], conv_trace_id, "error",
                f"会话创建失败 [{resp.status_code}]: {resp.text[:200]}",
            ))
            return results

        conversation_id = resp.json()["id"]

        # ── 连续发送消息 ──
        for i, content in enumerate(case["messages"], 1):
            msg_trace_id = str(uuid4())
            msg_headers = {
                **self._auth_headers(token),
                "X-Trace-Id": msg_trace_id,
                "X-Developer-Mode": "true",
            }
            sub_id = f"{case['id']}#{i}"
            try:
                resp = self.client.post(
                    f"/api/v1/conversations/{conversation_id}/messages",
                    json={"content": content, "diary_ids": [], "auto_retrieve": True},
                    headers=msg_headers,
                )
            except httpx.RequestError as exc:
                results.append(CaseResult(
                    sub_id, f"{case['name']} (轮{i})", msg_trace_id, "error",
                    f"消息请求异常: {exc}",
                ))
                continue

            if resp.status_code == 201:
                results.append(CaseResult(
                    sub_id, f"{case['name']} (轮{i})", msg_trace_id, "ok",
                    f"conv={conversation_id[:8]}",
                ))
            else:
                results.append(CaseResult(
                    sub_id, f"{case['name']} (轮{i})", msg_trace_id, "error",
                    f"消息失败 [{resp.status_code}]: {resp.text[:200]}",
                ))

        return results

    # ── 记忆验证 ──

    def verify_memory(self, token: str) -> MemorySummary:
        """调用三个记忆接口，返回记忆状态摘要。

        1. GET /api/v1/memory/overview → episodic 总数、profile 是否构建
        2. GET /api/v1/memory/episodic → 情景记忆列表，统计 source 分布
        3. GET /api/v1/memory/profile → 用户画像，检查 recurring_topics
        """
        headers = self._auth_headers(token)
        summary = MemorySummary()

        # ── overview ──
        resp = self.client.get("/api/v1/memory/overview", headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"memory/overview 失败 [{resp.status_code}]: {resp.text[:200]}")
        overview = resp.json()
        summary.episodic_count = overview.get("episodic_total", 0)
        summary.profile_built = overview.get("profile_built", False)

        # ── episodic 列表 ──
        resp = self.client.get("/api/v1/memory/episodic", headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"memory/episodic 失败 [{resp.status_code}]: {resp.text[:200]}")
        entries = resp.json()
        for entry in entries:
            source = entry.get("source", "unknown")
            summary.sources[source] = summary.sources.get(source, 0) + 1

        # ── profile ──
        resp = self.client.get("/api/v1/memory/profile", headers=headers)
        if resp.status_code == 200:
            profile = resp.json()
            if profile is not None:
                summary.recurring_topics = profile.get("recurring_topics", [])
                baseline = profile.get("emotion_baseline", {})
                summary.dominant_emotion = baseline.get("dominant_emotion", "N/A")

        return summary

    # ── diary_ids 引用解析 ──

    def _resolve_diary_ids(self, diary_ids: list[Any]) -> list[int]:
        """将 diary_ids 中的字符串引用（case_id）解析为实际整数 ID。

        例如 ``["C-D3"]`` → ``[42]``（C-D3 创建后返回的 diary_id）。
        """
        resolved: list[int] = []
        for did in diary_ids:
            if isinstance(did, str):
                actual = self._diary_id_map.get(did)
                if actual is None:
                    raise ValueError(f"无法解析日记引用: {did}（尚未创建或创建失败）")
                resolved.append(actual)
            else:
                resolved.append(int(did))
        return resolved

    # ── 主流程 ──

    def run(self) -> None:
        """遍历账号和用例，汇总打印。"""
        if self.dry_run:
            self._print_dry_run()
            return

        accounts = [
            a for a in ACCOUNTS
            if self.user_filter is None or a["key"] == self.user_filter
        ]
        if not accounts:
            print(f"未找到匹配的用户: {self.user_filter}")
            return

        total_start = time.time()

        for account in accounts:
            key = account["key"]
            print(f"\n{'=' * 70}")
            print(f"  账号: {key} ({account['nickname']}) — {account['desc']}")
            print(f"{'=' * 70}")

            # ── 认证 ──
            try:
                token = self.ensure_user(
                    account["email"], DEFAULT_PASSWORD, account["nickname"]
                )
            except Exception as exc:
                print(f"  [FATAL] 认证失败: {exc}")
                continue

            # ── 日记 ──
            diary_cases = [c for c in DIARY_CASES if c["user"] == key]
            if diary_cases:
                print(f"\n  --- 日记用例 ({len(diary_cases)} 条) ---")
            for case in diary_cases:
                result = self.seed_diary(token, case)
                self.results[key].append(result)
                print(result)

            # ── 对话 ──
            chat_cases = [c for c in CHAT_CASES if c["user"] == key]
            if chat_cases:
                print(f"\n  --- 对话用例 ({len(chat_cases)} 条) ---")
            for case in chat_cases:
                try:
                    result = self.seed_chat(token, case)
                except Exception as exc:
                    result = CaseResult(
                        case["id"], case["name"], "", "error", f"异常: {exc}",
                    )
                self.results[key].append(result)
                print(result)

            # ── 多轮 ──
            mt_cases = [c for c in MULTI_TURN_CASES if c["user"] == key]
            if mt_cases:
                print(f"\n  --- 多轮用例 ({len(mt_cases)} 组) ---")
            for case in mt_cases:
                results = self.seed_multi_turn(token, case)
                self.results[key].extend(results)
                for r in results:
                    print(r)

            # ── 账号小结 ──
            self._print_account_summary(key)

            # ── 记忆验证 ──
            if not self.skip_memory_check:
                print(f"\n  --- 记忆验证 ---")
                try:
                    memory = self.verify_memory(token)
                    print(memory)
                except Exception as exc:
                    print(f"  [MEMORY] 验证失败: {exc}")

        # ── 全局汇总 ──
        elapsed = time.time() - total_start
        self._print_final_summary(elapsed)
        self.client.close()

    # ── 打印辅助 ──

    def _print_account_summary(self, key: str) -> None:
        results = self.results[key]
        ok_count = sum(1 for r in results if r.status == "ok")
        err_count = len(results) - ok_count
        print(f"\n  小计: {len(results)} 条 (成功 {ok_count}, 失败 {err_count})")

    def _print_final_summary(self, elapsed: float) -> None:
        print(f"\n{'#' * 70}")
        print(f"  全局汇总  (耗时 {elapsed:.1f}s)")
        print(f"{'#' * 70}")

        total_ok = 0
        total_err = 0
        for account in ACCOUNTS:
            key = account["key"]
            if self.user_filter is not None and key != self.user_filter:
                continue
            results = self.results.get(key, [])
            ok = sum(1 for r in results if r.status == "ok")
            err = len(results) - ok
            total_ok += ok
            total_err += err
            status_str = f"OK={ok}" if err == 0 else f"OK={ok} ERR={err}"
            print(f"  {key} ({account['nickname']:<6})  {len(results):>3} 条  {status_str}")

        print(f"\n  总计: {total_ok + total_err} 条 (成功 {total_ok}, 失败 {total_err})")
        print(f"  日记用例: {len(DIARY_CASES)}  对话用例: {len(CHAT_CASES)}  "
              f"多轮用例: {len(MULTI_TURN_CASES)} 组")
        print()

    def _print_dry_run(self) -> None:
        """仅打印测试用例清单，不调用 API。"""
        print(f"\n{'=' * 70}")
        print(f"  开发者模式测试数据清单 (DRY-RUN)")
        print(f"{'=' * 70}")
        print(f"  API 地址  : {self.base_url}")
        print(f"  密码      : {DEFAULT_PASSWORD}")
        print(f"  日记用例  : {len(DIARY_CASES)} 条")
        print(f"  对话用例  : {len(CHAT_CASES)} 条")
        print(f"  多轮用例  : {len(MULTI_TURN_CASES)} 组")
        print()

        accounts = [
            a for a in ACCOUNTS
            if self.user_filter is None or a["key"] == self.user_filter
        ]

        for account in accounts:
            key = account["key"]
            print(f"  ── {key} ({account['nickname']}) — {account['desc']} ──")

            # 日记
            diary_cases = [c for c in DIARY_CASES if c["user"] == key]
            if diary_cases:
                print(f"  日记 ({len(diary_cases)}):")
                for c in diary_cases:
                    preset_str = c["preset"] or "default"
                    content_preview = c["content"][:40].replace("\n", " ")
                    if len(c["content"]) > 40:
                        content_preview += "..."
                    print(
                        f"    {c['id']:<8} {c['name']:<22} "
                        f"{c['date']}  preset={preset_str:<10} "
                        f"| {content_preview}"
                    )

            # 对话
            chat_cases = [c for c in CHAT_CASES if c["user"] == key]
            if chat_cases:
                print(f"  对话 ({len(chat_cases)}):")
                for c in chat_cases:
                    ar_str = "T" if c["auto_retrieve"] else "F"
                    dids = c["diary_ids"]
                    dids_str = f"diary_ids={dids}" if dids else "diary_ids=[]"
                    content_preview = c["content"][:40].replace("\n", " ")
                    if len(c["content"]) > 40:
                        content_preview += "..."
                    print(
                        f"    {c['id']:<8} {c['name']:<22} "
                        f"auto={ar_str} {dids_str:<20} "
                        f"| {content_preview}"
                    )

            # 多轮
            mt_cases = [c for c in MULTI_TURN_CASES if c["user"] == key]
            if mt_cases:
                print(f"  多轮 ({len(mt_cases)} 组):")
                for c in mt_cases:
                    print(f"    {c['id']:<8} {c['name']:<22} {len(c['messages'])} 轮")
                    for i, msg in enumerate(c["messages"], 1):
                        preview = msg[:50].replace("\n", " ")
                        if len(msg) > 50:
                            preview += "..."
                        print(f"             轮{i}: {preview}")

            print()

        print(f"{'=' * 70}")
        print(f"  共 {len(accounts)} 个账号, "
              f"{len(DIARY_CASES)} 条日记, {len(CHAT_CASES)} 条对话, "
              f"{len(MULTI_TURN_CASES)} 组多轮")
        print(f"{'=' * 70}")


# ── CLI 入口 ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="开发者模式数据链路测试数据生成脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API 地址 (默认: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印测试用例清单，不调用 API",
    )
    parser.add_argument(
        "--user",
        default=None,
        help="只生成指定用户 (如 --user a)",
    )
    parser.add_argument(
        "--skip-memory-check",
        action="store_true",
        help="跳过记忆验证",
    )
    args = parser.parse_args(argv)

    seeder = DevTraceSeeder(
        base_url=args.base_url,
        dry_run=args.dry_run,
        user_filter=args.user,
        skip_memory_check=args.skip_memory_check,
    )
    seeder.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
