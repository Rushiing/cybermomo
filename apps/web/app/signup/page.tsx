"use client"

/**
 * /signup · 用户名 + 密码注册
 *
 * - username: 3-20 字符,字母数字下划线
 * - password: 8-100 字符
 * - email: 选填,不校验真实性
 * - nickname: 选填,空就用 username 占位
 *
 * 成功后写 session cookie,跳 /onboarding
 */
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { api, type RegisterRequest, type UserMeResponse } from "@/lib/api"

const USERNAME_RE = /^[a-zA-Z0-9_]+$/

export default function SignupPage() {
  const router = useRouter()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [password2, setPassword2] = useState("")
  const [email, setEmail] = useState("")
  const [nickname, setNickname] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function clientValidate(): string | null {
    if (username.length < 3 || username.length > 20) return "用户名 3-20 个字符"
    if (!USERNAME_RE.test(username)) return "用户名只能用字母数字下划线"
    if (password.length < 8) return "密码至少 8 位"
    if (password.length > 100) return "密码最多 100 位"
    if (password !== password2) return "两次输入的密码不一致"
    return null
  }

  async function submit() {
    setError(null)
    const v = clientValidate()
    if (v) {
      setError(v)
      return
    }
    setSubmitting(true)
    try {
      const body: RegisterRequest = {
        username,
        password,
        email: email.trim() || null,
        nickname: nickname.trim() || null,
      }
      await api.post<UserMeResponse, RegisterRequest>("/api/auth/register", body)
      // 注册成功 → cookie 已写,跳 onboarding
      router.push("/onboarding")
    } catch (e: any) {
      setError(e?.detail || e?.message || "注册失败")
      setSubmitting(false)
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-12 bg-gradient-to-br from-bg via-bg to-[#efe7db]">
      <Link href="/" className="absolute top-6 left-6 text-xs text-ink-secondary hover:text-ink">
        ← 返回登录
      </Link>

      <div className="flex items-center gap-3 mb-2">
        <span className="block w-3 h-3 rounded-full bg-primary" />
        <h1 className="text-2xl font-semibold tracking-tight">注册</h1>
      </div>
      <p className="text-sm text-ink-secondary text-center max-w-sm mb-7">
        不用绑 Gmail,起个用户名 + 密码就能进。
      </p>

      <div className="w-full max-w-[360px] space-y-4">
        <Field label="用户名" hint="3-20 字符 · 字母数字下划线">
          <input
            value={username}
            onChange={e => setUsername(e.target.value.trim())}
            maxLength={20}
            autoComplete="username"
            placeholder="例:senyu_2026"
            className="w-full px-3.5 py-2.5 border-[1.5px] border-line-soft rounded-md text-sm focus:outline-none focus:border-primary bg-bg-elevated"
          />
        </Field>

        <Field label="密码" hint="至少 8 位">
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            maxLength={100}
            autoComplete="new-password"
            className="w-full px-3.5 py-2.5 border-[1.5px] border-line-soft rounded-md text-sm focus:outline-none focus:border-primary bg-bg-elevated"
          />
        </Field>

        <Field label="再输一次密码">
          <input
            type="password"
            value={password2}
            onChange={e => setPassword2(e.target.value)}
            maxLength={100}
            autoComplete="new-password"
            className="w-full px-3.5 py-2.5 border-[1.5px] border-line-soft rounded-md text-sm focus:outline-none focus:border-primary bg-bg-elevated"
          />
        </Field>

        <Field label="邮箱(选填)" hint="不验证 · 之后取回密码时才需要">
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value.trim())}
            maxLength={200}
            autoComplete="email"
            placeholder="可以先不填"
            className="w-full px-3.5 py-2.5 border-[1.5px] border-line-soft rounded-md text-sm focus:outline-none focus:border-primary bg-bg-elevated"
          />
        </Field>

        <Field label="昵称(选填)" hint="留空用用户名占位,后面 onboarding 可以改">
          <input
            value={nickname}
            onChange={e => setNickname(e.target.value)}
            maxLength={20}
            placeholder="例:森屿"
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
          disabled={submitting || !username || !password || !password2}
          className="w-full bg-primary text-white py-3 rounded-md font-medium hover:bg-primary-dark disabled:opacity-40 disabled:cursor-not-allowed transition"
        >
          {submitting ? "注册中…" : "注册并进入"}
        </button>

        <p className="text-xs text-ink-tertiary text-center">
          已有账号?{" "}
          <Link href="/signin" className="text-primary-dark underline-offset-2 hover:underline">
            去登录
          </Link>
        </p>
      </div>
    </main>
  )
}

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[13px] text-ink-secondary">{label}</span>
        {hint && <span className="text-[11px] text-ink-tertiary">{hint}</span>}
      </div>
      {children}
    </div>
  )
}
