"""Offline psychology knowledge base for the insight skill.

A static, keyword-retrievable set of theory entries so the insight skill
works without any embedding/Chroma dependency. Each entry pairs a theory
with a self-observation angle — the skill prompt injects the top matches
to ground its analysis. Entries describe common psychological patterns;
they are reference material, never diagnostic labels.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PsychologyEntry:
    theory: str
    summary: str
    observation: str
    keywords: tuple[str, ...]


PSYCHOLOGY_ENTRIES: tuple[PsychologyEntry, ...] = (
    PsychologyEntry(
        theory="情绪粒度",
        summary=(
            "情绪粒度指区分并精确命名情绪的能力。粗粒度者只用“难受/烦躁”概括一切，"
            "细粒度者能分清是失望、委屈还是羞耻。命名越精确，情绪越容易被调节。"
        ),
        observation="试着把此刻的感受换成一个更具体的词，会发生什么？",
        keywords=("情绪", "烦躁", "难受", "说不清", "复杂", "心情", "感觉", "情绪化"),
    ),
    PsychologyEntry(
        theory="认知重评",
        summary=(
            "同一事件可有多种解释框架，情绪跟着解释走。重评不是强行乐观，"
            "而是主动寻找同样成立、但更有建设性的解读，以降低情绪强度。"
        ),
        observation="这件事还有哪一种同样说得通、但你没选的解释？",
        keywords=("生气", "愤怒", "委屈", "接受不了", "想不通", "不公平", "受不了"),
    ),
    PsychologyEntry(
        theory="认知三角（CBT）",
        summary=(
            "想法、情绪、行为互相牵动。困扰常来自自动化思维——未被审视就当真的念头。"
            "把念头写下来并追问证据，是松动它的第一步。"
        ),
        observation="支撑这个结论的证据，除了感受本身还有别的吗？",
        keywords=(
            "总是",
            "肯定",
            "觉得",
            "认为",
            "怀疑",
            "肯定不",
            "注定",
            "认为自己不行",
        ),
    ),
    PsychologyEntry(
        theory="反刍思维",
        summary=(
            "反复回放同一场景并咀嚼“为什么”，看起来像分析，实则强化无力感。"
            "反刍与反思的区别：前者循环、后者推进到下一步行动。"
        ),
        observation="这段回想有没有产生任何新的结论，还是同一圈在转？",
        keywords=("反复", "一直想", "停不下来", "睡不着", "放不下", "回想", "后悔", "懊悔"),
    ),
    PsychologyEntry(
        theory="需求层次",
        summary=(
            "生理、安全、归属、尊重、自我实现逐层递进。当高层追求受挫时，"
            "常被体验为一种说不出的空，其根源可能在更低层未被满足。"
        ),
        observation="最近睡眠、饮食、安全感这些底层，是不是也在透支？",
        keywords=("迷茫", "空虚", "意义", "不知道想要什么", "浑浑噩噩", "倦怠", "累"),
    ),
    PsychologyEntry(
        theory="自我决定理论",
        summary=(
            "人的三种基本心理需要：自主、胜任、归属。动机枯竭往往是其中一种被剥夺："
            "被安排（自主）、长期做不好（胜任）、孤立无援（归属）。"
        ),
        observation="这件事里，是选择权、成就感还是联结感先丢了？",
        keywords=("没动力", "不想做", "拖延", "提不起劲", "被迫", "不得不", "麻木"),
    ),
    PsychologyEntry(
        theory="依恋理论",
        summary=(
            "早期依恋模式延续到成年关系：焦虑型怕被抛、反复确认；回避型怕被吞没、"
            "先撤退。识别自己是哪一种，能把“他为什么这样”转成“我为什么痛”。"
        ),
        observation="对方晚回消息时，你第一个冒出来的念头是什么？",
        keywords=(
            "依赖",
            "黏人",
            "怕失去",
            "没安全感",
            "忽冷忽热",
            "疏远",
            "分手",
            "恋人",
            "伴侣",
        ),
    ),
    PsychologyEntry(
        theory="完美主义",
        summary=(
            "适应型完美主义追求卓越，非适应型恐惧失败：把自我价值与表现绑定，"
            "于是拖延、过度准备、无法开始，本质都是对“不完美”的防御。"
        ),
        observation="如果做到 80 分，你担心具体会发生什么？",
        keywords=("完美", "必须", "高标准", "不允许出错", "细节", "强迫", "纠结"),
    ),
    PsychologyEntry(
        theory="冒名顶替感",
        summary=(
            "把成功归因运气、把失败归因能力，坚信自己“迟早被拆穿”。"
            "常见于高成就者，与实际能力无关，与归因习惯有关。"
        ),
        observation="如果朋友拿着你的成绩单来咨询，你会怎么评价他？",
        keywords=("心虚", "配不上", "运气", "会被发现", "名不副实", "实力", "冒名"),
    ),
    PsychologyEntry(
        theory="习得性无助",
        summary=(
            "长期不可控的失败让人停止尝试，因为大脑学会了“做什么都没用”。"
            "打破它的方式不是鼓励打气，而是制造一次小的、确定的可控体验。"
        ),
        observation="有没有一件 5 分钟内能完成、结果完全由你掌控的小事？",
        keywords=("放弃", "没用", "努力也没用", "绝望", "认命", "躺平", "无力"),
    ),
    PsychologyEntry(
        theory="归因风格",
        summary=(
            "内控者倾向归因自己（可控感强但易自责），外控者归因环境（少自责但易无力）。"
            "情绪困扰常来自把可控的事归了外因、把不可控的事揽到自己身上。"
        ),
        observation="这件事里，哪些部分其实在你手里，哪些从来就不在？",
        keywords=("怪", "都怪我", "怪别人", "命", "运气差", "为什么是我"),
    ),
    PsychologyEntry(
        theory="心流",
        summary=(
            "当挑战与能力匹配、目标即时反馈时进入心流——时间感消失的专注。"
            "长期没有心流体验的工作，会让人在忙碌中感到空洞。"
        ),
        observation="上一次忘记时间是在做什么？那件事有什么不同？",
        keywords=("专注", "无聊", "机械", "重复", "麻木", "充实", "效率"),
    ),
    PsychologyEntry(
        theory="心理边界",
        summary=(
            "边界不是冷漠，而是分清“我的课题/你的课题”。常见信号："
            "难以拒绝、替别人情绪负责、被评价就剧烈起伏——都是边界松动。"
        ),
        observation="这句评价描述的是你，还是评价者自己的标准？",
        keywords=(
            "拒绝",
            "不好意思",
            "讨好",
            "内疚",
            "被评价",
            "在意别人看法",
            "亏欠",
            "父母期望",
        ),
    ),
    PsychologyEntry(
        theory="自我分化",
        summary=(
            "既能感受情绪、又不被情绪淹没地思考，叫自我分化良好。"
            "分化不足的人在压力下要么只剩情绪（冲动决定），要么只剩理智（隔离麻木）。"
        ),
        observation="现在让你做决定，你是带着情绪做，还是把情绪关掉做？",
        keywords=("冷静", "上头", "冲动", "失控", "压抑", "麻木", "理性"),
    ),
    PsychologyEntry(
        theory="经验性回避（ACT）",
        summary=(
            "接纳承诺疗法认为痛苦常来自“摆脱情绪”本身：越对抗越放大。"
            "与情绪的关系从搏斗改为“允许经过”，行动反而更自由。"
        ),
        observation="如果不急着让这种感觉消失，它会自己走到哪里？",
        keywords=("焦虑", "对抗", "摆脱", "控制不住", "越想越", "内耗", "接纳"),
    ),
    PsychologyEntry(
        theory="投射",
        summary=(
            "把自己不能接受的念头安到别人身上（投射），或因别人的话剧烈刺痛"
            "（被击中的投射）。被刺痛之处，常藏着一个未处理的自我评价。"
        ),
        observation="他那句话刺到你的，是事实，还是你本来就怕它是事实？",
        keywords=("他是不是觉得", "别人怎么看", "针对我", "看不起", "被否定", "敏感"),
    ),
    PsychologyEntry(
        theory="社会比较",
        summary=(
            "人通过比较定位自我，但社交平台把比较对象换成了千万人的高光片段。"
            "嫉妒的强度，正比于该领域对你自我价值的重要性。"
        ),
        observation="嫉妒他的那件事，对你来说为什么这么重要？",
        keywords=("比较", "羡慕", "嫉妒", "别人都", "同龄人", "差距", "落后"),
    ),
    PsychologyEntry(
        theory="自我关怀",
        summary=(
            "对朋友和对自己，用的是两套完全不同的话。自我关怀三要素："
            "善待自己、承认人之共性、如实而不夸大地看待此刻。"
        ),
        observation="把你想对自己说的话，说给最好的朋友听一遍试试。",
        keywords=("自责", "讨厌自己", "失败", "没出息", "嫌弃自己", "骂自己"),
    ),
    PsychologyEntry(
        theory="丧失与哀伤",
        summary=(
            "丧失不限于死亡：关系、身份、可能性都会被哀悼。哀伤不是线性阶段，"
            "而是波动式的反复；允许它反复，比催促自己“该走出来了”更有效。"
        ),
        observation="你在哀悼的，是那个人，还是和他在一起时的自己？",
        keywords=("失去", "离世", "告别", "结束了", "遗憾", "怀念", "怀念过去"),
    ),
    PsychologyEntry(
        theory="职业倦怠",
        summary=(
            "倦怠三特征：情绪耗竭、去人格化（对服务对象冷漠）、成就感丧失。"
            "它与“不够努力”无关，是长期投入与回馈失衡的结果，休息只解决三分之一。"
        ),
        observation="是身体累，还是心里那杆秤长期没有回过本？",
        keywords=("加班", "职业", "工作压力", "辞职", "裸辞", "想逃离", "burnout", "burn out"),
    ),
    PsychologyEntry(
        theory="拖延的情绪调节观",
        summary=(
            "当代研究视拖延为情绪调节问题而非时间管理问题：回避的是任务附带的"
            "无聊、焦虑或自我怀疑。解决入口是先处理情绪，再谈方法。"
        ),
        observation="打开那份文件前的一秒钟，具体是哪种不舒服？",
        keywords=("拖延", "拖到", "deadline", "截止", "赶工", "临时抱佛脚"),
    ),
    PsychologyEntry(
        theory="矛盾心理",
        summary=(
            "同时想要两个互斥的东西（稳定与自由、亲密与独立）是正常心理，"
            "不是优柔寡断。真正的决策，是承认会失去一半、然后选择承担哪一半。"
        ),
        observation="如果两个选项都不能既要，你更承受不起失去哪个？",
        keywords=("纠结", "犹豫", "两难", "选择困难", "摇摆", "舍不得", "要不要"),
    ),
)


def retrieve_psychology(query: str, top: int = 3) -> list[PsychologyEntry]:
    """Keyword-scored retrieval over the static entries (offline, no deps)."""
    if not query.strip():
        return []
    scored: list[tuple[int, PsychologyEntry]] = []
    for entry in PSYCHOLOGY_ENTRIES:
        score = sum(1 for kw in entry.keywords if kw in query)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda pair: (-pair[0], PSYCHOLOGY_ENTRIES.index(pair[1])))
    return [entry for _, entry in scored[:top]]
