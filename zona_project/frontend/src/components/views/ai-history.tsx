"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, Search, Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Markdown } from "@/components/common/markdown";
import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { cn } from "@/lib/utils";

interface Row { id: number; task: string; label: string; user: string; provider: string; model: string; tokens: number; created_at: string; preview: string }
interface Item extends Row { prompt: string; result: Record<string, unknown>; input_tokens: number; output_tokens: number }

const TASKS = ["all", "route", "person", "audit", "workload", "translate", "support"] as const;

function fmt(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** Saqlangan AI tahlillari: har bir AI natijasi (yo'naltirish, xodim tahlili, audit, yuklama, support bot) shu yerda qoladi. */
export function AIHistory() {
  const t = useTranslations("aiHistory");
  const tt = useTranslations("ai.task");
  const [task, setTask] = useState<(typeof TASKS)[number]>("all");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const list = useQuery({
    queryKey: ["ai-history", task, q],
    queryFn: async () => (await api.get<Row[]>("ai/history/", { params: { ...(task !== "all" ? { task } : {}), ...(q ? { q } : {}), limit: 200 } })).data,
  });
  const item = useQuery({
    queryKey: ["ai-history", "item", open], enabled: open !== null,
    queryFn: async () => (await api.get<Item>(`ai/history/${open}/`)).data,
  });
  const label = (k: string) => (k === "all" ? t("all") : tt.has(k) ? tt(k) : k);

  return (
    <Page>
      <PageHeader title={t("title")} description={t("description")} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1">
          {TASKS.map((k) => (
            <button key={k} type="button" onClick={() => setTask(k)}
              className={cn("rounded-full border px-2.5 py-1 text-xs", task === k ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted")}>
              {label(k)}
            </button>
          ))}
        </div>
        <div className="relative ml-auto w-full max-w-64">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="h-9 pl-8" />
        </div>
      </div>
      {list.isLoading && <Skeleton className="h-64" />}
      {list.data?.length === 0 && <EmptyState icon={Sparkles} title={t("empty")} hint={t("emptyHint")} />}
      <div className="grid gap-2">
        {list.data?.map((r) => (
          <button key={r.id} type="button" onClick={() => setOpen(r.id)}
            className="flex flex-col gap-1 rounded-xl border bg-card p-3 text-left transition-colors hover:border-primary/40">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline" className="font-normal">{label(r.task)}</Badge>
              <span>{fmt(r.created_at)}</span>{r.user && <span>· {r.user}</span>}<span>· {r.model}</span>
              <span className="ml-auto font-mono">{r.tokens} tok</span>
            </div>
            <div className="truncate text-sm font-medium">{r.label || "—"}</div>
            {r.preview && <div className="line-clamp-2 text-xs text-muted-foreground">{r.preview}</div>}
          </button>
        ))}
      </div>
      <Dialog open={open !== null} onOpenChange={(v) => !v && setOpen(null)}>
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Bot className="size-4" />{item.data?.label || t("title")}</DialogTitle></DialogHeader>
          {!item.data ? <Skeleton className="h-40" /> : (
            <div className="grid gap-3">
              <div className="text-xs text-muted-foreground">{label(item.data.task)} · {fmt(item.data.created_at)} · {item.data.provider} / {item.data.model} · {item.data.input_tokens}+{item.data.output_tokens} tok</div>
              {typeof item.data.result.text === "string"
                ? <Card className="p-4"><Markdown text={item.data.result.text} /></Card>
                : <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs">{JSON.stringify(item.data.result, null, 2)}</pre>}
              {item.data.prompt && (
                <details className="text-xs"><summary className="cursor-pointer text-muted-foreground">{t("prompt")}</summary>
                  <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-muted p-3">{item.data.prompt}</pre></details>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </Page>
  );
}
