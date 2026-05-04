import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  allowedDevOrigins: ["192.168.37.195", '192.168.29.222'],
};

export default nextConfig;
