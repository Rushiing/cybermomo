#!/usr/bin/env python3
"""Validate the delivery boundary and risk declarations in a PR body."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


BOUNDARY_FIELDS = ("要解决", "不改", "验收标准")
RISK_LEVELS = ("低", "中", "高")
HIGH_RISK_CONFIRMATIONS = (
    "用户已确认任务边界",
    "部署或生产操作前需再次人工确认",
    "已写明回滚/恢复方案",
)


def _checked(body: str, label: str) -> bool:
    pattern = rf"^- \[[xX]\]\s+{re.escape(label)}(?:：|\s|$)"
    return re.search(pattern, body, flags=re.MULTILINE) is not None


def validate_pr_body(body: str) -> list[str]:
    errors: list[str] = []
    for field in BOUNDARY_FIELDS:
        match = re.search(
            rf"^- {re.escape(field)}：[ \t]*([^\r\n]*)$",
            body,
            flags=re.MULTILINE,
        )
        if match is None or not match.group(1).strip():
            errors.append(f"任务边界 `{field}` 不能为空")

    selected_risks = [risk for risk in RISK_LEVELS if _checked(body, risk)]
    if len(selected_risks) != 1:
        errors.append("风险等级必须且只能勾选低/中/高中的一个")
    elif selected_risks[0] == "高":
        for confirmation in HIGH_RISK_CONFIRMATIONS:
            if not _checked(body, confirmation):
                errors.append(f"高风险 PR 必须确认：{confirmation}")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-path", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    event = json.loads(args.event_path.read_text(encoding="utf-8"))
    body = event.get("pull_request", {}).get("body") or ""
    errors = validate_pr_body(body)
    if errors:
        print("PR delivery gate failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PR delivery boundary and risk declaration are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
