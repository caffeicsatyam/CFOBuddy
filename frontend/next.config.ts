import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  allowedDevOrigins: ["192.168.37.195", '192.168.29.222','192.168.17.9','10.68.226.229'],
};

export default nextConfig;
