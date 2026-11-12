import type { Metadata } from "next";

import { OrganizationMap } from "@/components/views/organization-map";

export const metadata: Metadata = { title: "Organization Map" };

export default function OrganizationPage() {
  return <OrganizationMap />;
}
