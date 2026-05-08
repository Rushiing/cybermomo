"use client"

import Link from "next/link"

type Tab = "plaza" | "room" | "me"

const TABS: { key: Tab; label: string; href: string }[] = [
  { key: "plaza", label: "广场", href: "/plaza" },
  { key: "room", label: "个人房间", href: "/room" },
  { key: "me", label: "我", href: "/me" },
]

export default function Topbar({ active }: { active: Tab }) {
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
      <Link href="/me" className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold bg-gradient-to-br from-[#C7E8D5] to-primary">M</Link>
    </header>
  )
}
