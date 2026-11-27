"use client";

import { useMutation } from "@tanstack/react-query";
import { format } from "date-fns";
import { ExternalLink, FlaskConical, Link2, Search, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

interface Acc { id: number; name: string; status: string; login: string; telegram: boolean; phone: string; joined: string; position: string; link: string }
interface Gate { code: string; ok: boolean; label: string; why: string }
interface CheckResult { a: Acc | null; b: Acc | null; phone: string; by: string; many: number; gates: Gate[]; card: string }
interface SimResult { kind: string; text: string; note?: string; planned: { key: string; text: string; enabled?: boolean }[] }
export interface BindReport { at?: string; pairs?: number; old_pending?: number; rows?: { a: Acc; b: Acc }[] }

const dt = (v?: string | null) => (v ? format(new Date(v), "dd.MM.yyyy HH:mm") : "—");

export function PrbcBinding({ ready, bot, strict, report, onSave }: {
  ready: boolean; bot: boolean; strict: boolean; report: BindReport; onSave: (v: Record<string, unknown>) => void;
}) {
  const t = useTranslations("prbcBind");
  const ta = useTranslations("prbcAccess");
  const [q, setQ] = useState("");
  const [res, setRes] = useState<CheckResult | null>(null);
  const [who, setWho] = useState("");
  const [phone, setPhone] = useState("");
  const [sim, setSim] = useState<SimResult | null>(null);
  const check = useMutation({
    mutationFn: async () => (await api.get<CheckResult>("prbc/access/bind/check/", { params: { q } })).data,
    onSuccess: setRes,
    onError: (e) => toast.error(errorMessage(e)),
  });
  const run = useMutation({
    mutationFn: async () => {
      const id = who.trim();
      const body = /^\d+$/.test(id) ? { tg_id: id, phone } : { query: id, phone };
      return (await api.post<SimResult>("prbc/access/bind/simulate/", body)).data;
    },
    onSuccess: setSim,
    onError: (e) => toast.error(errorMessage(e)),
  });
  const rows = report.rows ?? [];

  return (
    <Card className="gap-4 p-5">
      <div>
        <div className="flex items-center gap-2 font-semibold"><Link2 className="size-4" />{t("title")}</div>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("hint")}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="flex items-start gap-3 rounded-lg border p-3">
          <Switch checked={bot} onCheckedChange={(v) => onSave({ bind_bot: v })} />
          <span><span className="block text-sm font-medium">{t("bot")}</span><span className="text-xs text-muted-foreground">{t("botHint")}</span></span>
        </label>
        <label className="flex items-start gap-3 rounded-lg border p-3">
          <Switch checked={strict} onCheckedChange={(v) => onSave({ bind_strict_name: v })} />
          <span><span className="block text-sm font-medium">{t("strict")}</span><span className="text-xs text-muted-foreground">{t("strictHint")}</span></span>
        </label>
      </div>
      <p className="text-xs text-muted-foreground">{t("manual")}</p>

      <div className="space-y-2 rounded-lg border p-3">
        <div className="text-sm font-medium">{t("checkTitle")}</div>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 3) check.mutate(); }}>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("checkPh")} className="max-w-md" />
          <Button type="submit" disabled={!ready || check.isPending || q.trim().length < 3}><Search className="size-4" />{t("check")}</Button>
        </form>
        {res && (
          <div className="space-y-2">
            <div className="grid gap-2 sm:grid-cols-2">
              {(["a", "b"] as const).map((k) => {
                const u = res[k];
                return (
                  <div key={k} className="rounded-md border p-2 text-sm">
                    <div className="text-xs font-semibold text-muted-foreground">{t(k)}</div>
                    {u ? (
                      <>
                        <div className="font-medium">{u.name}</div>
                        <div className="text-xs text-muted-foreground">
                          #{u.id} · {u.login}… · {u.status} · {u.telegram ? "Telegram ✓" : "Telegram ✗"}{u.phone ? ` · ${u.phone}` : ""}
                        </div>
                        <a href={u.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
                          <ExternalLink className="size-3" />{t("open")}
                        </a>
                      </>
                    ) : <div className="text-muted-foreground">{t("none")}</div>}
                  </div>
                );
              })}
            </div>
            <div className="text-sm font-medium">{t("gatesTitle")}</div>
            <div className="grid gap-1 text-sm sm:grid-cols-2">
              {res.gates.filter((g) => g.code !== "G1").map((g) => (
                <div key={g.code} className={g.ok ? "text-foreground" : "text-destructive"}>
                  {g.ok ? "✅" : "❌"} {g.code}. {g.label}{!g.ok && g.why ? ` — ${g.why}` : ""}
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">{t("g1note")}</p>
          </div>
        )}
      </div>

      <div className="space-y-2 rounded-lg border bg-muted/30 p-3">
        <div className="flex items-center gap-2 text-sm font-medium"><FlaskConical className="size-4" />{t("simTitle")}</div>
        <p className="text-xs text-muted-foreground">{t("simHint")}</p>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (who.trim()) run.mutate(); }}>
          <Input value={who} onChange={(e) => setWho(e.target.value)} placeholder={t("simWho")} className="max-w-xs" />
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder={t("simPhone")} className="max-w-[200px]" />
          <Button type="submit" disabled={!ready || run.isPending || !who.trim()}><FlaskConical className="size-4" />{t("simRun")}</Button>
        </form>
        {sim && (
          <div className="space-y-2">
            <Badge variant="outline">{ta.has(`kind_${sim.kind}`) ? ta(`kind_${sim.kind}`) : sim.kind}</Badge>
            <pre className="whitespace-pre-wrap rounded-md border bg-card p-3 text-sm">{sim.text}</pre>
            {sim.note && <pre className="whitespace-pre-wrap rounded-md border bg-card p-3 text-xs text-muted-foreground">{sim.note}</pre>}
            {sim.planned.length > 0 && (
              <div className="text-sm">
                <div className="font-medium">{t("planned")}</div>
                {sim.planned.map((p) => (
                  <div key={p.key} className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className={p.enabled ? "border-success/40 text-success" : "text-muted-foreground"}>
                      {p.enabled ? t("would") : t("off")}
                    </Badge>
                    {ta.has(`a_${p.key}`) ? ta(`a_${p.key}`) : p.key}: {p.text}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-medium"><Users className="size-4" />{t("pairsTitle")}</div>
        <p className="text-xs text-muted-foreground">
          {t("pairsHint")} {t("lastScan")}: {dt(report.at)}{report.old_pending != null ? ` · ${t("oldPending", { n: report.old_pending })}` : ""}
        </p>
        {rows.length === 0 ? <EmptyState icon={Users} title={t("pairsEmpty")} /> : (
          <div className="max-h-[360px] overflow-auto">
            <Table>
              <TableHeader><TableRow><TableHead>{t("a")}</TableHead><TableHead>{t("b")}</TableHead></TableRow></TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={`${r.a.id}-${r.b.id}`}>
                    {[r.a, r.b].map((u) => (
                      <TableCell key={u.id} className="text-sm">
                        <a href={u.link} target="_blank" rel="noreferrer" className={cn("font-medium hover:underline")}>{u.name}</a>
                        <div className="text-xs text-muted-foreground">#{u.id} · {u.login}… · {u.status}{u.phone ? ` · ${u.phone}` : ""}</div>
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </Card>
  );
}
