import type { Metadata } from "next";

import { PrbcIntegration } from "@/components/views/prbc";

export const metadata: Metadata = { title: "PRBC — yangi tochka ruxsatlari" };

export default function PrbcAccessPage() {
  return <PrbcIntegration view="access" />;
}
