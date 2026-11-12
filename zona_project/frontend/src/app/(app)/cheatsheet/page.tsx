import type { Metadata } from "next";

import { Cheatsheet } from "@/components/views/cheatsheet";

export const metadata: Metadata = { title: "Who to Contact" };

export default function CheatsheetPage() {
  return <Cheatsheet />;
}
