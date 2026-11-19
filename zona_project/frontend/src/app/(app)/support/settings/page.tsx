import type { Metadata } from "next";

import { SupportSettingsPage } from "@/components/support/settings";

export const metadata: Metadata = { title: "Support — sozlamalar" };

export default function Page() {
  return <SupportSettingsPage />;
}
