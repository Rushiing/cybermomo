/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // API 反向代理到后端(本地开发)
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8787'
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
