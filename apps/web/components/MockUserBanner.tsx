"use client"

/**
 * 开发期 Mock User 切换条 — 浮在顶部
 *
 * Phase 1+ OAuth 接入后删掉这个组件。
 */
import { useEffect, useState } from "react"

import { getMockUserId, setMockUserId } from "@/lib/api"

export default function MockUserBanner() {
  const [mounted, setMounted] = useState(false)
  const [uid, setUid] = useState("1")

  useEffect(() => {
    setMounted(true)
    setUid(getMockUserId())
  }, [])

  if (!mounted) return null

  function pick(newId: string) {
    setMockUserId(newId)
    setUid(newId)
    // refresh page to re-fetch with new user
    window.location.reload()
  }

  return (
    <div className="fixed bottom-3 left-3 z-50 bg-ink/85 backdrop-blur text-bg px-3 py-2 rounded-md text-xs flex items-center gap-2 shadow-lg">
      <span className="opacity-70">DEV mock user:</span>
      <strong className="font-semibold">{uid}</strong>
      <span className="opacity-50">|</span>
      {[1, 2, 3, 4, 5].map(n => (
        <button
          key={n}
          onClick={() => pick(String(n))}
          className={`px-2 py-0.5 rounded transition ${
            String(n) === uid ? "bg-primary text-white" : "hover:bg-bg/20"
          }`}
        >
          {n}
        </button>
      ))}
    </div>
  )
}
