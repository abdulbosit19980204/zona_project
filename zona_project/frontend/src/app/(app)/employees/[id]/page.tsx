"use client";

import { useParams } from "next/navigation";

import { Employee360 } from "@/components/views/employee-360";

export default function EmployeePage() {
  const { id } = useParams<{ id: string }>();
  return <Employee360 memberId={Number(id)} />;
}
