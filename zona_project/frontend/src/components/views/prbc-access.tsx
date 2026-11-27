"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { CheckCircle2, CircleAlert, KeyRound, MapPinOff, RefreshCcwDot, Search, ShieldCheck, Wrench } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, StatCard } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type Key = "active" | "role" | "node" | "seat" | "mapping";
interface Row { id: number; name: string; position: string; node: string; telegram: string; issues: Key[]; fixed: Key[] }
interface Report {
  at?: string; autofix?: boolean; error?: string; error_at?: string; rows?: Row[];
  counts?: { tp: number; active: number; ok: number; role: number; node: number; seat: number; mapping: number; fixed: number };
}
interface LogRow { id: number; at: string; source: string; prbc_user: number | null; name: string; action: string; ok: boolean; text: string }
interface AccessData {
  access_bot: boolean; access_autofix: boolean; access_scan_minutes: number; scan_at: string | null; scan_requested: boolean;
  report: Report; ready: boolean; log: LogRow[];
}
interface CheckItem { id: number; name: string; position: string; telegram: string; checks: { key: Key; ok: boolean; value: string }[] }

const KEYS: Key[] = ["mapping", "seat", "role", "node"];
const dt = (v?: string | null) => (v ? format(new Date(v), "dd.MM.yyyy HH:mm") : "—");

