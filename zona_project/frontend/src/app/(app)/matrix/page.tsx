import type { Metadata } from "next";

import { Matrix } from "@/components/views/matrix";

export const metadata: Metadata = { title: "Responsibility Matrix" };

export default function MatrixPage() {
  return <Matrix />;
}
