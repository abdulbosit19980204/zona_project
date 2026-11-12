"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import type { ReactNode } from "react";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

let browserQueryClient: QueryClient | undefined;

/** Serverda har render uchun yangi, brauzerda bitta umumiy QueryClient (Next.js tavsiyasi). */
function getQueryClient() {
  const make = () =>
    new QueryClient({
      defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 } },
    });
  if (typeof window === "undefined") return make();
  browserQueryClient ??= make();
  return browserQueryClient;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={getQueryClient()}>
      <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
        <TooltipProvider delayDuration={200}>
          {children}
          <Toaster richColors closeButton position="bottom-right" />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