export function PrbcAccess() {
  const t = useTranslations("prbcAccess");
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["prbc", "access"], queryFn: async () => (await api.get<AccessData>("prbc/access/")).data,
    refetchInterval: (query) => (query.state.data?.scan_requested ? 4_000 : 30_000),
  });
  const save = useMutation({
    mutationFn: (v: Partial<AccessData>) => api.patch("prbc/access/", v),
    onSuccess: () => { toast.success(t("saved")); qc.invalidateQueries({ queryKey: ["prbc", "access"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const scan = useMutation({
    mutationFn: () => api.post("prbc/access/scan/"),
    onSuccess: () => { toast.success(t("scanQueued")); qc.invalidateQueries({ queryKey: ["prbc", "access"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const [only, setOnly] = useState<Key | "">("");
  const [minutes, setMinutes] = useState<string | null>(null);

  if (q.isPending) return <Skeleton className="h-96 rounded-xl" />;
  if (!q.data) return <EmptyState icon={CircleAlert} title={t("loadError")} />;
  const d = q.data;
  const rep = d.report || {};
  const c = rep.counts;
  const rows = (rep.rows ?? []).filter((r) => !only || r.issues.includes(only));

  return (
    <div className="space-y-5">
      <Card className="gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="font-semibold">{t("howTitle")}</div>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("how")}</p>
          </div>
          <Button variant="outline" onClick={() => scan.mutate()} disabled={scan.isPending || d.scan_requested || !d.ready}>
            <RefreshCcwDot className={cn("size-4", d.scan_requested && "animate-spin")} />{t("scanNow")}
          </Button>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <label className="flex items-start gap-3 rounded-lg border p-3">
            <Switch checked={d.access_bot} onCheckedChange={(v) => save.mutate({ access_bot: v })} />
            <span><span className="block text-sm font-medium">{t("bot")}</span><span className="text-xs text-muted-foreground">{t("botHint")}</span></span>
          </label>
          <label className="flex items-start gap-3 rounded-lg border p-3">
            <Switch checked={d.access_autofix} onCheckedChange={(v) => save.mutate({ access_autofix: v })} />
            <span><span className="block text-sm font-medium">{t("autofix")}</span><span className="text-xs text-muted-foreground">{t("autofixHint")}</span></span>
          </label>
          <div className="rounded-lg border p-3">
            <Label className="text-sm font-medium">{t("every")}</Label>
            <div className="mt-2 flex gap-2">
              <Input type="number" min={0} max={1440} className="w-28" value={minutes ?? String(d.access_scan_minutes)}
                onChange={(e) => setMinutes(e.target.value)} />
              <Button variant="secondary" disabled={minutes === null || save.isPending}
                onClick={() => { save.mutate({ access_scan_minutes: Number(minutes || 0) }); setMinutes(null); }}>{t("save")}</Button>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t("everyHint")}</p>
          </div>
        </div>
      </Card>

      <div className="text-sm text-muted-foreground">
        {t("lastScan")}: {dt(rep.at)}{rep.at && (rep.autofix ? ` · ${t("withFix")}` : ` · ${t("checkOnly")}`)}
      </div>
      {rep.error && (
        <Card className="flex-row items-center gap-2 border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <CircleAlert className="size-4" />{t("scanError", { at: dt(rep.error_at) })}: {rep.error}
        </Card>
      )}
      {c && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <StatCard label={t("cActive")} value={c.active} icon={ShieldCheck} hint={t("cTp", { n: c.tp })} />
          <StatCard label={t("cOk")} value={c.ok} icon={CheckCircle2} tone="success" />
          <StatCard label={t("cMapping")} value={c.mapping} icon={MapPinOff} tone={c.mapping ? "warning" : "default"} hint={t("cMappingHint")} />
          <StatCard label={t("cSeat")} value={c.seat} icon={KeyRound} tone={c.seat ? "danger" : "default"} />
          <StatCard label={t("cFixed")} value={c.fixed} icon={Wrench} tone={c.fixed ? "success" : "default"} />
        </div>
      )}

      <Card className="gap-3 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="font-semibold">{t("problems")}</div>
          <div className="flex flex-wrap gap-1.5">
            {(["", ...KEYS] as (Key | "")[]).map((k) => (
              <button key={k || "all"} onClick={() => setOnly(k)}
                className={cn("rounded-full border px-3 py-1 text-xs font-medium",
                  only === k ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>
                {k ? t(`k_${k}`) : t("all")}{k && c ? ` · ${c[k]}` : ""}
              </button>
            ))}
          </div>
        </div>
        {rows.length === 0 ? <EmptyState icon={CheckCircle2} title={t("noProblems")} /> : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>{t("person")}</TableHead><TableHead>{t("node")}</TableHead>
                <TableHead>{t("missing")}</TableHead><TableHead>{t("fixedNow")}</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>
                      <div className="font-medium">{r.name}</div>
                      <div className="text-xs text-muted-foreground">{r.telegram ? `@${r.telegram} · ` : ""}PRBC #{r.id}</div>
                    </TableCell>
                    <TableCell className="text-sm">{r.node || "—"}</TableCell>
                    <TableCell><div className="flex flex-wrap gap-1">
                      {r.issues.length ? r.issues.map((k) => <Badge key={k} variant="outline" className="border-destructive/40 text-destructive">{t(`k_${k}`)}</Badge>) : "—"}
                    </div></TableCell>
                    <TableCell><div className="flex flex-wrap gap-1">
                      {r.fixed.length ? r.fixed.map((k) => <Badge key={k} variant="outline" className="border-success/40 text-success">{t(`k_${k}`)}</Badge>) : "—"}
                    </div></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <p className="text-xs text-muted-foreground">{t("mappingNote")}</p>
      </Card>

      <CheckOne />

      <Card className="gap-3 p-5">
        <div className="font-semibold">{t("logTitle")}</div>
        {d.log.length === 0 ? <EmptyState icon={Search} title={t("logEmpty")} /> : (
          <div className="max-h-[520px] overflow-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>{t("when")}</TableHead><TableHead>{t("source")}</TableHead><TableHead>{t("person")}</TableHead>
                <TableHead>{t("action")}</TableHead><TableHead>{t("result")}</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {d.log.map((x) => (
                  <TableRow key={x.id}>
                    <TableCell className="whitespace-nowrap text-xs">{dt(x.at)}</TableCell>
                    <TableCell><Badge variant="secondary">{t(`src_${x.source}`)}</Badge></TableCell>
                    <TableCell className="text-sm">{x.name || "—"}</TableCell>
                    <TableCell className="text-sm">{t.has(`a_${x.action}`) ? t(`a_${x.action}`) : x.action}</TableCell>
                    <TableCell className={cn("text-sm", x.ok ? "text-foreground" : "text-destructive")}>{x.ok ? "✅" : "⚠️"} {x.text}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>
    </div>
  );
}

function CheckOne() {
  const t = useTranslations("prbcAccess");
  const [text, setText] = useState("");
  const [items, setItems] = useState<CheckItem[] | null>(null);
  const run = useMutation({
    mutationFn: async () => (await api.get<{ items: CheckItem[] }>("prbc/access/check/", { params: { q: text } })).data,
    onSuccess: (r) => setItems(r.items),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card className="gap-3 p-5">
      <div>
        <div className="font-semibold">{t("checkTitle")}</div>
        <p className="text-sm text-muted-foreground">{t("checkHint")}</p>
      </div>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim().length >= 3) run.mutate(); }}>
        <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={t("checkPh")} className="max-w-md" />
        <Button type="submit" disabled={run.isPending || text.trim().length < 3}><Search className="size-4" />{t("check")}</Button>
      </form>
      {items && items.length === 0 && <p className="text-sm text-muted-foreground">{t("notFound")}</p>}
      {items && items.map((u) => (
        <div key={u.id} className="rounded-lg border p-3">
          <div className="font-medium">{u.name} <span className="text-xs font-normal text-muted-foreground">{u.position}{u.telegram ? ` · @${u.telegram}` : ""} · PRBC #{u.id}</span></div>
          <div className="mt-2 grid gap-1 text-sm sm:grid-cols-2">
            {u.checks.map((ch) => (
              <div key={ch.key} className={cn(ch.ok ? "text-foreground" : ch.key === "node" ? "text-warning" : "text-destructive")}>
                {ch.ok ? "✅" : ch.key === "node" ? "⚠️" : "❌"} {t(`k_${ch.key}`)}{ch.value ? `: ${ch.value}` : ""}
              </div>
            ))}
          </div>
        </div>
      ))}
    </Card>
  );
}
