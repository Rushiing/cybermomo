# CyberMOMO 内测 Runbook(ops 规矩 + 应急手册)

> 给内测期(~100 人陆续进)的运维规矩。配合审计报告 `docs/audit-2026-06.md` 看。
> 核心:有些审计项(平台封禁闭环、pipeline 可恢复)代码没完全做完,内测期用**规矩 + 人工 ops + admin endpoint** 兜底。

---

## 0 · 内测期三条铁规矩

1. **内测期间不 deploy**(除非紧急 hotfix)。
   原因(audit P0-4):onboarding 后台跑 6-8 分钟 LLM 链路(BackgroundTask),部署/重启会把跑一半的链路 kill,用户停在"有 match 没简报"。
   要 hotfix 时:先 `GET /api/admin/pipeline/incomplete` 看有没有在途用户,尽量等空窗;deploy 后必跑 `POST /api/admin/pipeline/repair-all` 补。

2. **平台底线封禁靠人工**(audit P0-2:`user_hard_blocklist` 表是空壳,没代码写入闭环)。
   内测期发现黄赌毒/违法用户 → 手动处理(见 §3)。公开发布前必须补代码闭环。

3. **ADMIN_SECRET 已泄露过,确认已 rotate**(audit P1-8)。所有 admin endpoint 靠它,别再贴进聊天/截图。

---

## 1 · 部署前检查(每次 deploy 必过)

```bash
# 后端起得来吗(ENV=prod 守卫:secret 没配齐会启动即 crash,这是故意的)
curl --max-time 10 https://cybermomo-production.up.railway.app/healthz   # {"ok":true}
# 确认 Railway 配齐:JWT_SECRET(≥16随机) / ADMIN_SECRET / CORS_ORIGINS(非 localhost) / DASHSCOPE_API_KEY / ENV
# 任一缺失 → 容器 crash,看部署日志的 "[startup] 生产配置不安全" 报错补齐
```

---

## 2 · "用户房间一直没简报" — pipeline 补跑

最常见的内测故障(部署中断/LLM 失败/DashScope 抖)。

```bash
SECRET="<ADMIN_SECRET>"
BASE="https://cybermomo-production.up.railway.app"

# ① 诊断:谁的 pipeline 没跑完(只读)
curl -sS -H "X-Admin-Secret: $SECRET" "$BASE/api/admin/pipeline/incomplete"
# → {"incomplete_user_count": N, "user_ids": [...]}

# ② 修单个用户(同步,返回报告:补了几步 desensitize/agent_chat/summary)
curl -sS -X POST -H "X-Admin-Secret: $SECRET" "$BASE/api/admin/pipeline/repair?user_id=29"

# ③ 批量修所有(后台串行,立即返;进度看 Railway 日志 [pipeline-resume])
curl -sS -X POST -H "X-Admin-Secret: $SECRET" "$BASE/api/admin/pipeline/repair-all"

# ④ 复查:应返 incomplete_user_count: 0
curl -sS -H "X-Admin-Secret: $SECRET" "$BASE/api/admin/pipeline/incomplete"
```

补跑是**按 stage 幂等**的:缺 hook 补脱敏、缺 done chat 补互聊、done chat 缺 summary 补简报;已有产物的跳过。重跑安全。

补跑内部并发(repair-one vs repair-all、跨 worker)由每个 match 的 `pg_advisory_xact_lock` 串行化,补跑之间不会重复建互聊。

> ⚠️ **已知局限(codex 终审 P0,档 B 闭环)**:补跑的建 chat 锁只覆盖补跑这条路;
> **正常 onboarding pipeline 建 chat 没拿同一把锁**。所以理论上"某新用户 onboarding 正在跑互聊"
> 与"同一刻 admin 对这个 match 手动 repair"会撞车、可能重复建一场互聊(只是浪费一次 LLM,
> 不会脏数据/泄露)。内测期规避:**别在拉新开闸/有用户正在 onboarding 时跑 repair-all 或 repair-one**
> (repair-one 同样会撞正在 onboarding 的那个 match);先 `GET /pipeline/incomplete` 看清单,
> 挑空窗补。公开发布前(档 B)把三处建 chat 入口
> (normal pipeline / redispatch / repair)统一收口到一个带锁的 create helper。

---

## 3 · 平台底线封禁(人工 · 内测临时方案)

代码闭环没做(P0-2),内测期手动:

```sql
-- 软删用户(deleted_at):立刻踢下线(auth 已过滤 deleted_at,cookie+mock 两条路都失效)
UPDATE users SET deleted_at = now() WHERE id = <user_id>;
```

- 软删后该用户 JWT 立刻失效(audit P1-10 已修:cookie 和 mock 路径都查 `deleted_at IS NULL`)。
- 留证:封禁前先把该用户的 .md / 消息 / 举报记录导出存档(违规数据要完整留,别只删)。
- 公开发布前补:`user_hard_blocklist` 写入闭环(report / Agent boundary_hit='铁律' / admin 审核都能写)+ match/chat 侧过滤。

---

## 4 · DashScope 配额监控

100 人 × ~50 LLM call ≈ 5000 call。RPM 15000 / TPM 1.2M 够用(峰值 ~250K TPM)。
内测期在阿里云控制台盯一眼用量,异常报错先看是不是限流。

---

## 5 · 连接池 / 并发(audit P0-5,内测期观察项)

- 当前:4 worker × pool(10+10)= 80 < PG usable 97。
- 风险:后台 pipeline 无并发上限 + LLM 调用期持有 session;"陆续来"缓解,但**短时高并发涌入**(如内测开闸瞬间)可能撑爆池子 → 普通请求 500/卡顿。
- 内测期 mitigation:**分批拉人**(别一次性群发 100 人链接),30 人/批、间隔开。
- 公开发布前补(档 B):后台 pipeline 全局 semaphore 限并发 + LLM 调用期释放 session。

---

## 6 · 快速体检一条龙

```bash
SECRET="<ADMIN_SECRET>"; BASE="https://cybermomo-production.up.railway.app"
curl -sS "$BASE/healthz"                                                    # 活着?
curl -sS -H "X-Admin-Secret: $SECRET" "$BASE/api/admin/pipeline/incomplete" # 有没有掉队用户?
# mock 越权应被拒(返 401 = ENV=prod 生效)
curl -sS -o /dev/null -w "%{http_code}\n" -H "X-Mock-User-Id: 1" "$BASE/api/auth/me"
```
