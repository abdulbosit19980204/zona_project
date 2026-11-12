import type { Metadata } from "next";

import { Processes } from "@/components/views/processes";

export const metadata: Metadata = { title: "Business Processes" };

export default function ProcessesPage() {
  return <Processes />;
}
