import type { Metadata } from "next";

import { PrbcIntegration } from "@/components/views/prbc";

export const metadata: Metadata = { title: "PRBC — sozlamalar" };

export default function PrbcSettingsPage() {
  return <PrbcIntegration view="settings" />;
}
