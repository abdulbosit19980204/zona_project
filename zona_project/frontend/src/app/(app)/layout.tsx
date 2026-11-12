import { Suspense } from "react";

import { AppShell, ShellSkeleton } from "@/components/layout/app-shell";

/** Ilova qismi: sidebar + yuqori panel. Server Component — brauzerga bog'liq qism Suspense ichida. */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <Suspense fallback={<ShellSkeleton />}>
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
