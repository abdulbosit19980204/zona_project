import type { Metadata } from "next";

import { Manual } from "@/components/docs/manual";

export const metadata: Metadata = { title: "Qo'llanma" };

export default function DocsPage() {
  return <Manual />;
}
