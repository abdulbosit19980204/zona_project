import type { Metadata } from "next";

import { Gaps } from "@/components/views/gaps";

export const metadata: Metadata = { title: "Accountability Gaps" };

export default function GapsPage() {
  return <Gaps />;
}
