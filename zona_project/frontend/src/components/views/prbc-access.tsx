"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  CheckCircle2, CircleAlert, FlaskConical, KeyRound, MapPinOff, RefreshCcwDot, RotateCcw, Search, ShieldCheck, Undo2, Users, Wrench,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, StatCard } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type Key = "active" | "role" | "node" | "seat" | "mapping";
interface Row { id: number; name: string; position: string; node: string; telegram: string; issues: Key[]; fixed: Key[] }
interface Report {
  at?: string; error?: string; error_at?: string; rows?: Row[];
  counts?: { tp: number; active: number; ok: number; role: number; node: number; seat: number; mapping: number; fixed: number };
}
interface LogRow {
  id: number; at: string; source: string; prbc_user: number | null; name: string; action: string; ok: boolean; text: string;
  reversible: boolean; reverted_at: string | null; reverted_by: string;
}
interface Action { key: string; group: string; title: string; does: string; api: string; reversible: boolean; enabled: boolean }
interface Planned { key: string; title: string; does: string; api: string }
interface AccessData {
  access_bot: boolean; access_scan_minutes: number; scan_at: string | null; scan_requested: boolean;
  report: Report; ready: boolean; log: LogRow[]; actions: Action[]; planned: Planned[];
}
interface CheckItem { id: number; name: string; position: string; telegram: string; checks: { key: Key; ok: boolean; value: string }[] }
interface GroupRow { id: number; title: string; node: string; node_id: number | null; base: string }
interface SimResult { kind: string; text: string; note?: string; planned: { key: string; title: string; need: string; enabled: boolean }[] }

const KEYS: Key[] = ["mapping", "seat", "role", "node"];
const dt = (v?: string | null) => (v ? format(new Date(v), "dd.MM.yyyy HH:mm") : "—");

