import type { Metadata } from "next";
import { Suspense } from "react";

import { InvDesktop } from "@/components/inventory/desktop";
import { Spinner } from "@/components/inventory/ui";

export const metadata: Metadata = { title: "Inventarizatsiya — import / eksport" };

export default function Page() {
  return (
    <Suspense fallback={<Spinner />}>
      <InvDesktop view="exchange" />
    </Suspense>
  );
}
