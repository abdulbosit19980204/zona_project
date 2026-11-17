import type { Metadata } from "next";

import { QrRequests } from "@/components/qrdrive/requests";

export const metadata: Metadata = { title: "QR Drive — Kirish so'rovlari" };

export default function RequestsPage() {
  return <QrRequests />;
}
