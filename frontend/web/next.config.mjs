/** @type {import("next").NextConfig} */
const backendBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendBase.replace(/\/$/, "")}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

