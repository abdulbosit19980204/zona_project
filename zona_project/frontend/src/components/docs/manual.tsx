"use client";

import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { BookOpen, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState, Page } from "@/components/common/page";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { headings, Markdown } from "./markdown";

interface Chapter { slug: string; order: number; title: string; description: string; updated: number; hits?: number; text?: string }

/** Qo'llanma: chapda boblar (va qidiruv), o'rtada bob matni, o'ngda bob mundarijasi. */
export function Manual({ slug = "umumiy" }: { slug?: string }) {
  const [q, setQ] = useState("");
  const list = useQuery({ queryKey: ["docs", "list", q], queryFn: async () => (await api.get<Chapter[]>("docs/", { params: q ? { q } : {} })).data });
  const doc = useQuery({ queryKey: ["docs", slug], queryFn: async () => (await api.get<Chapter>(`docs/${slug}/`)).data, retry: false });
  const toc = doc.data?.text ? headings(doc.data.text) : [];
  return (
    <Page>
      <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)] xl:grid-cols-[240px_minmax(0,1fr)_220px]">
        <aside className="lg:sticky lg:top-4 lg:h-fit">
          <div className="relative mb-3">
            <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input className="h-9 pl-8" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Qo'llanmadan qidirish…" />
          </div>
          <nav className="grid gap-0.5">
            {list.isPending && <Skeleton className="h-40" />}
            {list.data?.map((c) => (
              <Link key={c.slug} href={c.slug === "umumiy" ? "/docs" : `/docs/${c.slug}`}
                className={cn("rounded-lg px-3 py-2 text-sm transition-colors hover:bg-muted",
                  c.slug === slug ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground")}>
                <span className="flex items-center justify-between gap-2">{c.title}
                  {c.hits ? <span className="rounded-full bg-primary/15 px-1.5 text-[10px] text-primary">{c.hits}</span> : null}</span>
              </Link>
            ))}
            {list.data && !list.data.length && <p className="px-3 text-xs text-muted-foreground">Topilmadi</p>}
          </nav>
        </aside>
        <Card className="min-w-0 gap-0 p-6 md:p-8">
          {doc.isPending ? <Skeleton className="h-96" /> : !doc.data ? <EmptyState icon={BookOpen} title="Bob topilmadi" /> : (
            <>
              <Markdown text={doc.data.text ?? ""} />
              <div className="mt-10 border-t pt-3 text-xs text-muted-foreground">
                Oxirgi yangilanish: {format(new Date(doc.data.updated * 1000), "dd.MM.yyyy HH:mm")} · manba: <code>docs/manual</code>
              </div>
            </>
          )}
        </Card>
        {toc.length > 0 && (
          <aside className="hidden xl:block xl:sticky xl:top-4 xl:h-fit">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Shu bobda</div>
            <nav className="grid gap-1 border-l pl-3 text-xs">
              {toc.map((h) => (
                <a key={h.id} href={`#${h.id}`} className={cn("text-muted-foreground hover:text-foreground", h.level === 3 && "pl-3")}>{h.title}</a>
              ))}
            </nav>
          </aside>
        )}
      </div>
    </Page>
  );
}
