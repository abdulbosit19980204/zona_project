import type { Metadata } from "next";

import { SupportReview } from "@/components/support/review";

export const metadata: Metadata = { title: "Support — tasdiqlash" };

export default function Page() {
  return <SupportReview />;
}
