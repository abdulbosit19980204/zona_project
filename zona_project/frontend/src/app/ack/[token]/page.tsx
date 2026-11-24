import type { Metadata, Viewport } from "next";
import { Suspense } from "react";

import { AckPublicPage } from "@/components/inventory/ack-public";

export const metadata: Metadata = { title: "Qurilmalarni tasdiqlash · StarGroup", robots: { index: false, follow: false } };
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#4f46e5" };

/** Xodim uchun ochiq sahifa (loginsiz): unga biriktirilgan qurilmalarni ko'rib, imzo bilan tasdiqlaydi. */
export default function Page() {
  return (
    <Suspense fallback={<div className="h-full bg-background" />}>
      <AckPublicPage />
    </Suspense>
  );
}
