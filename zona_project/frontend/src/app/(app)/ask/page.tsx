import type { Metadata } from "next";

import { Ask } from "@/components/views/ask";

export const metadata: Metadata = { title: "Who answers?" };

export default function AskPage() {
  return <Ask />;
}
