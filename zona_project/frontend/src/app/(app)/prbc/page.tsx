import type { Metadata } from "next";

import { PrbcIntegration } from "@/components/views/prbc";

export const metadata: Metadata = { title: "PRBC integratsiya" };

export default function PrbcPage() {
  return <PrbcIntegration />;
}
