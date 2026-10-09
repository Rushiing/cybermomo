# Google OAuth 接入步骤

部署完代码后,要让 "用 Google 登录" 真的工作,需要做两件事:

1. 在 Google Cloud Console 建一个 OAuth 2.0 Client
2. 在阿里云私有运行配置中把 client_id / client_secret + 几个相关 env 配上

## 1. Google Cloud Console

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)
2. 顶栏选一个项目(没有就新建一个,叫 `cybermomo` 之类)
3. 左侧菜单 → **APIs & Services** → **OAuth consent screen**
   - User Type 选 **External**(让所有 Google 账户都能登)
   - App name: `CyberMOMO`
   - User support email: 你的邮箱
   - Developer contact: 你的邮箱
   - Scopes:不用加,默认的 `openid email profile` 够了(代码里写死)
   - Test users:测试阶段可以加几个朋友邮箱(发布前 Google 限制只能 test users 登录,发布后任意账户可登)
   - 保存
4. 左侧 → **Credentials** → **+ Create Credentials** → **OAuth client ID**
   - Application type: **Web application**
   - Name: `cybermomo-prod`
   - **Authorized redirect URIs** 加:
     ```
     https://cybermomo.daydreamer.world/api/auth/google/callback
     ```
     (如果还要本地开发,再加一行 `http://localhost:8080/api/auth/google/callback`)
   - 创建后会拿到 **Client ID** 和 **Client Secret** — 复制存好

## 2. 阿里云 backend 私有环境变量

在已授权配置变更范围内维护 `/opt/cybermomo-prod/backend.env`，不要输出凭据值；以下是 OAuth 配置参考，不表示国内 Google 登录已经验收。

| 变量 | 值 | 说明 |
|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | `xxx.apps.googleusercontent.com` | 上一步拿到的 |
| `GOOGLE_OAUTH_CLIENT_SECRET` | `GOCSPX-xxx` | 上一步拿到的 |
| `GOOGLE_OAUTH_REDIRECT_URI` | `https://cybermomo.daydreamer.world/api/auth/google/callback` | 跟 Google Console 那行完全一致 |
| `WEB_BASE_URL` | `https://cybermomo.daydreamer.world` | 前端域名 |
| `JWT_SECRET` | `openssl rand -hex 32` 生成 | **必填**,session JWT 签名密钥 |
| `ENV` | `prod` | 关掉 dev mock fallback;cookie auth 唯一通路 |

## 3. 前端同域代理

浏览器使用相对 `/api`，构建时 `NEXT_PUBLIC_DEV_MOCK_AUTH=false`，服务端代理指向 Compose backend。不要重新设置已停用的 Railway API 域名。旧 Google-only 用户可使用 `/recover` 验证原邮箱并保留原账号及历史。

## 4. Google OAuth 专项验收（尚未完成）

部署完后:

- 浏览器访问 `https://cybermomo.daydreamer.world/`
- 应该看到"用 Google 登录"按钮**可点**(不再灰)、左下角 DEV banner **消失**
- 点 Google 登录 → 跳到 Google 同意页 → 选账户 → 同意 → 跳回 `/room`(老用户)或 `/onboarding`(新用户)
- 进 `/me` → 设置区 → "退出登录" 点两下 → 跳回 `/`,再访问 `/room` 应该 401 跳回登录页

## 5. dev 本地开发(不必接 OAuth)

本地起 api service 时,只要不设 `GOOGLE_OAUTH_*` 三个变量 + `ENV=dev`(默认就是),mock 头 fallback 仍然有效。前端 `NEXT_PUBLIC_DEV_MOCK_AUTH=true`(默认) 时 DEV banner 还在,你可以切 mock user 测试。

## 6. 安全提示

- `JWT_SECRET` 泄漏 = 任意伪造登录态。换的话所有用户立刻被踢下线
- `GOOGLE_OAUTH_CLIENT_SECRET` 泄漏 = 别人能假冒我们的 OAuth 客户端。Google Console 上可以 Rotate
- OAuth consent screen 发布前(Testing 状态)只有 Test Users 列表里的账户能登,Verification 通过后才放开;朋友测试期可以保留 Testing,过完体验直接加他们邮箱
