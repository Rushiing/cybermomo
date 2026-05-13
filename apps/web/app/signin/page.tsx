"use client"

/**
 * /signin · 用户名 + 密码登录
 *
 * 成功后写 session cookie,根据 onboarded_at 跳 /room 或 /onboarding
 */
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { api, type LoginRequest, type UserMeResponse } from "@/lib/api"

export default function SigninPage() {
  const router = useRouter()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setError(null)
    if (!username.trim() || !password) {
      setError("用户名和密码都得填")
      return
    }
    setSubmitting(true)
    try {
      const me = await api.post<UserMeResponse, LoginRequest>(
        "/api/auth/login",
        { username: username.trim(), password },
      )
      // 已 onboard 跳 room,没 onboard 跳 onboarding
      router.push(me.onboarded_at ? "/room" : "/onboarding")
    } catch (e: any) {
      setError(e?.detail || e?.message || "登录失败")
      setSubmitting(false)
    }
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") void submit()
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-12 bg-gradient-to-br from-bg via-bg to-[#efe7db]">
      <Link href="/" className="absolute top-6 left-6 text-xs text-ink-secondary hover:text-ink">
        ← 返回
      </Link>

      <div className="flex items-center gap-3 mb-2">
        <span className="block w-3 h-3 rounded-full bg-primary" />
        <h1 className="text-2xl font-semibold tracking-tight">登录</h1>
      </div>
      <p className="text-sm text-ink-secondary mb-7">用户名 + 密码</p>

      <div className="w-full max-w-[360px] space-y-4">
        <Field label="用户名">
          <input
            value={username}
            onChange={e => setUsername(e.target.value.trim())}
            onKeyDown={onKey}
            maxLength={20}
            autoComplete="username"
            autoFocus
            className="w-full px-3.5 py-2.5 border-[1.5px] border-line-soft rounded-md text-sm focus:outline-none focus:border-primary bg-bg-elevated"
          />
        </Field>

        <Field label="密码">
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={onKey}
            maxLength={100}
            autoComplete="current-password"
            className="w-full px-3.5 py-2.5 border-[1.5px] border-line-soft rounded-md text-sm focus:outline-none focus:border-primary bg-bg-elevated"
          />
        </Field>

        {error && (
          <div className="bg-warn-soft text-warn px-3.5 py-2 rounded-md text-sm">
            {error}
          </div>
        )}

        <button
          onClick={submit}
          disabled={submitting || !username.trim() || !password}
          className="w-full bg-primary text-white py-3 rounded-md font-medium hover:bg-primary-dark disabled:opacity-40 disabled:cursor-not-allowed transition"
        >
          {submitting ? "登录中…" : "登录"}
        </button>

        <p className="text-xs text-ink-tertiary text-center">
          还没账号?{" "}
          <Link href="/signup" className="text-primary-dark underline-offset-2 hover:underline">
            去注册
          </Link>
        </p>
      </div>
    </main>
  )
}

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div>
      <div className="text-[13px] text-ink-secondary mb-1">{label}</div>
      {children}
    </div>
  )
}
