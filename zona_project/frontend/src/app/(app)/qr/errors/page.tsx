import type { Metadata } from "next";
import { Suspense } from "react";

import { QrErrors } from "@/components/qrdrive/errors";

export const metadata: Metadata = { title: "QR Drive — Xatolar markazi" };

export default function ErrorsPage() {
  return (
    <Suspense>
      <QrErrors />
    </Suspense>
  );
}
