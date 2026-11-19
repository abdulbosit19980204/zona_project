import type { Metadata } from "next";

import { SupportKnowledge } from "@/components/support/knowledge";

export const metadata: Metadata = { title: "Support — bilim bazasi" };

export default function Page() {
  return <SupportKnowledge />;
}
