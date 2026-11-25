import type { Metadata } from "next";

import { PrbcIntegration } from "@/components/views/prbc";

export const metadata: Metadata = { title: "PRBC — vazifalar" };

export default function PrbcTasksPage() {
  return <PrbcIntegration view="tasks" />;
}
