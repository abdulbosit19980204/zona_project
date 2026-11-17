import type { Metadata } from "next";

import { QrSetup } from "@/components/qrdrive/setup";

export const metadata: Metadata = { title: "QR Drive — Sozlash ustasi" };

export default function SetupPage() {
  return <QrSetup />;
}
