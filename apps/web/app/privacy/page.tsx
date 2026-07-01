import Link from "next/link"

const sections = [
  {
    title: "1. 我们收集的信息",
    body: [
      "为了提供服务,我们会收集你注册和使用过程中主动提供的信息,包括用户名、邮箱、昵称、头像、基础资料、问卷回答、人格画像、聊天内容、决策记录和反馈。",
      "我们也会收集必要的技术信息,例如登录状态、设备与浏览器信息、请求日志、错误日志和基础使用记录,用于安全、排障和产品改进。",
    ],
  },
  {
    title: "2. 信息如何被使用",
    body: [
      "我们使用你的信息来完成账号登录、创建 Agent、生成个人画像、运行匹配、支持 Agent 互聊、生成简报、提供真人聊天和维护服务安全。",
      "我们也可能基于聚合或脱敏后的数据分析产品质量,例如排查失败链路、理解功能使用情况和改进推荐体验。",
    ],
  },
  {
    title: "3. 人格画像与隐私边界",
    body: [
      "你的完整人格画像和原始回答不会全文展示给其他用户。面向他人的场景只会使用昵称、脱敏摘要、话题钩子或 Agent 基于画像生成的表达。",
      "其他用户不会看到你的完整内部信号、私有判断或仅供你本人查看的 Agent 简报内容。",
    ],
  },
  {
    title: "4. 信息共享",
    body: [
      "我们不会出售你的个人信息。为提供服务所必需时,我们可能将必要数据提供给基础设施、数据库、日志、错误监控或大模型服务供应商处理。",
      "如法律法规、监管要求、司法程序或保护用户安全所必需,我们可能依法保存或披露相关信息。",
    ],
  },
  {
    title: "5. 数据保存与安全",
    body: [
      "我们会在实现服务目的所需的期限内保存数据,并采取合理的技术和管理措施保护数据安全。",
      "互联网服务无法保证绝对安全。若发生可能影响你权益的安全事件,我们会按照适用要求进行处理和通知。",
    ],
  },
  {
    title: "6. 你的选择",
    body: [
      "你可以在产品内查看和更新部分资料。对于账号注销、数据导出、删除或其他隐私请求,内测阶段可通过平台提供的联系方式向我们提出。",
      "如果你不同意本政策,请停止使用本服务。",
    ],
  },
]

export default function PrivacyPage() {
  return (
    <main className="min-h-screen px-6 py-10">
      <article className="max-w-[720px] mx-auto">
        <Link href="/" className="text-xs text-ink-secondary hover:text-ink">
          ← 返回登录
        </Link>

        <header className="mt-6 mb-8">
          <h1 className="text-2xl font-semibold">隐私政策</h1>
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
