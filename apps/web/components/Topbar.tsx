"use client"

import Link from "next/link"
import { useEffect, useState } from "react"

import { api, type UserMeResponse } from "@/lib/api"

type Tab = "plaza" | "room" | "me"

const TABS: { key: Tab; label: string; href: string }[] = [
  { key: "plaza", label: "广场", href: "/plaza" },
  { key: "room", label: "个人房间", href: "/room" },
  { key: "me", label: "我", href: "/me" },
]

export default function Topbar({ active }: { active: Tab }) {
  // 之前写死 "M",上传完头像右上角不变就是这个原因。每个挂 Topbar 的页面会发 1 次
  // /api/auth/me — /me endpoint 已 selectinload profile,是轻请求,先不优化共享。
  const [me, setMe] = useState<UserMeResponse | null>(null)
  useEffect(() => {
    let cancelled = false
    api.get<UserMeResponse>("/api/auth/me")
      .then(r => { if (!cancelled) setMe(r) })
      .catch(() => { /* 未登录 / 网络断,静默 fallback 到默认 initial */ })
    return () => { cancelled = true }
  }, [])

  const avatarUrl = me?.profile?.avatar_url || me?.google_avatar_url || null
  const showImg = !!avatarUrl && (avatarUrl.startsWith("data:") || avatarUrl.startsWith("http"))
  const initial = (
    me?.profile?.nickname || me?.username || me?.google_name || "M"
  ).trim().charAt(0).toUpperCase() || "M"

  return (
    <header className="bg-bg border-b border-line-soft px-6 py-3.5 flex items-center justify-between sticky top-0 z-10">
      <Link href="/" className="font-semibold flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-primary" />
        CyberMOMO
      </Link>
      <nav className="flex gap-3">
        {TABS.map(tab => {
          const isActive = active === tab.key
          return (
            <Link
              key={tab.key}
              href={tab.href}
              className={`px-3.5 py-1.5 rounded-full text-sm transition ${
                isActive ? "bg-ink text-bg" : "text-ink-secondary hover:text-ink"
              }`}
            >
              {tab.label}
            </Link>
          )
        })}
      </nav>
      <Link
        href="/me"
        className="w-8 h-8 rounded-full overflow-hidden flex items-center justify-center text-white text-xs font-semibold bg-gradient-to-br from-[#C7E8D5] to-primary"
      >
        {showImg ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={avatarUrl!} alt="avatar" className="w-full h-full object-cover" />
        ) : (
          initial
        )}
      </Link>
    </header>
  )
}
