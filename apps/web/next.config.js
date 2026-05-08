/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // standalone 输出 — Docker 镜像更小;Railway / Vercel 都支持
  output: 'standalone',
  // 注:不再用 rewrites 反代 /api/*。
  // API client (lib/api.ts) 直接拼 NEXT_PUBLIC_API_URL,跨域走 backend CORS。
  // 这样部署时不需要前后端同域,后端可以独立 Railway service。
}

module.exports = nextConfig
