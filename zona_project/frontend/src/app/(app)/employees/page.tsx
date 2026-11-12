import type { Metadata } from "next";

import { Employees } from "@/components/views/employees";

export const metadata: Metadata = { title: "Employees" };

export default function EmployeesPage() {
  return <Employees />;
}
