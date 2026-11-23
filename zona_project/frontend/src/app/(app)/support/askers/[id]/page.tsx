"use client";

import { useParams } from "next/navigation";

import { AskerPage } from "@/components/support/person-pages";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <AskerPage id={Number(id)} />;
}
