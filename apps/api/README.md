# CyberMOMO API

FastAPI 后端,部署到 Railway。

## 模块结构

```
apps/api/
├── main.py             # FastAPI 入口
├── requirements.txt    # Python 依赖
└── src/                # 业务模块(待建)
    ├── auth/           # 01-用户注册 + Google OAuth
    ├── md/             # 02-.md 创建(v3 profile JSON 入库)
    ├── match/          # 03-匹配引擎
    ├── agent_chat/     # 04-Agent 互聊
    ├── room/           # 05-个人房间
    ├── summary/        # 06-Agent 简报
    ├── human_chat/     # 07-真人聊天
    ├── governance/     # 治理(举报、硬拉黑、违规留底)
    ├── llm/            # LLM 网关 + provider 抽象 + prompt 版本
    └── shared/         # 共用(模型、工具、auth dep)
```

模块间依赖规则:**模块只能依赖 `shared/` 和 `llm/`,不横向依赖业务模块**。

## 本地开发

```bash
# 在 monorepo 根目录
docker-compose up -d  # 启动 Postgres + pgvector

# 进入 api 目录
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 设置 env
cp ../../.env.example ../../.env  # 在根目录配置变量

# 跑
uvicorn main:app --reload --port 8787

# 访问
curl http://localhost:8787/healthz
```

## 设计参考

详细设计见 `cybermomo/` vault:
- `工程拆解/_工程架构.md` — 整体架构
- `工程拆解/_数据模型.md` — 数据模型(15 张表)
- `落地拆解/0X-*/` — 7 大业务模块
