# CyberMOMO Web

Next.js 14 (App Router) + TypeScript + Tailwind 前端。

## 设计 tokens

全部在 `tailwind.config.ts` 中,基于 `cybermomo/交互拆解/_设计调性.md`:

- **米白底** `bg-bg`(#FAF8F3)
- **拓竹绿** `bg-primary`(#00AE42)
- **警告红** `bg-warn`(#DC2626)
- **思源黑 + Inter** `font-sans`
- **微圆** `rounded-sm/md/lg`(8/12/16px)

## 本地开发

```bash
# monorepo 根目录先起 docker-compose(后端 Postgres)
cd ../..
docker-compose up -d

# 起后端
cd apps/api
uvicorn main:app --reload --port 8787

# 起前端
cd ../web
pnpm install   # 或 npm i
pnpm dev       # http://localhost:3000
```

`next.config.js` 把 `/api/*` 反向代理到后端 `http://localhost:8787`。

## 屏与原型对应

`cybermomo/DEMO/mvp/` 下的 13 屏 HTML 原型是**视觉设计稿**。MVP 实现时按对应屏号迁移:

| 屏 | 原型 | 实现路径(待建) |
|---|---|---|
| 1 Login | `01-login.html` | `app/page.tsx`(本页) |
| 2-5 Onboarding | `02-onboarding.html` | `app/onboarding/page.tsx` |
| 6 Basic | `03-md-basic.html` | `app/md/basic/page.tsx` |
| 7 Quiz | `04-md-quiz.html` | `app/md/quiz/page.tsx`(用 v3 题库) |
| 8 Generating | `05-md-generating.html` | `app/md/generating/page.tsx` |
| 9 Review | `06-md-review.html` | `app/md/review/page.tsx` |
| 10 Empty | `07-room-empty.html` | `app/room/page.tsx`(空态分支) |
| 11-12 Plaza | `08-plaza.html` | **暂 hold**(产品形态待讨论) |
| 13-14 Room | `09-room.html` | `app/room/page.tsx` |
| 16 Prebrief | `10-prebriefing.html` | `app/chat/[sessionId]/briefing/page.tsx` |
| 17-18 Chat | `11-chat.html` | `app/chat/[sessionId]/page.tsx` |
| 20 Observation | `12-room-observation.html` | `app/room/page.tsx`(回访状态) |

## 部署

MVP 阶段先本地开发。后续部署可:
- 同 Railway service(独立 service · 推荐)
- 或 Vercel(Next.js 原生友好)
