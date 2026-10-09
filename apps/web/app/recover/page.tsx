"use client"

import { useState } from "react"
import Link from "next/link"
import { api, ApiError } from "@/lib/api"

export default function RecoverPage() {
  const [email, setEmail] = useState("")
  const [token, setToken] = useState("")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [notice, setNotice] = useState("")
  const [busy, setBusy] = useState(false)

  async function submit(confirm: boolean) {
    setBusy(true)
    setNotice("")
    try {
      if (confirm) {
        await api.post("/api/auth/email-claim/confirm", { email: email.trim(), token: token.trim(), username: username.trim(), password })
        window.location.assign("/room")
      } else {
        const result = await api.post<{ detail: string }>("/api/auth/email-claim/request", { email: email.trim() })
        setNotice(result.detail)
      }
    } catch (error) {
      setNotice(error instanceof ApiError ? error.detail : "请求失败，请稍后重试")
    } finally {
      setBusy(false)
    }
  }

  const inputClass = "w-full border border-line rounded-md p-3 bg-bg-elevated"
  return (
    <main className="max-w-md mx-auto px-6 py-12 space-y-5">
      <h1 className="text-2xl font-semibold">找回旧 Google 账号</h1>
      <p className="text-sm text-ink-secondary">填写原 Google 邮箱，验证后为原账号设置用户名和密码。个人资料、匹配和聊天记录都会保留。已有用户名和密码的账号请直接登录。</p>
      <label className="block">原 Google 邮箱
        <input className={inputClass} type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} />
      </label>
      <button className="text-primary-dark underline disabled:opacity-40" disabled={busy || !email.trim()} onClick={() => submit(false)}>发送验证邮件</button>
      <form className="space-y-4" onSubmit={e => { e.preventDefault(); submit(true) }}>
        <label className="block">邮件中的验证口令
          <input className={inputClass} required value={token} autoComplete="off" onChange={e => setToken(e.target.value)} />
        </label>
        <label className="block">设置登录用户名
          <input className={inputClass} required minLength={3} maxLength={20} pattern="[a-zA-Z0-9_]+" autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} />
          <span className="text-xs text-ink-secondary">3–20 位字母、数字或下划线</span>
        </label>
        <label className="block">设置密码
          <input className={inputClass} type="password" required minLength={8} maxLength={100} autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} />
        </label>
        <button disabled={busy} className="w-full bg-primary text-white py-3 rounded-md disabled:opacity-40">{busy ? "处理中…" : "验证并登录原账号"}</button>
      </form>
      {notice && <p role="status" className="text-sm">{notice}</p>}
      <Link href="/signin" className="text-primary-dark">返回登录</Link>
    </main>
  )
}
