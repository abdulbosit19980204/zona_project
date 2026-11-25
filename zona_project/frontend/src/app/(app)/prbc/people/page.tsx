import type { Metadata } from "next";

import { PrbcIntegration } from "@/components/views/prbc";

export const metadata: Metadata = { title: "PRBC — xodimlar" };

export default function PrbcPeoplePage() {
  return <PrbcIntegration view="people" />;
}
