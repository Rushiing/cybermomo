"use client"

/**
 * MBTI 选择器:四个维度块,每维二选一 + 不知道 checkbox
 *
 * 用法:
 *   const [mbti, setMbti] = useState<string | null>(...) // "INFJ" | null
 *   <MbtiPicker value={mbti} onChange={setMbti} />
 *
 * value=null 表示用户选了"不知道"或还没填全;onChange 只在 4 维都齐时给完整串,
 * 否则给 null。
 */
import { useEffect, useState } from "react"

const DIMS = [
  { key: "ei", label: "内向 / 外向", a: "I", aLabel: "I · 偏内向", b: "E", bLabel: "E · 偏外向" },
  { key: "ns", label: "直觉 / 实感", a: "N", aLabel: "N · 直觉型",  b: "S", bLabel: "S · 实感型" },
  { key: "tf", label: "理智 / 感受", a: "T", aLabel: "T · 理智型",  b: "F", bLabel: "F · 感受型" },
  { key: "jp", label: "计划 / 灵活", a: "J", aLabel: "J · 计划型",  b: "P", bLabel: "P · 灵活型" },
] as const

export function isValidMbti(s: string | null | undefined): boolean {
  return !!s && /^[IE][NS][TF][JP]$/.test(s)
}

interface Props {
  value: string | null
  onChange: (v: string | null) => void
}

export default function MbtiPicker({ value, onChange }: Props) {
  const [ei, setEi] = useState<string>(value && isValidMbti(value) ? value[0] : "")
  const [ns, setNs] = useState<string>(value && isValidMbti(value) ? value[1] : "")
  const [tf, setTf] = useState<string>(value && isValidMbti(value) ? value[2] : "")
  const [jp, setJp] = useState<string>(value && isValidMbti(value) ? value[3] : "")
  // 默认不勾选「不知道 / 不想填」— 让用户主动选(之前从 value=null 推断成勾选会
  // 把维度选项一并灰掉,用户上来就以为不能选)
  const [unknown, setUnknown] = useState<boolean>(false)

  // value prop 变化时同步内部 state(用于外部 reset)
  // 只在 value 是完整 MBTI 时同步,value=null 不动 unknown — 由用户控制
  useEffect(() => {
    if (isValidMbti(value)) {
      setEi(value![0])
      setNs(value![1])
      setTf(value![2])
      setJp(value![3])
      setUnknown(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  const composed = unknown ? "" : `${ei}${ns}${tf}${jp}`
  const complete = !unknown && isValidMbti(composed)

  // 任何变化都汇报给父:complete → composed,否则 null
  useEffect(() => {
    onChange(complete ? composed : null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ei, ns, tf, jp, unknown])

  return (
    <div>
      <div className={`space-y-2.5 ${unknown ? "opacity-40 pointer-events-none" : ""}`}>
        <Dim label="内向 / 外向" dim={DIMS[0]} value={ei} onChange={setEi} />
        <Dim label="直觉 / 实感" dim={DIMS[1]} value={ns} onChange={setNs} />
        <Dim label="理智 / 感受" dim={DIMS[2]} value={tf} onChange={setTf} />
        <Dim label="计划 / 灵活" dim={DIMS[3]} value={jp} onChange={setJp} />
      </div>
      <label className="mt-3 flex items-center gap-2 text-[13px] text-ink-secondary cursor-pointer select-none">
        <input
          type="checkbox"
          checked={unknown}
          onChange={e => setUnknown(e.target.checked)}
          className="w-4 h-4"
        />
        <span>不知道 / 不想填</span>
      </label>
      {!unknown && composed.length > 0 && composed.length < 4 && (
        <p className="text-[11px] text-ink-tertiary mt-2">
          当前 <strong>{composed}</strong> — 再选 {4 - composed.length} 个维度就齐了
        </p>
      )}
      {complete && (
        <p className="text-[11px] text-primary-dark mt-2">
          ✓ <strong>{composed}</strong>
        </p>
      )}
    </div>
  )
}

function Dim(p: {
  label: string
  dim: { a: string; aLabel: string; b: string; bLabel: string }
  value: string
  onChange: (v: string) => void
}) {
  const { a, aLabel, b, bLabel } = p.dim
  const toggle = (v: string) => p.onChange(p.value === v ? "" : v)
  return (
    <div className="flex items-center gap-3">
      <span className="text-[11.5px] text-ink-tertiary w-[60px] flex-shrink-0">{p.label}</span>
      <div className="grid grid-cols-2 gap-2 flex-1">
        <button
          onClick={() => toggle(a)}
          className={`px-3 py-2.5 rounded-md border-[1.5px] text-[13px] transition font-[inherit] ${
            p.value === a
              ? "bg-primary-soft border-primary text-primary-dark font-medium"
              : "bg-bg-elevated border-line-soft text-ink hover:border-ink-secondary"
          }`}
        >
          {aLabel}
        </button>
        <button
          onClick={() => toggle(b)}
          className={`px-3 py-2.5 rounded-md border-[1.5px] text-[13px] transition font-[inherit] ${
            p.value === b
              ? "bg-primary-soft border-primary text-primary-dark font-medium"
              : "bg-bg-elevated border-line-soft text-ink hover:border-ink-secondary"
          }`}
        >
          {bLabel}
        </button>
      </div>
    </div>
  )
}
