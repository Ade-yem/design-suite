import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  turbopack: {

  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:5000/api/:path*",
      },
      {
        source: "/auth/:path*",
        destination: "http://127.0.0.1:5000/auth/:path*",
      },
      {
        source: "/users/:path*",
        destination: "http://127.0.0.1:5000/users/:path*",
      },
    ];
  },
};

export default nextConfig;
