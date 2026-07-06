/** @type {import('next').NextConfig} */
const apiProxyTarget =
  process.env.API_PROXY_TARGET ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8787'

const nextConfig = {
  reactStrictMode: true,
  // standalone 输出 — Docker 镜像更小;Railway / Vercel 都支持
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${apiProxyTarget}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
