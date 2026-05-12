"use client"

/**
 * 屏 6 · .md 创建 - 基础信息
 *
 * 用户填:头像 / 昵称 / 年龄段 / 性别 / MBTI
 * → PUT /api/auth/me/profile
 * → 跳 /md/quiz
 */
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import MbtiPicker from "@/components/MbtiPicker"
import { api, type UpsertProfileRequest, type UserMeResponse } from "@/lib/api"

const AGE_OPTIONS = ["18-25", "25-30", "30-35", "35-40", "40+"] as const
const GENDER_OPTIONS = [
  { val: "female", label: "女" },
  { val: "male", label: "男" },
  { val: "non_binary", label: "非二元" },
  { val: "prefer_not_to_say", label: "不愿透露" },
] as const

export default function MdBasicPage() {
  const router = useRouter()
  const [nickname, setNickname] = useState("MOMO")
  const [ageBand, setAgeBand] = useState<string>("25-30")
  const [gender, setGender] = useState<string>("male")
  // MBTI:null = 不知道或没填全;"INFJ" 之类完整串才会保存
  const [mbti, setMbti] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // 拉旧 profile 预填
    api.get<UserMeResponse>("/api/auth/me").then(me => {
      if (me.profile) {
        setNickname(me.profile.nickname)
        if (me.profile.age_band) setAgeBand(me.profile.age_band)
        if (me.profile.gender) setGender(me.profile.gender)
        if (me.profile.mbti) setMbti(me.profile.mbti)
      }
    }).catch(() => { /* 没有就用默认 */ })
  }, [])

  async function submit() {
    if (!nickname.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const body: UpsertProfileRequest = {
        profile: {
          nickname: nickname.trim(),
          age_band: ageBand,
          gender: gender,
          mbti: mbti || undefined,
        },
      }
      await api.put("/api/auth/me/profile", body)
      router.push("/md/quiz")
    } catch (e: any) {
      setError(e?.detail || e?.message || "保存失败")
      setSubmitting(false)
    }
  }

  const initial = nickname.trim().charAt(0) || "你"

  return (
    <div className="min-h-screen flex flex-col">
      {/* Step bar */}
      <div className="px-8 py-6 border-b border-line-soft">
        <div className="max-w-[720px] mx-auto flex items-center gap-4">
          <span className="bg-primary text-white w-[22px] h-[22px] rounded-full flex items-center justify-center text-xs font-semibold">
            1
          </span>
          <span className="text-[13px] text-ink-secondary">
            <strong className="text-ink font-medium">基础信息</strong> · 接下来还有 <strong className="text-ink font-medium">问卷</strong> · <strong className="text-ink font-medium">生成</strong>
          </span>
        </div>
      </div>

      <main className="flex-1 max-w-[540px] w-full mx-auto px-8 pt-12 pb-32">
        <h1 className="text-2xl font-semibold mb-2">先互相认识下</h1>
        <p className="text-ink-secondary mb-9">
          这些信息会显示给其他用户。<strong className="text-ink">.md 是另一回事</strong> — 那个只给你的 Agent 看。
        </p>

        {/* 头像 */}
        <Field label="头像">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full flex items-center justify-center text-white text-[22px] font-semibold flex-shrink-0 bg-gradient-to-br from-[#C7E8D5] to-primary">
              {initial}
            </div>
            <div className="flex gap-2">
              <button className="px-3.5 py-2 border-[1.5px] border-line rounded-md text-[13px] text-ink-secondary hover:border-ink-secondary hover:text-ink transition" disabled>
                用 Google 头像
              </button>
              <button className="px-3.5 py-2 border-[1.5px] border-line rounded-md text-[13px] text-ink-secondary hover:border-ink-secondary hover:text-ink transition" disabled>
                上传图片
              </button>
            </div>
          </div>
          <p className="text-[11px] text-ink-tertiary mt-2">头像上传 OAuth 接入后启用</p>
        </Field>

        {/* 昵称 */}
        <Field label={<>昵称 <span className="text-primary">*</span></>}>
          <input
            value={nickname}
            onChange={e => setNickname(e.target.value)}
            maxLength={20}
            placeholder="比如:森屿、雨季的鱼……"
            className="w-full px-3.5 py-3 border-[1.5px] border-line-soft rounded-md text-[14.5px] outline-none focus:border-primary transition bg-bg-elevated"
          />
        </Field>

        {/* 年龄段 */}
        <Field label={<>年龄段 <span className="text-primary">*</span></>}>
          <ChipsRow
            options={AGE_OPTIONS.map(a => ({ val: a, label: a }))}
            value={ageBand}
            onChange={setAgeBand}
          />
        </Field>

        {/* 性别 */}
        <Field label="性别">
          <ChipsRow
            options={GENDER_OPTIONS as any}
            value={gender}
            onChange={setGender}
          />
        </Field>

        {/* MBTI · 四维各选一,自由组合 */}
        <Field label="MBTI(可选)">
          <MbtiPicker value={mbti} onChange={setMbti} />
        </Field>

        {error && (
          <div className="mt-4 px-4 py-3 bg-warn-soft text-warn text-sm rounded-md">{error}</div>
        )}
      </main>

      {/* footer */}
      <footer className="fixed bottom-0 left-0 right-0 bg-bg border-t border-line-soft px-8 py-4">
        <div className="max-w-[540px] mx-auto flex items-center justify-between">
          <button onClick={() => router.back()} className="text-sm text-ink-secondary hover:text-ink transition">
            ← 上一步
          </button>
          <button
            onClick={submit}
            disabled={!nickname.trim() || submitting}
            className="bg-primary text-white px-7 py-3 rounded-full font-medium hover:bg-primary-dark disabled:bg-line disabled:text-ink-tertiary disabled:cursor-not-allowed transition"
          >
            {submitting ? "保存中…" : "下一步:做问卷"}
          </button>
        </div>
      </footer>
    </div>
  )
}

function Field({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <div className="text-[13px] text-ink-secondary mb-2">{label}</div>
      {children}
    </div>
  )
}

function ChipsRow<T extends string>(p: {
  options: { val: T; label: string }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {p.options.map(o => (
        <button
          key={o.val}
          onClick={() => p.onChange(o.val)}
          className={`px-4 py-2 rounded-full border-[1.5px] text-[13.5px] transition font-[inherit] ${
            o.val === p.value
              ? "bg-primary-soft border-primary text-primary-dark font-medium"
              : "bg-bg-elevated border-line-soft text-ink hover:border-ink-secondary"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

