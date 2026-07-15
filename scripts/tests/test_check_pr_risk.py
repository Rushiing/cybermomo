import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_pr_risk import validate_pr_body  # noqa: E402


BOUNDARY = """## 任务边界

- 要解决：建立可重复的发布验收
- 不改：业务行为和生产数据
- 验收标准：CI 和 production smoke 通过
"""


class PullRequestRiskGateTests(unittest.TestCase):
    def test_medium_risk_pr_passes(self):
        body = BOUNDARY + """
- [ ] 低：文档
- [x] 中：部署配置
- [ ] 高：生产数据
"""
        self.assertEqual(validate_pr_body(body), [])

    def test_missing_boundary_and_multiple_risks_fail(self):
        body = """
- 要解决：
- 不改：生产数据
- 验收标准：
- [x] 低：文档
- [x] 中：部署配置
"""
        errors = validate_pr_body(body)
        self.assertIn("任务边界 `要解决` 不能为空", errors)
        self.assertIn("任务边界 `验收标准` 不能为空", errors)
        self.assertIn("风险等级必须且只能勾选低/中/高中的一个", errors)

    def test_high_risk_requires_all_confirmations(self):
        body = BOUNDARY + """
- [ ] 低：文档
- [ ] 中：部署配置
- [x] 高：OAuth
- [x] 用户已确认任务边界
- [ ] 部署或生产操作前需再次人工确认
- [x] 已写明回滚/恢复方案
"""
        errors = validate_pr_body(body)
        self.assertEqual(errors, ["高风险 PR 必须确认：部署或生产操作前需再次人工确认"])

    def test_high_risk_with_all_confirmations_passes(self):
        body = BOUNDARY + """
- [ ] 低：文档
- [ ] 中：部署配置
- [x] 高：OAuth
- [x] 用户已确认任务边界
- [x] 部署或生产操作前需再次人工确认
- [x] 已写明回滚/恢复方案
"""
        self.assertEqual(validate_pr_body(body), [])

    def test_checked_marker_is_case_insensitive(self):
        body = BOUNDARY + """
- [X] 低：文档
- [ ] 中：部署配置
- [ ] 高：生产数据
"""
        self.assertEqual(validate_pr_body(body), [])


if __name__ == "__main__":
    unittest.main()
