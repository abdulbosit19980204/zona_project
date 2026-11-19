import type { Metadata } from "next";

import { SupportAnalytics } from "@/components/support/analytics";

export const metadata: Metadata = { title: "Support — tahlil" };

export default function Page() {
  return <SupportAnalytics />;
}
