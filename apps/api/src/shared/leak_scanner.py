"""
shared · .md 原文泄露确定性扫描器(audit P0-1 兜底)

铁律3:用户 .md 全文绝对不向他人暴露。架构上 desensitize/agent_chat 的 prompt
设计已尽量只喂脱敏字段,但 domains/label/portrait 仍含客户端可控自由文本,且
"LLM 不照抄原文"只是 prompt 自律。本模块提供**确定性兜底**:

任何要给"对方"看到的 LLM 产物(desensitize 的 hook_text、agent_chat 的 utterance)
入库前,跟相关用户 profile 的自由文本比对,命中足够长的连续重叠片段 → 判定泄露。
调用方据此丢弃/重跑/置空,不让原文穿透到对方。

设计取舍:
- 只防"长片段照抄",不防语义复述(语义复述不算字面外泄,且属人格化表达,允许)
- 中文为主,按字符 n-gram 滑窗,默认窗口 12 字(约半句话)
- 大小写/空白归一,降低绕过空间;但不做分词(够用且无依赖)
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

# 命中判定:连续重叠 ≥ 这么多字符就算"照抄原文片段"
_DEFAULT_NGRAM = 12
# 提取 profile 自由文本时,短于这个长度的片段不参与比对(避免常见短词误杀)
_MIN_SOURCE_LEN = 8

# 比较态剥掉所有空白 + 常见标点(全/半角),抗"插标点/加空格"绕过(codex review P1-3)
# 留汉字/字母/数字。NFKC 已把全角折叠成半角,这里统一删非字母数字。
_STRIP_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def _norm(s: str) -> str:
    """归一(抗绕过):NFKC 折叠全角半角/兼容字符 → 小写 → 删所有空白和标点。

    NFKC 把"１２３/ＡＢＣ/，。！"这类全角折成半角;再删非字母数字,
    使"微 信 号"、"微.信.号"、"微信号"归一后一致 → 简单插标点/加空格绕不过。
    只改"比较态",不改落库文本。
    """
    nfkc = unicodedata.normalize("NFKC", s or "")
    return _STRIP_RE.sub("", nfkc).lower()


def collect_profile_freetext(profile_json: dict) -> list[str]:
    """
    从一个 profile_json 里抽出所有"自由文本"字段(用户/LLM 可写的散文),
    用作泄露比对的源。结构化枚举/数值/字段路径不算自由文本,不参与。
    """
    out: list[str] = []
    if not isinstance(profile_json, dict):
        return out

    portrait = profile_json.get("portrait") or {}
    for k in ("title", "title_reason", "core_tension", "main_type"):
        v = portrait.get(k)
        if isinstance(v, str):
            out.append(v)
    for k in ("body", "tags"):
        seq = portrait.get(k) or []
        if isinstance(seq, list):
            out.extend(x for x in seq if isinstance(x, str))

    # raw_answers.option_text:问卷选项原文,属用户可控自由文本
    raw = profile_json.get("raw_answers") or {}
    if isinstance(raw, dict):
        for ans in raw.values():
            if isinstance(ans, dict):
                t = ans.get("option_text")
                if isinstance(t, str):
                    out.append(t)

    # 维度 label 也可能被塞文本
    rw = profile_json.get("relationship_warmth") or {}
    if isinstance(rw, dict):
        for dim in rw.values():
            if isinstance(dim, dict):
                lb = dim.get("label")
                if isinstance(lb, str):
                    out.append(lb)

    return [s for s in out if len(_norm(s)) >= _MIN_SOURCE_LEN]


def find_leak(
    text: str,
    sources: Iterable[str],
    *,
    ngram: int = _DEFAULT_NGRAM,
) -> str | None:
    """
    text 里是否照抄了 sources 的连续片段。命中返回片段(便于日志),否则 None。

    判定:对每个源 s(归一后 ≥ _MIN_SOURCE_LEN),取匹配长度 L = min(len(s), ngram):
    - 源比 ngram 长 → 源的任意 ngram 长连续片段出现在 text 即命中
    - 源比 ngram 短(但 ≥ _MIN_SOURCE_LEN)→ 整段(≥8 字)被 text 包含即命中
    这样既能抓长原文照抄,也能抓"微信号 / 短句原文"这类 8-12 字的整段照抄。
    误判只会导致丢弃/重跑(fail-safe),不会放过泄露。
    """
    nt = _norm(text)
    if not nt:
        return None
    for s in sources:
        ns = _norm(s)
        if len(ns) < _MIN_SOURCE_LEN:
            continue
        L = min(len(ns), ngram)
        for i in range(len(ns) - L + 1):
            frag = ns[i : i + L]
            if frag in nt:
                return frag
    return None


def scrub_peer_visible_text(
    text: str,
    *peer_profiles: dict,
    ngram: int = _DEFAULT_NGRAM,
) -> tuple[str, str | None]:
    """
    给"对方可见"的 LLM 产物做泄露兜底。

    text:LLM 产出的、即将被对方看到的文本(hook_text / utterance)
    peer_profiles:相关用户(尤其对方)的 profile_json;命中其自由文本即判泄露

    返回 (safe_text, leaked_fragment):
    - 未命中 → (原 text, None)
    - 命中 → ("", 命中片段)。调用方拿到 leaked 非 None 时应丢弃/重跑/置空,
      不要把原 text 落库给对方看。
    """
    sources: list[str] = []
    for p in peer_profiles:
        sources.extend(collect_profile_freetext(p))
    if not sources:
        return text, None
    hit = find_leak(text, sources, ngram=ngram)
    if hit:
        return "", hit
    return text, None
