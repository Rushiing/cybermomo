"""
冷启动 mock 用户 seed 模块。

- archetypes.py:8 骨架 × 2-3 variant = 20 人 fixture
- operations.py:upsert_user / run_pipeline / verify_* 等业务操作

被两处消费:
- apps/api/src/admin/router.py:HTTP endpoint 远程触发(主路径)
- scripts/cold_start_seed.py:本地 CLI 触发(兼容路径)
"""
