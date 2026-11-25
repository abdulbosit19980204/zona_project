"use client";

import { useParams } from "next/navigation";

import { Manual } from "@/components/docs/manual";

export default function DocsChapterPage() {
  const { slug } = useParams<{ slug: string }>();
  return <Manual slug={slug} />;
}
