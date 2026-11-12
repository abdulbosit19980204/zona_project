import type { Metadata } from "next";

import { WorkloadView } from "@/components/views/workload";

export const metadata: Metadata = { title: "Workload Analysis" };

export default function WorkloadPage() {
  return <WorkloadView />;
}
