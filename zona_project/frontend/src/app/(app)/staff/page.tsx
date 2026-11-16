import type { Metadata } from "next";

import { Staff } from "@/components/views/staff";

export const metadata: Metadata = { title: "Field Teams" };

export default function StaffPage() {
  return <Staff />;
}
