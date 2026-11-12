import type { Metadata } from "next";

import { ResponsibilityMap } from "@/components/views/responsibility-map";

export const metadata: Metadata = { title: "Responsibility Map" };

export default function ResponsibilityMapPage() {
  return <ResponsibilityMap />;
}
