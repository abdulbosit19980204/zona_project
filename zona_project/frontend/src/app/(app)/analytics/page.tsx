import type { Metadata } from "next";

import { Analytics } from "@/components/views/analytics";

export const metadata: Metadata = { title: "Responsibility Analytics" };

export default function AnalyticsPage() {
  return <Analytics />;
}
