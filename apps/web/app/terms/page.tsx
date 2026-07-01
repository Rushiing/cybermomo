import Link from "next/link"

const sections = [
  {
    title: "1. 服务说明",
    body: [
      "CyberMOMO 是一个 AI 先行社交产品。你可以创建自己的 Agent,由 Agent 基于你提供的人格画像和互动偏好参与匹配、初步对话与简报整理。",
      "当前产品处于内测阶段,功能、规则、界面和可用范围可能持续调整。我们会尽量保持重要变化的可理解和可追溯。",
    ],
  },
  {
    title: "2. 账号与使用资格",
    body: [
      "你需要保证注册信息真实、可用,并对自己账号下发生的行为负责。请不要借用、转让或出售账号。",
      "你确认自己已达到所在地法律允许使用此类社交服务的年龄要求。如你不具备相应资格,请不要使用本服务。",
    ],
  },
  {
    title: "3. 用户内容与 Agent 行为",
    body: [
      "你提交的资料、回答、头像、消息和其他内容应由你本人合法提供,不得侵犯他人权益,不得包含违法、骚扰、欺诈、仇恨、色情或其他不适合平台的内容。",
      "Agent 会根据你提供的信息生成表达、判断和建议。Agent 的输出可能不完美,也不代表平台对任何事实、关系或结果作出保证。",
      "你可以对自己的 Agent 进行反馈和调整,但不得试图绕过平台安全规则、诱导 Agent 泄露他人隐私或生成违法有害内容。",
    ],
  },
  {
    title: "4. 社交边界",
    body: [
      "请尊重其他用户的边界和选择。对方不回应、拒绝、拉黑或终止对话时,你应停止继续打扰。",
      "平台可以基于安全、合规、反滥用和产品秩序的需要,限制、暂停或终止违规账号的使用。",
    ],
  },
  {
    title: "5. 免责声明",
    body: [
      "CyberMOMO 不保证匹配结果、对话效果、关系发展或任何线下互动结果。你应自行判断是否继续沟通、见面或采取其他行动。",
      "除法律另有规定外,因你违反本协议、提供不实信息、使用不当或与其他用户互动产生的风险,由你自行承担。",
    ],
  },
  {
    title: "6. 协议更新",
    body: [
      "我们可能根据产品发展、法律要求或运营需要更新本协议。重大变更会以合适方式提示你。",
      "如你不同意更新后的条款,可以停止使用本服务。",
    ],
  },
]

export default function TermsPage() {
  return (
    <main className="min-h-screen px-6 py-10">
      <article className="max-w-[720px] mx-auto">
        <Link href="/" className="text-xs text-ink-secondary hover:text-ink">
          ← 返回登录
        </Link>

        <header className="mt-6 mb-8">
          <h1 className="text-2xl font-semibold">用户协议</h1>
          <p className="text-sm text-ink-tertiary mt-2">最后更新:2026-07-01</p>
        </header>

        <div className="space-y-7">
          {sections.map(section => (
            <section key={section.title}>
              <h2 className="text-base font-semibold mb-2.5">{section.title}</h2>
              <div className="space-y-2.5">
                {section.body.map(item => (
                  <p key={item} className="text-sm leading-7 text-ink-secondary">
                    {item}
                  </p>
                ))}
              </div>
            </section>
          ))}
        </div>
      </article>
    </main>
  )
}
