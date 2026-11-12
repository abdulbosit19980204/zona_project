import type { Metadata } from "next";

import { Departments } from "@/components/views/departments";

export const metadata: Metadata = { title: "Departments" };

export default function DepartmentsPage() {
  return <Departments />;
}
