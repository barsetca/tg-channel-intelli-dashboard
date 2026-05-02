import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // Не задаём outputFileTracingRoot: в Docker build context = только apps/web, иначе
  // standalone окажется вложенным (server.js не в корне) и образ сломается.
};

export default nextConfig;
