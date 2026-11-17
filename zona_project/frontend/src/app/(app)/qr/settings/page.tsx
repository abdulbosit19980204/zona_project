import type { Metadata } from "next";

import { QrSettingsPage } from "@/components/qrdrive/settings";

export const metadata: Metadata = { title: "QR Drive — Bot sozlamalari" };

export default function SettingsPage() {
  return <QrSettingsPage />;
}
