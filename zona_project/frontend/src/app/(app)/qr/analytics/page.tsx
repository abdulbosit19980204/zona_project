import type { Metadata } from "next";

import { QrAnalytics } from "@/components/qrdrive/analytics";

export const metadata: Metadata = { title: "QR Drive — Analitika" };

export default function AnalyticsPage() {
  return <QrAnalytics />;
}
