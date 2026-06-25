"""leak_scanner 单元测试(.md 泄露兜底 · 铁律3)。

纯函数、无 DB/无 LLM,直接断言。重点覆盖:
- _norm 的归一(NFKC + 去空白标点 + 小写)能抗"插空格/全角/标点"绕过
- collect_profile_freetext 抽取范围 + 短文本过滤
- find_leak 长片段照抄 / 短整段照抄 命中,普通文本不误判
- scrub_peer_visible_text 命中即清空、干净即原样
"""

from src.shared.leak_scanner import (
    _MIN_SOURCE_LEN,
    _norm,
    collect_profile_freetext,
    find_leak,
    scrub_peer_visible_text,
)


# ---------- _norm ----------

def test_norm_strips_whitespace_punct_and_lowercases():
    assert _norm("Hello,  World!") == "helloworld"
    assert _norm("微 信 号:abc_123") == _norm("微信号abc123")


def test_norm_nfkc_folds_fullwidth():
    # 全角字母数字 → 半角后应与半角等价(抗全角绕过)
    assert _norm("ＡＢＣ１２３") == _norm("ABC123")


# ---------- collect_profile_freetext ----------

def test_collect_pulls_portrait_and_answers_and_labels():
    profile = {
        "portrait": {
            "title": "深夜写诗的工程师",
            "title_reason": "在理性与感性之间反复横跳的人",
            "body": ["喜欢一个人在深夜散步", "短"],  # "短" 会被长度过滤
            "tags": ["内向但内心其实很热烈"],
        },
        "raw_answers": {
            "q1": {"option_text": "我更愿意先听完再表达观点"},
            "q2": {"option_text": "x"},  # 太短,过滤
        },
        "relationship_warmth": {
            "trust": {"label": "需要时间建立信任"},
        },
    }
    out = collect_profile_freetext(profile)
    assert "深夜写诗的工程师" in out
    assert "在理性与感性之间反复横跳的人" in out
    assert "喜欢一个人在深夜散步" in out
    assert "内向但内心其实很热烈" in out
    assert "我更愿意先听完再表达观点" in out
    assert "需要时间建立信任" in out
    # 短文本被过滤
    assert "短" not in out
    assert "x" not in out


def test_collect_handles_non_dict():
    assert collect_profile_freetext(None) == []
    assert collect_profile_freetext("nope") == []
    assert collect_profile_freetext({}) == []


# ---------- find_leak:命中 ----------

def test_find_leak_long_verbatim_copy_hits():
    source = "我是一个习惯在深夜独自思考人生方向的人"
    text = f"对方跟你很像,他说『{source}』,你们都这样。"
    assert find_leak(text, [source]) is not None


def test_find_leak_short_full_segment_hits():
    # 8~12 字的短句整段照抄(如微信号、口头禅原文)
    source = "深夜散步的人"  # 归一后 6 字 < 8,先确认它达不到源门槛
    assert len(_norm(source)) < _MIN_SOURCE_LEN
    # 用一个刚好 ≥8 的短源
    src2 = "习惯深夜散步思考"  # 8 字
    assert len(_norm(src2)) >= _MIN_SOURCE_LEN
    assert find_leak(f"他也{src2}呢", [src2]) is not None


def test_find_leak_catches_space_insertion_bypass():
    # 攻击者/LLM 在原文里插空格/标点试图绕过逐字匹配 → 归一后仍命中
    source = "我的微信号是abcdef123"
    leaked = "我 的 微 信 号 是 a-b-c-d-e-f-1-2-3"
    assert find_leak(leaked, [source]) is not None


def test_find_leak_catches_fullwidth_bypass():
    source = "私密代号是night2046"
    leaked = "私密代号是ｎｉｇｈｔ２０４６"  # 全角
    assert find_leak(leaked, [source]) is not None


# ---------- find_leak:不误判 ----------

def test_find_leak_no_overlap_returns_none():
    assert find_leak("今天天气不错我们去散步吧", ["他喜欢研究量子物理和古典音乐"]) is None


def test_find_leak_short_source_below_threshold_is_ignored():
    # 源归一后 < 8 字不作为比对源,避免常见短词造成大面积误杀
    short = "你好呀"
    assert len(_norm(short)) < _MIN_SOURCE_LEN
    assert find_leak("你好呀，很高兴认识你", [short]) is None


def test_find_leak_empty_text_returns_none():
    assert find_leak("", ["我是一个习惯深夜思考的人"]) is None


# ---------- scrub_peer_visible_text ----------

def _profile_with(text: str) -> dict:
    return {"portrait": {"title_reason": text}}


def test_scrub_blanks_on_leak():
    secret = "我童年在云南的一个小山村里长大"
    peer = _profile_with(secret)
    utterance = f"我感觉你跟他很合,因为{secret}"
    safe, hit = scrub_peer_visible_text(utterance, peer)
    assert safe == ""
    assert hit is not None


def test_scrub_passes_clean_text():
    peer = _profile_with("我童年在云南的一个小山村里长大")
    clean = "你们都喜欢安静的相处方式,挺搭的。"
    safe, hit = scrub_peer_visible_text(clean, peer)
    assert safe == clean
    assert hit is None


def test_scrub_no_sources_returns_original():
    # peer profile 没有可用自由文本源 → 原样返回(不阻断)
    safe, hit = scrub_peer_visible_text("任意文本", {})
    assert safe == "任意文本"
    assert hit is None
