import type { Metadata } from "next";

import { QrDashboard } from "@/components/qrdrive/dashboard";

export const metadata: Metadata = { title: "QR Drive" };

export default function QrPage() {
  return <QrDashboard />;
}
