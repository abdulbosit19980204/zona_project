import type { Metadata } from "next";

import { PrbcIntegration } from "@/components/views/prbc";

export const metadata: Metadata = { title: "PRBC — jurnal" };

export default function PrbcLogPage() {
  return <PrbcIntegration view="log" />;
}
