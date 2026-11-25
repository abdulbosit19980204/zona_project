import type { Metadata } from "next";

import { PrbcIntegration } from "@/components/views/prbc";

export const metadata: Metadata = { title: "PRBC — nazorat" };

export default function PrbcPage() {
  return <PrbcIntegration view="control" />;
}
