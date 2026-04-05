import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  rewrites: async () => [
    {
      source: "/api/:path*",
      destination: `${process.env.BACKEND_URL}/api/:path*`,
    },
  ],
  allowedDevOrigins: [process.env.NGROK_DOMAIN || ""],
};

export default nextConfig;
