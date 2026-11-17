import type { Metadata } from "next";
import { Suspense } from "react";

import { QrStorages } from "@/components/qrdrive/storages";

export const metadata: Metadata = { title: "QR Drive — Saqlash joylari" };

export default function StoragesPage() {
  return (
    <Suspense>
      <QrStorages />
    </Suspense>
  );
}
