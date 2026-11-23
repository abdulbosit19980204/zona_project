"use client";

import { useParams } from "next/navigation";

import { StaffPage } from "@/components/support/person-pages";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <StaffPage id={Number(id)} />;
}
