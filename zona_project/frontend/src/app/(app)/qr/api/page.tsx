import type { Metadata } from "next";

import { QrApi } from "@/components/qrdrive/api-keys";

export const metadata: Metadata = { title: "QR Drive — API" };

export default function ApiPage() {
  return <QrApi />;
}
