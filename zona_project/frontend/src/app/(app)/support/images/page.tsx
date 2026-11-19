import type { Metadata } from "next";

import { SupportImages } from "@/components/support/images";

export const metadata: Metadata = { title: "Support — rasm turlari" };

export default function Page() {
  return <SupportImages />;
}
