import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginScreen } from "@/components/views/login-screen";

export const metadata: Metadata = { title: "Kirish" };

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="h-full canvas-grid" />}>
      <LoginScreen />
    </Suspense>
  );
}
