import type { Metadata } from "next";

import { Audit } from "@/components/views/audit";

export const metadata: Metadata = { title: "Audit History" };

export default function AuditPage() {
  return <Audit />;
}