export function PrbcAccess() {
  const t = useTranslations("prbcAccess");
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["prbc", "access"], queryFn: async () => (await api.get<AccessData>("prbc/access/")).data,
    refetchInterval: (query) => (query.state.data?.scan_requested ? 4_000 : 30_000),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["prbc", "access"] });
  const save = useMutation({
    mutationFn: (v: Record<string, unknown>) => api.patch("prbc/access/", v),
    onSuccess: () => { toast.success(t("saved")); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const scan = useMutation({
    mutationFn: () => api.post("prbc/access/scan/"),
    onSuccess: () => { toast.success(t("scanQueued")); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const revert = useMutation({
    mutationFn: async (id: number) => (await api.post<{ detail: string }>(`prbc/access/log/${id}/revert/`)).data,
    onSuccess: (r) => { toast.success(r.detail); refresh(); },
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
        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex items-start gap-3 rounded-lg border p-3">
            <Switch checked={d.access_bot} onCheckedChange={(v) => save.mutate({ access_bot: v })} />
            <span><span className="block text-sm font-medium">{t("bot")}</span><span className="text-xs text-muted-foreground">{t("botHint")}</span></span>
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

      <Card className="gap-3 p-5">
        <div>
          <div className="flex items-center gap-2 font-semibold"><Wrench className="size-4" />{t("actionsTitle")}</div>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("actionsHint")}</p>
        </div>
        {(["outlet", "request"] as const).map((g) => (
          <div key={g} className="space-y-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t(`grp_${g}`)}</div>
            {d.actions.filter((a) => a.group === g).map((a) => (
              <label key={a.key} className={cn("flex items-start gap-3 rounded-lg border p-3", a.enabled && "border-success/40 bg-success/5")}>
                <Switch checked={a.enabled} onCheckedChange={(v) => save.mutate({ auto_actions: { [a.key]: v } })} />
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
                    {a.title}
                    <Badge variant="outline" className={a.enabled ? "border-success/40 text-success" : "text-muted-foreground"}>
                      {a.enabled ? t("on") : t("off")}
                    </Badge>
                    {a.reversible && <Badge variant="secondary"><Undo2 className="size-3" />{t("reversible")}</Badge>}
                  </span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">{a.does}</span>
                  <code className="mt-1 block break-all text-[11px] text-muted-foreground/80">{a.api}</code>
                </span>
              </label>
            ))}
          </div>
        ))}
        <div className="rounded-lg border border-dashed p-3">
          <div className="text-sm font-medium">{t("plannedTitle")}</div>
          <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
            {d.planned.map((p) => <li key={p.key}><span className="font-medium text-foreground">{p.title}</span> — {p.does}</li>)}
          </ul>
        </div>
      </Card>

      <Simulator ready={d.ready} />

      <div className="text-sm text-muted-foreground">{t("lastScan")}: {dt(rep.at)} · {t("checkOnly")}</div>
      {rep.error && (
        <Card className="flex-row items-center gap-2 border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <CircleAlert className="size-4" />{t("scanError", { at: dt(rep.error_at) })}: {rep.error}
        </Card>
      )}
      {c && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label={t("cActive")} value={c.active} icon={ShieldCheck} hint={t("cTp", { n: c.tp })} />
          <StatCard label={t("cOk")} value={c.ok} icon={CheckCircle2} tone="success" />
          <StatCard label={t("cMapping")} value={c.mapping} icon={MapPinOff} tone={c.mapping ? "warning" : "default"} hint={t("cMappingHint")} />
          <StatCard label={t("cSeat")} value={c.seat} icon={KeyRound} tone={c.seat ? "danger" : "default"} />
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
          <div className="max-h-[480px] overflow-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>{t("person")}</TableHead><TableHead>{t("node")}</TableHead><TableHead>{t("missing")}</TableHead>
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
                      {r.issues.map((k) => <Badge key={k} variant="outline" className="border-destructive/40 text-destructive">{t(`k_${k}`)}</Badge>)}
                    </div></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <p className="text-xs text-muted-foreground">{t("mappingNote")}</p>
      </Card>

      <GroupNodes ready={d.ready} />

      <Card className="gap-3 p-5">
        <div>
          <div className="font-semibold">{t("logTitle")}</div>
          <p className="text-sm text-muted-foreground">{t("logHint")}</p>
        </div>
        {d.log.length === 0 ? <EmptyState icon={Search} title={t("logEmpty")} /> : (
          <div className="max-h-[560px] overflow-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>{t("when")}</TableHead><TableHead>{t("source")}</TableHead><TableHead>{t("person")}</TableHead>
                <TableHead>{t("action")}</TableHead><TableHead>{t("result")}</TableHead><TableHead />
              </TableRow></TableHeader>
              <TableBody>
                {d.log.map((x) => (
                  <TableRow key={x.id} className={cn(x.reverted_at && "opacity-60")}>
                    <TableCell className="whitespace-nowrap text-xs">{dt(x.at)}</TableCell>
                    <TableCell><Badge variant="secondary">{t.has(`src_${x.source}`) ? t(`src_${x.source}`) : x.source}</Badge></TableCell>
                    <TableCell className="text-sm">{x.name || "—"}</TableCell>
                    <TableCell className="text-sm">{t.has(`a_${x.action}`) ? t(`a_${x.action}`) : x.action}</TableCell>
                    <TableCell className={cn("text-sm", x.ok ? "text-foreground" : "text-destructive")}>
                      {x.ok ? "✅" : "⚠️"} {x.text}
                      {x.reverted_at && <div className="text-xs text-muted-foreground">{t("reverted", { at: dt(x.reverted_at), by: x.reverted_by || "—" })}</div>}
                    </TableCell>
                    <TableCell>
                      {x.reversible && (
                        <Button size="sm" variant="outline" disabled={revert.isPending}
                          onClick={() => { if (window.confirm(t("revertConfirm"))) revert.mutate(x.id); }}>
                          <RotateCcw className="size-3.5" />{t("revert")}
                        </Button>
                      )}
                    </TableCell>
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

function Simulator({ ready }: { ready: boolean }) {
  const t = useTranslations("prbcAccess");
  const [text, setText] = useState("");
  const [items, setItems] = useState<CheckItem[] | null>(null);
  const [pick, setPick] = useState<CheckItem | null>(null);
  const [question, setQuestion] = useState("");
  const [group, setGroup] = useState("");
  const [res, setRes] = useState<SimResult | null>(null);
  const groups = useQuery({
    queryKey: ["prbc", "access-groups"], enabled: ready, retry: false,
    queryFn: async () => (await api.get<GroupRow[]>("prbc/access/groups/")).data,
  });
  const find = useMutation({
    mutationFn: async () => (await api.get<{ items: CheckItem[] }>("prbc/access/check/", { params: { q: text } })).data,
    onSuccess: (r) => { setItems(r.items); setPick(null); setRes(null); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const sim = useMutation({
    mutationFn: async () => (await api.post<SimResult>("prbc/access/simulate/", { user_id: pick?.id, text: question, group })).data,
    onSuccess: setRes,
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card className="gap-3 p-5">
      <div>
        <div className="flex items-center gap-2 font-semibold"><FlaskConical className="size-4" />{t("simTitle")}</div>
        <p className="text-sm text-muted-foreground">{t("simHint")}</p>
      </div>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim().length >= 3) find.mutate(); }}>
        <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={t("checkPh")} className="max-w-md" />
        <Button type="submit" disabled={find.isPending || text.trim().length < 3}><Search className="size-4" />{t("check")}</Button>
      </form>
      {items && items.length === 0 && <p className="text-sm text-muted-foreground">{t("notFound")}</p>}
      {items && items.map((u) => (
        <div key={u.id} className={cn("rounded-lg border p-3", pick?.id === u.id && "border-primary")}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="font-medium">{u.name} <span className="text-xs font-normal text-muted-foreground">{u.position}{u.telegram ? ` · @${u.telegram}` : ""} · PRBC #{u.id}</span></div>
            <Button size="sm" variant={pick?.id === u.id ? "default" : "outline"} onClick={() => { setPick(u); setRes(null); }}>
              <FlaskConical className="size-3.5" />{t("simPick")}
            </Button>
          </div>
          <div className="mt-2 grid gap-1 text-sm sm:grid-cols-2">
            {u.checks.map((ch) => (
              <div key={ch.key} className={cn(ch.ok ? "text-foreground" : ch.key === "node" ? "text-warning" : "text-destructive")}>
                {ch.ok ? "✅" : ch.key === "node" ? "⚠️" : "❌"} {t(`k_${ch.key}`)}{ch.value ? `: ${ch.value}` : ""}
              </div>
            ))}
          </div>
        </div>
      ))}
      {pick && (
        <div className="space-y-2 rounded-lg border bg-muted/30 p-3">
          <div className="grid gap-2 md:grid-cols-2">
            <div>
              <Label className="text-xs">{t("simQuestion")}</Label>
              <Textarea rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={t("simQuestionPh")} />
            </div>
            <div>
              <Label className="text-xs">{t("simGroup")}</Label>
              <Select value={group || "_none"} onValueChange={(v) => setGroup(v === "_none" ? "" : v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">{t("simNoGroup")}</SelectItem>
                  {(groups.data ?? []).map((g) => <SelectItem key={g.id} value={g.title}>{g.title}{g.node ? ` → ${g.node}` : ""}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button onClick={() => sim.mutate()} disabled={sim.isPending}><FlaskConical className="size-4" />{t("simRun", { name: pick.name })}</Button>
          {res && (
            <div className="space-y-2">
              <Badge variant="outline">{t(`kind_${res.kind}`)}</Badge>
              <pre className="whitespace-pre-wrap rounded-md border bg-card p-3 text-sm">{res.text}</pre>
              {res.planned.length > 0 && (
                <div className="text-sm">
                  <div className="font-medium">{t("simPlanned")}</div>
                  {res.planned.map((p) => (
                    <div key={p.key} className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className={p.enabled ? "border-success/40 text-success" : "text-muted-foreground"}>
                        {p.enabled ? t("simWould") : t("simOff")}
                      </Badge>
                      {p.title}: {p.need}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function GroupNodes({ ready }: { ready: boolean }) {
  const t = useTranslations("prbcAccess");
  const q = useQuery({
    queryKey: ["prbc", "access-groups"], enabled: ready, retry: false,
    queryFn: async () => (await api.get<GroupRow[]>("prbc/access/groups/")).data,
  });
  return (
    <Card className="gap-3 p-5">
      <div>
        <div className="flex items-center gap-2 font-semibold"><Users className="size-4" />{t("groupsTitle")}</div>
        <p className="text-sm text-muted-foreground">{t("groupsHint")}</p>
      </div>
      {q.isPending ? <Skeleton className="h-24" /> : (
        <div className="max-h-[360px] overflow-auto">
          <Table>
            <TableHeader><TableRow><TableHead>{t("group")}</TableHead><TableHead>{t("prbcNode")}</TableHead><TableHead>{t("base")}</TableHead></TableRow></TableHeader>
            <TableBody>
              {(q.data ?? []).map((g) => (
                <TableRow key={g.id}>
                  <TableCell className="text-sm">{g.title}</TableCell>
                  <TableCell className={cn("text-sm", !g.node && "text-muted-foreground")}>{g.node || t("noNode")}</TableCell>
                  <TableCell className="text-sm">{g.base || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </Card>
  );
}
