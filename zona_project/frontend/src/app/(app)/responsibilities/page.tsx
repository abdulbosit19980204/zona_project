import type { Metadata } from "next";

import { Responsibilities } from "@/components/views/responsibilities";

export const metadata: Metadata = { title: "Responsibilities" };

export default function ResponsibilitiesPage() {
  return <Responsibilities />;
}
