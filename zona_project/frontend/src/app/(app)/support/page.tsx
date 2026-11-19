import type { Metadata } from "next";

import { SupportInbox } from "@/components/support/inbox";

export const metadata: Metadata = { title: "Support — savollar" };

export default function Page() {
  return <SupportInbox />;
}
