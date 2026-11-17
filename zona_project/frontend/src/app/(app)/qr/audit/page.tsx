import type { Metadata } from "next";

import { QrAudit } from "@/components/qrdrive/audit";

export const metadata: Metadata = { title: "QR Drive — Jurnal" };

export default function AuditPage() {
  return <QrAudit />;
}
