import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Playwright는 번들하지 않고 런타임에 node_modules에서 로드(lazy import). 스크래퍼 fallback 전용.
  serverExternalPackages: ["playwright"],
};

export default nextConfig;
