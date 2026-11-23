import type { Metadata, Viewport } from "next";
import { Suspense } from "react";

import { InventoryRoot } from "@/components/inventory/app";

export const metadata: Metadata = { title: "IT inventarizatsiya" };
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#4f46e5" };

/** Platforma menyusisiz mustaqil sahifa: filial xodimlari telefonda faqat shu modulni ko'radi. */
export default function InventoryPage() {
  return (
    <Suspense fallback={<div className="h-full bg-background" />}>
      <InventoryRoot />
    </Suspense>
  );
}
