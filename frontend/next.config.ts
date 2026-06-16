import os from "node:os";
import type { NextConfig } from "next";

function privateLanOrigins(): string[] {
  const allowed = new Set(["localhost", "127.0.0.1"]);
  const interfaces = os.networkInterfaces();

  for (const addresses of Object.values(interfaces)) {
    for (const address of addresses ?? []) {
      if (address.internal || address.family !== "IPv4") continue;
      if (
        address.address.startsWith("10.") ||
        address.address.startsWith("192.168.") ||
        /^172\.(1[6-9]|2\d|3[0-1])\./.test(address.address)
      ) {
        allowed.add(address.address);
      }
    }
  }

  return Array.from(allowed);
}

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  allowedDevOrigins: privateLanOrigins(),
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
