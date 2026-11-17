import type { Metadata } from "next";
import { Suspense } from "react";

import { QrFiles } from "@/components/qrdrive/files";

export const metadata: Metadata = { title: "QR Drive — Fayllar" };

export default function FilesPage() {
  return (
    <Suspense>
      <QrFiles />
    </Suspense>
  );
}
