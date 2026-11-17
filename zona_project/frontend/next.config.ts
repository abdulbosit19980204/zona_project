import type { NextConfig } from "next";

/** Django backend manzili. Brauzer /api/... ga murojaat qiladi, Next.js uni backendga yo'naltiradi (CORS kerak emas). */
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
/** QR Drive mikroservisi (FastAPI). Alohida jarayon — ishlamasa ham Zona sahifalari ishlayveradi. */
const QRDRIVE_URL = process.env.QRDRIVE_URL ?? "http://127.0.0.1:8100";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Django API manzillari "/" bilan tugaydi — Next.js ularni qayta yo'naltirmasin
  skipTrailingSlashRedirect: true,
  async rewrites() {
    // ":path*" oxirgi "/" ni olib tashlaydi; Django esa "/" li manzilga qayta yo'naltiradi → cheksiz halqa.
    // Shuning uchun "/" bilan tugaydigan so'rovlar alohida qoida bilan "/" saqlangan holda uzatiladi.
    return [
      { source: "/api/:path*/", destination: `${BACKEND_URL}/api/:path*/` },
      { source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` },
      { source: "/qrdrive/:path*", destination: `${QRDRIVE_URL}/qrdrive/:path*` },
    ];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
