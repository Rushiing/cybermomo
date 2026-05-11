"use client"

/**
 * 顶部柔和提示条 · 替代 alert() / 错误冒泡
 *
 * 用法:
 *   const [notice, setNotice] = useState<string | null>(null)
 *   <Toast message={notice} onClose={() => setNotice(null)} />
 *
 *   // 触发提示
 *   setNotice("已丢。这个人以后不会再被推给你。")
 *
 * 5 秒自动消失;variant='warn' 用红色背景。
 */
import { useEffect } from "react"

interface Props {
  message: string | null
  onClose: () => void
  variant?: "info" | "warn"
  /** 自动消失毫秒数,0 = 不自动消失 */
  autoDismissMs?: number
}

export default function Toast({
  message,
  onClose,
  variant = "info",
  autoDismissMs = 5000,
}: Props) {
  useEffect(() => {
    if (!message || autoDismissMs <= 0) return
    const t = setTimeout(onClose, autoDismissMs)
    return () => clearTimeout(t)
  }, [message, autoDismissMs, onClose])

  if (!message) return null

  const colorClass =
    variant === "warn"
      ? "bg-warn text-bg"
      : "bg-ink text-bg"

  return (
    <div
      className={`fixed top-20 left-1/2 -translate-x-1/2 z-50 ${colorClass} px-4 py-3 rounded-md text-sm shadow-modal animate-fade-in max-w-[640px]`}
      onClick={onClose}
      role="status"
    >
      {message}
    </div>
  )
}
