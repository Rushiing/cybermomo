# cybermomo-app

CyberMomo 灵魂快照 · Railway 部署版。

托管 `prototype-v0.4.html`，代理智谱 GLM-5，收集测试数据到 Postgres。

## 线上结构

```
[browser] → prototype-v0.4.html
            ↓
[/api/messages]  → dashscope (GLM-5)
[/api/log-generation]  → Postgres: generations
[/api/log-feedback]    → Postgres: feedback
```

## 环境变量（在 Railway 设）

| 变量 | 说明 |
|---|---|
| `GLM_API_KEY` | 智谱 / dashscope key，格式 `sk-sp-...` |
| `DATABASE_URL` | Railway Postgres 插件会自动注入，不用手填 |
| `PORT` | Railway 自动注入 |

## Railway 部署步骤

1. GitHub 新建空 repo，把本目录推上去
2. Railway → New Project → Deploy from GitHub repo → 选这个 repo
3. 项目里 Add Service → Database → PostgreSQL（自动注入 `DATABASE_URL`）
4. 回到 web service → Variables → 加 `GLM_API_KEY`
5. 重新部署即可

启动命令由 `Procfile` 提供：`uvicorn app:app --host 0.0.0.0 --port $PORT`

首次启动会自动建表（`generations` + `feedback`，幂等），不需要手动跑迁移。

## 本地开发

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GLM_API_KEY=sk-sp-...
# 不设 DATABASE_URL 也能跑，只是不会记录数据
uvicorn app:app --reload --port 8787
# 打开 http://localhost:8787
```

## 数据结构

```sql
-- 每次生成一条，包含用户原始输入和生成的 .md
generations(id, created_at, prompt_version, quiz_version, model,
            nickname, age_band, gender, mbti,
            dimension_scores jsonb, raw_answers jsonb, supplement jsonb,
            md_output text)

-- 每份反馈一条，外键指向 generations
feedback(id, created_at, generation_id fk, payload jsonb)
```

查询示例：

```sql
-- 看最近 10 份生成 + 反馈
SELECT g.id, g.nickname, g.created_at,
       g.prompt_version, g.dimension_scores,
       f.payload -> 'overall_fit' AS overall_fit
FROM generations g
LEFT JOIN feedback f ON f.generation_id = g.id
ORDER BY g.created_at DESC
LIMIT 10;
```
