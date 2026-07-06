"use client"

/**
 * 登录页 client 部分(需要 useSearchParams 看 ?auth_error= 错误,所以单独抽出来)
 *
 * 卡片式布局(参考 Qwen):
 * - 用户名 + 密码内嵌(原 /signin 入口收编到这里)
 * - Google 登录在分割线下方(平级备选)
 * - "注册"链接跳 /signup(注册流程仍单独一页 — 字段多)
 * - /signin 路由仍保留为兼容入口
 */
import { useRouter, useSearchParams } from "next/navigation"
import { useState, type KeyboardEvent } from "react"

import { api, isDevMockAuth, type LoginRequest, type UserMeResponse } from "@/lib/api"

const BASE = process.env.NEXT_PUBLIC_API_CLIENT_BASE || ""

const AUTH_ERROR_LABEL: Record<string, string> = {
  state_mismatch: "登录会话过期了,请重试。",
  token_exchange_failed: "Google 通信失败,请重试。",
  no_id_token: "Google 没给我们 id_token,可能是 OAuth 配置不全。",
  id_token_decode_failed: "Google 返回的 token 解不开,请重试。",
  incomplete_id_token: "Google 返回的 token 缺关键字段。",
  missing_code_or_state: "登录回调缺参数。",
  access_denied: "你拒绝了授权 — 没事,下次想登再点。",
}

export default function LoginScreen() {
  const router = useRouter()
  const sp = useSearchParams()
  const authError = sp.get("auth_error")
  const initialError = authError
    ? (AUTH_ERROR_LABEL[authError] || `登录失败:${authError}`)
    : null

  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(initialError)

  const loginUrl = `${BASE}/api/auth/google/login`
  const showDev = isDevMockAuth()
  const canSubmit = !!username.trim() && !!password && !submitting

  async function submit() {
    setError(null)
    if (!canSubmit) return
    setSubmitting(true)
    try {
      const me = await api.post<UserMeResponse, LoginRequest>(
        "/api/auth/login",
        { username: username.trim(), password },
      )
      router.push(me.onboarded_at ? "/room" : "/onboarding")
    } catch (e: any) {
      setError(e?.detail || e?.message || "登录失败")
      setSubmitting(false)
    }
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") void submit()
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-10 bg-gradient-to-br from-bg via-bg to-[#efe7db]">
      {/* 顶部品牌 */}
      <div className="flex items-center gap-2.5 mb-2">
        <div className="relative">
          <span className="block w-3 h-3 rounded-full bg-primary shadow-[0_0_0_5px_rgba(0,174,66,0.15)]" />
          <span className="absolute inset-[-5px] rounded-full border-[1.5px] border-primary opacity-40 animate-agent-pulse" />
        </div>
        <span className="text-2xl font-semibold tracking-tight">CyberMOMO</span>
      </div>
      <p className="text-sm text-ink-secondary mb-7 text-center">
        先聊的不是你 · 让 Agent 替你做社交初筛
      </p>

      {/* 登录卡片 */}
      <div className="w-full max-w-[420px] bg-bg-elevated rounded-lg shadow-modal border border-line-soft px-7 py-7">
        <h1 className="text-xl font-semibold text-center mb-6">登录到 CyberMOMO</h1>

        {/* 用户名 */}
        <div className="relative mb-3">
          <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-tertiary pointer-events-none">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </span>
          <input
            value={username}
            onChange={e => setUsername(e.target.value.trim())}
            onKeyDown={onKey}
            placeholder="输入您的用户名"
            maxLength={20}
            autoComplete="username"
            autoFocus
            className="w-full pl-10 pr-3.5 py-3 bg-bg rounded-md border border-line-soft text-sm focus:outline-none focus:border-primary transition"
          />
        </div>

        {/* 密码 */}
        <div className="relative">
          <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-tertiary pointer-events-none">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
          </span>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={onKey}
            placeholder="输入您的密码"
            maxLength={100}
            autoComplete="current-password"
            className="w-full pl-10 pr-3.5 py-3 bg-bg rounded-md border border-line-soft text-sm focus:outline-none focus:border-primary transition"
          />
        </div>

        {error && (
          <div className="mt-3 bg-warn-soft text-warn px-3 py-2 rounded-md text-xs leading-relaxed">
            {error}
          </div>
        )}

        {/* 登录按钮 */}
        <button
          onClick={submit}
          disabled={!canSubmit}
          className="w-full mt-5 py-3 rounded-md font-medium text-sm bg-primary text-white hover:bg-primary-dark disabled:bg-line disabled:text-ink-tertiary disabled:cursor-not-allowed transition"
        >
          {submitting ? "登录中…" : "登录"}
        </button>

        <p className="text-xs text-ink-tertiary text-center mt-3.5">
          没有账号?{" "}
          <a href="/signup" className="text-primary-dark hover:underline underline-offset-2">
            注册
          </a>
        </p>

        {/* 分割线 */}
        <div className="flex items-center gap-3 my-5">
          <div className="flex-1 h-px bg-line-soft" />
          <span className="text-xs text-ink-tertiary">或</span>
          <div className="flex-1 h-px bg-line-soft" />
        </div>

        {/* Google 登录 */}
        <a
          href={loginUrl}
          className="flex items-center justify-center gap-2.5 w-full py-3 rounded-md bg-bg border border-line-soft hover:border-ink-tertiary text-sm font-medium transition"
        >
          <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]">
            <path fill="#4285F4" d="M22.5 12.27c0-.83-.07-1.62-.2-2.39H12v4.51h5.91c-.26 1.37-1.04 2.53-2.21 3.31v2.74h3.57c2.09-1.93 3.23-4.77 3.23-8.17z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.27-2.66l-3.57-2.74c-.98.66-2.24 1.05-3.7 1.05-2.84 0-5.25-1.92-6.11-4.5H2.18v2.83C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.89 14.15c-.22-.66-.34-1.36-.34-2.07s.13-1.41.34-2.07V7.18H2.18C1.43 8.66 1 10.28 1 12s.43 3.34 1.18 4.82l3.71-2.67z"/>
            <path fill="#EA4335" d="M12 5.43c1.61 0 3.06.55 4.21 1.64l3.16-3.16C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.18l3.71 2.83C6.75 7.35 9.16 5.43 12 5.43z"/>
          </svg>
          继续使用 Google 登录
        </a>
      </div>

      {showDev && (
        <div className="mt-5 text-center">
          <p className="text-xs text-ink-tertiary mb-2">开发模式 · 跳过 OAuth 直接走流程</p>
          <div className="flex justify-center gap-2">
            <a href="/onboarding" className="text-xs text-primary font-medium border border-primary px-3 py-1.5 rounded-full hover:bg-primary-soft transition">
              从 Onboarding 开始
            </a>
            <a href="/md/quiz" className="text-xs text-ink-secondary border border-line-soft px-3 py-1.5 rounded-full hover:border-ink-secondary transition">
              直接答题
            </a>
            <a href="/room" className="text-xs text-ink-secondary border border-line-soft px-3 py-1.5 rounded-full hover:border-ink-secondary transition">
              进个人房间
            </a>
          </div>
        </div>
      )}

      <p className="mt-7 text-xs text-ink-tertiary text-center max-w-sm">
        登录即表示同意{' '}
        <a className="text-ink-secondary hover:text-ink underline-offset-2 hover:underline" href="/terms">
          用户协议
        </a>
        {' '}与{' '}
        <a className="text-ink-secondary hover:text-ink underline-offset-2 hover:underline" href="/privacy">
          隐私政策
        </a>
      </p>
    </main>
  )
}
