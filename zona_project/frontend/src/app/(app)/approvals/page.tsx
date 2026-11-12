import type { Metadata } from "next";

import { Approvals } from "@/components/views/approvals";

export const metadata: Metadata = { title: "Approval Workflows" };

export default function ApprovalsPage() {
  return <Approvals />;
}
