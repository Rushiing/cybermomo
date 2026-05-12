/**
 * CyberMOMO 登录页(屏 1)
 * 设计依据:cybermomo/DEMO/mvp/01-login.html
 *
 * 点 "用 Google 登录" → 跳后端 /api/auth/google/login → Google consent → 回调 → 写 cookie → 跳 /room
 */
import { Suspense } from "react"

import LoginScreen from "./LoginScreen"

export default function HomePage() {
  return (
    <Suspense fallback={null}>
      <LoginScreen />
    </Suspense>
  )
}
