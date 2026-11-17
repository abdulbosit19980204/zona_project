import type { Metadata } from "next";

import { QrSystem } from "@/components/qrdrive/system";

export const metadata: Metadata = { title: "QR Drive — Tizim holati" };

export default function SystemPage() {
  return <QrSystem />;
}
