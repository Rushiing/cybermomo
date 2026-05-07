/**
 * CyberMOMO 登录页(屏 1)
 * 设计依据:cybermomo/DEMO/mvp/01-login.html
 *
 * MVP 阶段 placeholder · Phase 0 后续接入 NextAuth.js + Google OAuth
 */
export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-12 bg-gradient-to-br from-bg via-bg to-[#efe7db]">
      <div className="flex items-center gap-3 mb-3">
        <div className="relative">
          <span className="block w-3.5 h-3.5 rounded-full bg-primary shadow-[0_0_0_6px_rgba(0,174,66,0.15)]" />
          <span className="absolute inset-[-6px] rounded-full border-[1.5px] border-primary opacity-40 animate-agent-pulse" />
        </div>
        <span className="text-3xl font-semibold tracking-tight">CyberMOMO</span>
      </div>

      <p className="text-base text-ink-secondary text-center max-w-sm mb-16 leading-relaxed">
        先聊的不是你。
        <br />
        让 Agent 替你做社交初筛。
      </p>

      <button
        disabled
        className="flex items-center gap-3 bg-bg-elevated border-[1.5px] border-line rounded-sm px-7 py-3.5 font-medium opacity-60 cursor-not-allowed shadow-card"
        type="button"
        title="OAuth 后续接入 — 开发期请用下方 dev 入口"
      >
        <svg viewBox="0 0 24 24" className="w-5 h-5">
          <path fill="#4285F4" d="M22.5 12.27c0-.83-.07-1.62-.2-2.39H12v4.51h5.91c-.26 1.37-1.04 2.53-2.21 3.31v2.74h3.57c2.09-1.93 3.23-4.77 3.23-8.17z"/>
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.27-2.66l-3.57-2.74c-.98.66-2.24 1.05-3.7 1.05-2.84 0-5.25-1.92-6.11-4.5H2.18v2.83C3.99 20.53 7.7 23 12 23z"/>
          <path fill="#FBBC05" d="M5.89 14.15c-.22-.66-.34-1.36-.34-2.07s.13-1.41.34-2.07V7.18H2.18C1.43 8.66 1 10.28 1 12s.43 3.34 1.18 4.82l3.71-2.67z"/>
          <path fill="#EA4335" d="M12 5.43c1.61 0 3.06.55 4.21 1.64l3.16-3.16C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.18l3.71 2.83C6.75 7.35 9.16 5.43 12 5.43z"/>
        </svg>
        用 Google 登录(待接入)
      </button>

      {/* Dev skip — Phase 1 OAuth 接入后删除 */}
      <div className="mt-6 text-center">
        <p className="text-xs text-ink-tertiary mb-3">开发模式 · OAuth 还没接</p>
        <div className="flex gap-2">
          <a href="/md/quiz" className="text-sm text-primary underline-offset-4 hover:underline">
            做问卷 →
          </a>
          <span className="text-ink-tertiary">·</span>
          <a href="/room" className="text-sm text-primary underline-offset-4 hover:underline">
            个人房间 →
          </a>
        </div>
      </div>

      <p className="fixed bottom-8 text-xs text-ink-tertiary text-center">
        点击登录即表示同意{' '}
        <a className="text-ink-secondary hover:text-ink underline-offset-2 hover:underline" href="#">
          用户协议
        </a>{' '}
        与{' '}
        <a className="text-ink-secondary hover:text-ink underline-offset-2 hover:underline" href="#">
          隐私协议
        </a>
      </p>
    </main>
  )
}
