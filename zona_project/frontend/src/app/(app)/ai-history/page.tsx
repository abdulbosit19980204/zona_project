import type { Metadata } from "next";

import { AIHistory } from "@/components/views/ai-history";

export const metadata: Metadata = { title: "AI tahlillar" };

export default function Page() {
  return <AIHistory />;
}
