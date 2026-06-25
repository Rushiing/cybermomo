# Fly.io 迁移 runbook(Railway → Fly hkg)

> 状态:**草稿,等 user 给 flyctl token / 装 CLI 后开始**
>
> 账号:`wei.zhouw@gmail.com`(Fly.io)
> 目标 region:**hkg**(香港 · 中国大陆 ~50-100ms)
> 迁移工作量估计:2-4 小时,主要是 Postgres dump/restore + DNS

## 0 · 前置准备(你做)

### 0.1 · 装 flyctl + 登录(2 选 1)

**选项 A:本地装(macOS)**
```bash
brew install flyctl
flyctl auth login        # 浏览器登录,完成后回 CLI
flyctl auth token         # 把这个 token 给 Claude
```

**选项 B:授权 Claude 用 brew 装**
你说"用 brew 装 flyctl",我跑 `brew install flyctl`,然后给我 token 即可。

### 0.2 · 备份 Railway 数据(我做)

需要你给的:
- Railway 的 `DATABASE_URL`(看 Railway dashboard → cybermomo-production → Variables)

我会 `pg_dump` 出 sql 文件存本地,迁移失败可回滚。

---

## 1 · 创建 Fly app + Postgres(我做,你看着)

```bash
# 1) 创建 api app(应用名要全局唯一,如果冲突加后缀)
flyctl apps create cybermomo-api --org personal

# 2) 创建 Fly Postgres(hkg,1 个 machine,10GB 磁盘)
flyctl postgres create \
  --name cybermomo-pg \
  --region hkg \
  --vm-size shared-cpu-1x \
  --initial-cluster-size 1 \
  --volume-size 10

# 3) attach Postgres 到 api(自动注入 DATABASE_URL secret)
flyctl postgres attach --app cybermomo-api cybermomo-pg

# 4) 注入其余 secrets(从 Railway 现有 secrets 抄过来)
flyctl secrets set --app cybermomo-api \
  JWT_SECRET="$JWT_SECRET" \
  DASHSCOPE_API_KEY="$DASHSCOPE_API_KEY" \
  GOOGLE_OAUTH_CLIENT_ID="$GOOGLE_OAUTH_CLIENT_ID" \
  GOOGLE_OAUTH_CLIENT_SECRET="$GOOGLE_OAUTH_CLIENT_SECRET" \
  ADMIN_SECRET="$ADMIN_SECRET" \
  CORS_ORIGINS="https://cybermomo-web.fly.dev" \
  GOOGLE_OAUTH_REDIRECT_URI="https://cybermomo-api.fly.dev/api/auth/google/callback"
```

⚠️ **OAuth 回调要在 Google Console 加 fly.dev 的回调 URL**(你做,我提醒到位)。

---

## 2 · 部署 api(我做)

```bash
cd "/Users/xihe/Documents/项目文件/cybermomo/app"
flyctl deploy --config fly.api.toml --dockerfile Dockerfile
```

部署后跑 alembic migration(Dockerfile CMD 已经做了,首次启动会自动)。

健康检查:
```bash
curl https://cybermomo-api.fly.dev/healthz
```

---

## 3 · 迁移 Postgres 数据(我做)

```bash
# 从 Railway dump(用你给我的 DATABASE_URL)
pg_dump "$RAILWAY_DB_URL" \
  --no-owner --no-acl --format=custom \
  > /tmp/cybermomo-backup.dump

# 找 Fly Postgres 的 connection string(用 proxy)
flyctl postgres connect --app cybermomo-pg   # 看看能不能进
# 或者 attach 后,DATABASE_URL secret 里就是 fly 内部 URL,
# 用 flyctl proxy 转发到本地:
flyctl proxy 5433:5432 --app cybermomo-pg

# 在另一个 terminal:
pg_restore --no-owner --no-acl --clean --if-exists \
  -d "postgres://postgres:PASS@localhost:5433/cybermomo" \
  /tmp/cybermomo-backup.dump
```

完事跑 `alembic upgrade head`(已 deploy 的 api machine 重启时会自动跑,但手动跑一次更稳):
```bash
flyctl ssh console --app cybermomo-api
> cd /app/apps/api && alembic upgrade head
```

---

## 4 · 部署 web(我做)

```bash
cd "/Users/xihe/Documents/项目文件/cybermomo/app/apps/web"
flyctl apps create cybermomo-web --org personal

# 注入 build-time env(Next.js 在 build 阶段把这俩 bake 进 bundle)
flyctl deploy \
  --build-arg NEXT_PUBLIC_API_URL=https://cybermomo-api.fly.dev \
  --build-arg NEXT_PUBLIC_DEV_MOCK_AUTH=false
```

健康检查:
```bash
curl -I https://cybermomo-web.fly.dev/
# 200 + 看到 next.js 的 X-Powered-By 即对
```

---

## 5 · 验证(你做)

> ⚠️ 注:本 fly 迁移是**草稿**,当前决定留在 Railway,未执行。

1. 浏览器打开 `https://cybermomo-web.fly.dev/` 看登录页能不能加载
2. **从中国大陆 ping 一下延迟**:`ping cybermomo-api.fly.dev`(应该 < 100ms)
3. 登录跑 happy path,验证简报数据都在(数据 dump/restore 成功)
4. `psql $DATABASE_URL -c "SHOW max_connections;"` 看新 PG 上限(可能跟 Railway 不一样,需重算 pool)
   (原 /api/admin/db-stats 临时 endpoint 已在内测前清理删除)

---

## 6 · DNS / 域名

**短期(内测)**:直接用 `*.fly.dev` 子域,免备案免折腾

**长期(自定义域名)**:
```bash
flyctl certs add --app cybermomo-web cybermomo.your-domain.com
flyctl certs add --app cybermomo-api api.cybermomo.your-domain.com
# Fly 会给 DNS 记录(A + AAAA + CNAME),你去 DNS 服务商加
# 然后 fly 自动签 LE 证书
```

---

## 7 · cron(observation-sweep)

Railway 这边是手配的 Cron Job。Fly 没原生 cron。推荐:

**外部 cron 调 admin endpoint**(最简单):
- 用 GitHub Actions schedule(`*/60 * * * *`)
- workflow 里跑 `curl -X POST -H "X-Admin-Secret: $ADMIN_SECRET" https://cybermomo-api.fly.dev/api/admin/observation-sweep`
- ADMIN_SECRET 放 GitHub repo secret

或者用 cron-job.org(免费,5 分钟设置完)。

---

## 8 · 回滚预案

如果 Fly 部署后体验更差或者数据错位:
1. 不要立刻删 Railway,**保留 24-48 小时**
2. 前端域名 / web 用 fly.dev 子域,不切自定义域名 = 真人没访问到 Fly
3. 如果要回滚:web/api 改回 Railway URL,前端 redeploy,数据用 Railway 的(没动过)

---

## 9 · 关掉 Railway

确认 Fly 稳定运行 3-7 天后:
- 关 Railway service(保留代码备份)
- 取消 Railway 订阅
- ICP 备案如果未来要做(切大陆云),记得这步要先关

---

## TODO before deploy(我提醒,你确认)

- [ ] flyctl token 给我
- [ ] Railway 的 DATABASE_URL 给我(用于 pg_dump)
- [ ] 确认 ADMIN_SECRET 是不是用旧的 `1b27a291...`(还是已 rotate)
- [ ] Google OAuth 回调要加 fly.dev URL(你去 Google Console 改)
- [ ] cron 方案选 GitHub Actions 还是 cron-job.org
