"use client"

/**
 * 头像选择 / 上传组件
 *
 * 行为:
 * - 显示当前头像(圆形 64px)。若 value 为空,用 nickname 首字母占位
 * - 「用 Google 头像」:把 googleAvatarUrl 直接当 value(没 Google 头像 → 按钮 disabled)
 * - 「上传图片」:本地选图 → canvas 压到 256×256 JPEG quality=0.85 → toDataURL
 *   → onChange(dataUrl)。压缩后 ≤ 200KB 才接受,超过 toast 提示
 *
 * 存储路径:value 直接是字符串,父组件 PUT /api/auth/me/profile 时整包提交。
 * 不需要单独的 avatar upload endpoint。
 */
import { useRef, useState } from "react"

interface AvatarUploadProps {
  value?: string | null
  onChange: (avatarUrl: string | null) => void
  /** nickname 首字母占位 */
  fallbackInitial?: string
  /** OAuth 拿到的 Google 头像 URL,没值则该按钮 disabled */
  googleAvatarUrl?: string | null
}

// 压缩参数:目标 256×256 JPEG q=0.85,大头像 ~50-80KB
const TARGET_SIZE = 256
const JPEG_QUALITY = 0.85
const MAX_BYTES = 200_000 // 跟后端 schema 对齐

export default function AvatarUpload({
  value,
  onChange,
  fallbackInitial,
  googleAvatarUrl,
}: AvatarUploadProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const showImg = !!value && (value.startsWith("data:") || value.startsWith("http"))
  const initial = (fallbackInitial || "").trim().charAt(0) || "你"

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = "" // reset 让连续选同一文件也触发 change
    if (!file) return
    if (!file.type.startsWith("image/")) {
      setError("只能上传图片")
      return
    }
    // SVG 是 XML 不是位图,canvas 渲染行为不一致 + 内嵌 <script> / 外链有安全风险
    // (虽然 <img src> 上下文多数浏览器禁脚本,但作为用户可控 data URL 不值得这个风险)
    // 后端 schemas.py 的 _ALLOWED_AVATAR_DATA_MIME 也不收 svg,这里前端先挡 UX 更友好
    if (file.type === "image/svg+xml") {
      setError("不支持 SVG,换 JPG / PNG / WebP / GIF")
      return
    }
    setError(null)
    setBusy(true)
    try {
      const dataUrl = await compressImageToDataUrl(file)
      if (dataUrl.length > MAX_BYTES) {
        setError(`图片压缩后还是太大(${(dataUrl.length / 1024).toFixed(0)}KB),换张试试`)
        return
      }
      onChange(dataUrl)
    } catch (err: any) {
      setError(err?.message || "图片处理失败")
    } finally {
      setBusy(false)
    }
  }

  function useGoogle() {
    if (googleAvatarUrl) onChange(googleAvatarUrl)
  }

  function clear() {
    onChange(null)
    setError(null)
  }

  return (
    <div>
      <div className="flex items-center gap-4">
        {/* 头像圆 */}
        <div className="w-16 h-16 rounded-full overflow-hidden flex-shrink-0 bg-gradient-to-br from-[#C7E8D5] to-primary flex items-center justify-center text-white text-[22px] font-semibold">
          {showImg ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={value!} alt="avatar" className="w-full h-full object-cover" />
          ) : (
            initial
          )}
        </div>

        {/* 按钮组 */}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={useGoogle}
            disabled={!googleAvatarUrl || busy}
            className="px-3.5 py-2 border-[1.5px] border-line rounded-md text-[13px] text-ink-secondary hover:border-ink-secondary hover:text-ink disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            用 Google 头像
          </button>
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="px-3.5 py-2 border-[1.5px] border-line rounded-md text-[13px] text-ink-secondary hover:border-ink-secondary hover:text-ink disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {busy ? "处理中…" : "上传图片"}
          </button>
          {showImg && (
            <button
              type="button"
              onClick={clear}
              disabled={busy}
              className="px-3.5 py-2 border-[1.5px] border-line rounded-md text-[13px] text-ink-tertiary hover:text-warn hover:border-warn transition"
            >
              清除
            </button>
          )}
        </div>

        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          onChange={onPick}
          className="hidden"
        />
      </div>

      {!googleAvatarUrl && (
        <p className="text-[11px] text-ink-tertiary mt-2">没用 Google 登录的就直接上传</p>
      )}
      {error && (
        <p className="text-[12px] text-warn mt-2">{error}</p>
      )}
    </div>
  )
}


/**
 * 本地把图片压到 256×256 居中 cover JPEG,返回 data URL。
 *
 * 步骤:
 *   1. FileReader.readAsDataURL → 原图 data URL
 *   2. new Image().src = dataUrl → 拿原始宽高
 *   3. canvas 256×256,drawImage 用 cover 算法(短边铺满,长边裁切)
 *   4. canvas.toDataURL("image/jpeg", 0.85)
 *
 * 浏览器不支持 canvas 或者图片解码失败时抛错。
 */
async function compressImageToDataUrl(file: File): Promise<string> {
  const reader = new FileReader()
  const rawDataUrl: string = await new Promise((resolve, reject) => {
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(new Error("读取文件失败"))
    reader.readAsDataURL(file)
  })

  const img = await new Promise<HTMLImageElement>((resolve, reject) => {
    const el = new Image()
    el.onload = () => resolve(el)
    el.onerror = () => reject(new Error("图片格式不支持或损坏"))
    el.src = rawDataUrl
  })

  const canvas = document.createElement("canvas")
  canvas.width = TARGET_SIZE
  canvas.height = TARGET_SIZE
  const ctx = canvas.getContext("2d")
  if (!ctx) throw new Error("浏览器不支持 canvas")

  // cover:短边铺满 256,长边裁中间
  const scale = Math.max(TARGET_SIZE / img.width, TARGET_SIZE / img.height)
  const sw = TARGET_SIZE / scale
  const sh = TARGET_SIZE / scale
  const sx = (img.width - sw) / 2
  const sy = (img.height - sh) / 2
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, TARGET_SIZE, TARGET_SIZE)

  return canvas.toDataURL("image/jpeg", JPEG_QUALITY)
}
