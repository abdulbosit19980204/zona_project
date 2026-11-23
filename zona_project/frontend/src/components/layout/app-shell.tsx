"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { use, useEffect, type ReactNode } from "react";
import { browser } from "react-dom";

import { Sidebar } from "@/components/layout/sidebar";
import { MiniTopbar, Topbar } from "@/components/layout/topbar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useOrg } from "@/hooks/use-org";
import { useRealtime } from "@/hooks/use-realtime";
import { I18nProvider } from "@/i18n/provider";
import { moduleOf } from "@/lib/nav";
import { errorMessage } from "@/lib/api/client";
import { useAuth } from "@/stores/auth";

/** Server prerenderida ko'rinadigan skelet (JWT va til brauzerda). */
export function ShellSkeleton() {
  return (
    <div className="flex h-full">
      <div className="hidden w-64 shrink-0 border-r bg-sidebar p-4 md:block">
        <Skeleton className="mb-8 h-9 w-40" />
        {Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="mb-3 h-7 w-full" />)}
      </div>
      <div className="flex-1">
        <div className="h-16 border-b" />
        <div className="grid grid-cols-2 gap-4 p-8 lg:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
      </div>
    </div>
  );
}

function ZonaDown({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div className="grid h-full place-items-center p-8">
      <div className="max-w-md text-center">
        <AlertTriangle className="mx-auto mb-3 size-8 text-warning" />
        <div className="font-medium">Masʼuliyat platformasi backendi bilan aloqa yoʻq</div>
        <p className="mt-1 text-sm text-muted-foreground">{errorMessage(error)}</p>
        <p className="mt-1 text-sm text-muted-foreground">Boshqa servislar (masalan, QR Drive) ishlashda davom etadi — chap menyudan oching.</p>
        <Button className="mt-4" variant="outline" onClick={retry}><RefreshCw className="size-4" />Qayta urinish</Button>
      </div>
    </div>
  );
}

/** Har bir servis mustaqil: Zona backendi ishlamasa ham menyu va QR Drive sahifalari ochiladi. */
function Shell({ children }: { children: ReactNode }) {
  const org = useOrg();
  const pathname = usePathname();
  const me = org.data?.me;
  const live = useRealtime(me && !me.anonymous ? me.username : undefined);
  const qrPage = moduleOf(pathname).key === "qrdrive";

  if (org.isPending && !qrPage) return <ShellSkeleton />;
  const zonaOk = !!org.model;
  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        {zonaOk ? <Topbar live={live} /> : <MiniTopbar />}
        <main className="relative min-h-0 flex-1">
          {zonaOk || qrPage ? children : <ZonaDown error={org.error} retry={() => org.refetch()} />}
        </main>
      </div>
    </div>
  );
}

/**
 * Autentifikatsiya qilingan ilova. Faqat brauzerda render qilinadi (React 19.3 `browser()`):
 * token localStorage'da, shuning uchun serverda skelet ko'rinadi.
 */
export function AppShell({ children }: { children: ReactNode }) {
  use(browser("JWT tokenlar va til localStorage'da saqlanadi"));
  const router = useRouter();
  const access = useAuth((s) => s.access);
  const refresh = useAuth((s) => s.refresh);
  const inventoryOnly = useAuth((s) => s.user?.role === "inventory");

  useEffect(() => {
    if (!access && !refresh) router.replace("/login");
    else if (inventoryOnly) router.replace("/inventory");  // faqat inventarizatsiya logini — boshqa sahifalar yopiq
  }, [access, refresh, inventoryOnly, router]);

  if ((!access && !refresh) || inventoryOnly) return <ShellSkeleton />;
  return (
    <I18nProvider>
      <Shell>{children}</Shell>
    </I18nProvider>
  );
}
