import type { Metadata } from "next";

import { SupportExplore } from "@/components/support/explore";

export const metadata: Metadata = { title: "Support — konstruktor" };

export default function Page() {
  return <SupportExplore />;
}
