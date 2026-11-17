import type { Metadata } from "next";

import { QrEmployees } from "@/components/qrdrive/employees";

export const metadata: Metadata = { title: "QR Drive — Xodimlar" };

export default function EmployeesPage() {
  return <QrEmployees />;
}
