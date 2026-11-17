"use client";

import { CheckCircle2, HardDrive, Pencil, Plug, Plus, Server, Star, Trash2, XCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useQr, useQrAction } from "@/hooks/use-qrdrive";
import { formatBytes, qrApi, qrError, type QrStorage, type StorageKind } from "@/lib/api/qrdrive";
import { cn } from "@/lib/utils";

import { ConfirmDialog, Dot, FormRow, QrGuard, fmtDate } from "./common";
import { errorText, useQt, type QKey } from "./i18n";

export interface Draft {
  id?: number; name: string; kind: string; base_folder: string; link_mode: "provider" | "system";
  is_fallback: boolean; enabled: boolean; is_primary: boolean; config: Record<string, unknown>;
}

type Check = { ok: boolean; title?: string; hint?: string; latency_ms?: number; kind?: string } | null;

export function QrStorages() {
  const t = useQt();
  const q = useQr<QrStorage[]>(["storages"], "storages");
  const params = useSearchParams();
  useEffect(() => {
    const g = params.get("google");
    if (g === "ok") toast.success(t("googleOk"));
    if (g === "error") toast.error(t("googleErr"));
  }, [params, t]);
  const google = useQrAction(async (id: number) => (await qrApi.post<{ url: string }>(`storages/${id}/google/start`)).data);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [del, setDel] = useState<QrStorage | null>(null);
  const test = useQrAction(async (id: number) => (await qrApi.post<QrStorage>(`storages/${id}/test`)).data,
    (r) => (r.check?.ok ? t("connOk", { ms: r.check.latency_ms ?? 0 }) : undefined));
  const primary = useQrAction(async (id: number) => qrApi.post(`storages/${id}/primary`), t("saved"));
  const remove = useQrAction(async (id: number) => qrApi.delete(`storages/${id}`), t("saved"));

  return (
    <Page>
      <PageHeader title={t("stoTitle")} description={t("stoDesc")}
        actions={<Button onClick={() => setDraft({ name: "", kind: "synology", base_folder: "/Kadrlar", link_mode: "provider",
          is_fallback: false, enabled: true, is_primary: false, config: {} })}><Plus className="size-4" />{t("addStorage")}</Button>} />
      <QrGuard query={q}>
        {!q.data?.length ? <EmptyState icon={HardDrive} title={t("stoEmpty")} hint={t("stoEmptyHint")} /> : (
          <div className="grid gap-4 lg:grid-cols-2">
            {q.data.map((s) => {
              const pct = s.quota_total && s.quota_used !== null ? s.quota_used / s.quota_total : null;
              const err = s.last_error ? errorText(t, { kind: s.last_error, title: "", hint: "" }) : null;
              return (
                <Card key={s.id} className={cn("gap-3 p-5", !s.enabled && "opacity-60")}>
                  <div className="flex items-start gap-3">
                    <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
                      {s.kind === "synology" ? <Server className="size-5" /> : <HardDrive className="size-5" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 font-medium">{s.name}
                        {s.is_primary && <Badge className="border-0 bg-primary/15 text-primary"><Star className="size-3" />{t("primary")}</Badge>}
                        {s.is_fallback && <Badge variant="outline">{t("fallback")}</Badge>}
                      </div>
                      <div className="text-xs text-muted-foreground">{s.kind_label} · {s.base_folder} · {t("stoFiles", { n: s.files })}</div>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs">
                      <Dot ok={s.status === "ok"} unknown={s.status === "unknown"} />{t(`status_${s.status}` as QKey)}
                    </div>
                  </div>
                  {err && (s.status === "down" || s.last_error === "not_configured") && (
                    <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm">
                      <div className="font-medium text-destructive">{err.title}</div>
                      <div className="text-xs text-muted-foreground">{err.hint}</div>
                    </div>
                  )}
                  {pct !== null && (
                    <div>
                      <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                        <span>{t("quota")}</span><span>{formatBytes(s.quota_used)} / {formatBytes(s.quota_total)} ({Math.round(pct * 100)}%)</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div className={cn("h-full rounded-full", pct > 0.9 ? "bg-destructive" : pct > 0.75 ? "bg-warning" : "bg-primary")} style={{ width: `${Math.round(pct * 100)}%` }} />
                      </div>
                    </div>
                  )}
                  <div className="text-xs text-muted-foreground">
                    {t("lastCheck")}: {fmtDate(s.last_check_at)}{s.latency_ms !== null && ` · ${s.latency_ms} ms`} · {s.link_mode === "system" ? t("linkModeSystem") : t("linkModeProvider")}
                  </div>
                  {s.kind === "gdrive" && s.config.auth === "oauth" && (
                    <div className="flex items-center gap-2 text-sm">
                      <span className={s.config.google_connected ? "text-success" : "text-warning"}>
                        {s.config.google_connected ? t("googleConnected") : t("googleNotConnected")}
                      </span>
                      <Button size="sm" variant="outline" className="ml-auto"
                        onClick={() => google.mutate(s.id, { onSuccess: (r) => { window.location.href = r.url; } })}>{t("googleConnect")}</Button>
                    </div>
                  )}
                  {s.last_error === "not_configured" && (
                    <Button size="sm" className="w-fit" onClick={() => setDraft({ id: s.id, name: s.name, kind: s.kind, base_folder: s.base_folder,
                      link_mode: s.link_mode, is_fallback: s.is_fallback, enabled: s.enabled, is_primary: s.is_primary, config: { ...s.config } })}>
                      {t("enterCredentials")}
                    </Button>
                  )}
                  <div className="flex flex-wrap gap-1.5">
                    <Button size="sm" variant="outline" disabled={test.isPending} onClick={() => test.mutate(s.id)}><Plug className="size-4" />{t("testConn")}</Button>
                    <Button size="sm" variant="outline" onClick={() => setDraft({ id: s.id, name: s.name, kind: s.kind, base_folder: s.base_folder,
                      link_mode: s.link_mode, is_fallback: s.is_fallback, enabled: s.enabled, is_primary: s.is_primary, config: { ...s.config } })}>
                      <Pencil className="size-4" />{t("edit")}
                    </Button>
                    {!s.is_primary && <Button size="sm" variant="outline" onClick={() => primary.mutate(s.id)}><Star className="size-4" />{t("makePrimary")}</Button>}
                    {!s.files && <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setDel(s)}><Trash2 className="size-4" />{t("delete")}</Button>}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </QrGuard>
      <StorageDialog draft={draft} setDraft={setDraft} />
      <ConfirmDialog open={!!del} onOpenChange={(v) => !v && setDel(null)} title={`${t("delete")}: ${del?.name}`} description={t("areYouSure")}
        destructive onConfirm={() => del && remove.mutate(del.id, { onSuccess: () => setDel(null) })} />
    </Page>
  );
}

export function StorageDialog({ draft, setDraft, onSaved }: { draft: Draft | null; setDraft: (d: Draft | null) => void; onSaved?: () => void }) {
  const t = useQt();
  const kinds = useQr<StorageKind[]>(["storage-kinds"], "storages/kinds");
  const [check, setCheck] = useState<Check>(null);
  const [testing, setTesting] = useState(false);
  const save = useQrAction(async (d: Draft) => {
    const body = { name: d.name, kind: d.kind, base_folder: d.base_folder, link_mode: d.link_mode, is_fallback: d.is_fallback,
      enabled: d.enabled, is_primary: d.is_primary || undefined, config: d.config };
    return (await (d.id ? qrApi.patch<QrStorage>(`storages/${d.id}`, body) : qrApi.post<QrStorage>("storages", body))).data;
  }, (r) => (r.check && !r.check.ok ? undefined : t("saved")));
  if (!draft) return null;
  const kind = kinds.data?.find((k) => k.kind === draft.kind);
  const setCfg = (k: string, v: unknown) => setDraft({ ...draft, config: { ...draft.config, [k]: v } });
  const runTest = async () => {
    setTesting(true);
    try {
      const body = { kind: draft.kind, base_folder: draft.base_folder, config: draft.config };
      const r = draft.id ? (await qrApi.patch<QrStorage>(`storages/${draft.id}`, body)).data.check : (await qrApi.post<Check>("storages/test", body)).data;
      setCheck(r ?? null);
    } catch (e) {
      setCheck({ ok: false, title: qrError(e) });
    } finally {
      setTesting(false);
    }
  };
  const checkText = check && !check.ok ? (check.kind ? errorText(t, { kind: check.kind, title: check.title ?? "", hint: check.hint ?? "" }) : { title: check.title, hint: check.hint }) : null;

  return (
    <Dialog open onOpenChange={(v) => { if (!v) { setDraft(null); setCheck(null); } }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{draft.id ? t("edit") : t("addStorage")}</DialogTitle>
          <DialogDescription>{t("stoDesc")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          {!draft.id && (
            <FormRow label={t("stoKind")}>
              <div className="grid grid-cols-2 gap-2">
                {kinds.data?.map((k) => (
                  <button key={k.kind} type="button" onClick={() => { setDraft({ ...draft, kind: k.kind, config: {}, link_mode: k.links ? "provider" : "system" }); setCheck(null); }}
                    className={cn("flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left text-sm", draft.kind === k.kind && "border-primary bg-primary/5")}>
                    {k.kind === "synology" ? <Server className="size-4" /> : <HardDrive className="size-4" />}{k.label}
                  </button>
                ))}
              </div>
            </FormRow>
          )}
          <FormRow label={t("stoName")}><Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder={kind?.label} /></FormRow>
          {kind?.fields.filter((f) => !f.when || f.when === String(draft.config.auth ?? kind.fields.find((x) => x.key === "auth")?.default ?? "")).map((f) => f.type === "bool" ? (
            <label key={f.key} className="flex items-center justify-between gap-3 text-sm">
              <span className="flex items-center gap-1.5">{f.label}</span>
              <Switch checked={(draft.config[f.key] ?? f.default ?? true) as boolean} onCheckedChange={(v) => setCfg(f.key, v)} />
            </label>
          ) : f.type === "select" ? (
            <FormRow key={f.key} label={f.label} help={f.help}>
              <Select value={String(draft.config[f.key] ?? f.default ?? "")} onValueChange={(v) => setCfg(f.key, v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{f.options?.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
              </Select>
            </FormRow>
          ) : f.type === "textarea" ? (
            <FormRow key={f.key} label={f.label} help={f.help}
              hint={f.secret && draft.id ? (draft.config[`${f.key}_set`] ? `${t("set")} — ${t("secretKeep")}` : t("notSet")) : undefined}>
              <Textarea rows={5} className="font-mono text-xs" placeholder={f.placeholder} value={String(draft.config[f.key] ?? "")}
                onChange={(e) => setCfg(f.key, e.target.value)} />
            </FormRow>
          ) : (
            <FormRow key={f.key} label={f.label} help={f.help}
              hint={f.secret && draft.id ? (draft.config[`${f.key}_set`] ? `${t("set")} — ${t("secretKeep")}` : t("notSet")) : undefined}>
              <Input type={f.secret ? "password" : "text"} autoComplete={f.secret ? "new-password" : "off"} placeholder={f.placeholder}
                value={String(draft.config[f.key] ?? "")} onChange={(e) => setCfg(f.key, e.target.value)} />
            </FormRow>
          ))}
          <FormRow label={t("baseFolder")} help={t("baseFolderHint")}><Input value={draft.base_folder} onChange={(e) => setDraft({ ...draft, base_folder: e.target.value })} /></FormRow>
          {kind?.links && (
            <FormRow label={t("linkMode")} help={t("linkModeHint")}>
              <Select value={draft.link_mode} onValueChange={(v) => setDraft({ ...draft, link_mode: v as Draft["link_mode"] })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="provider">{t("linkModeProvider")}</SelectItem>
                  <SelectItem value="system">{t("linkModeSystem")}</SelectItem>
                </SelectContent>
              </Select>
            </FormRow>
          )}
          <label className="flex items-center justify-between gap-3 text-sm"><span>{t("fallback")}<span className="block text-xs text-muted-foreground">{t("fallbackHint")}</span></span>
            <Switch checked={draft.is_fallback} onCheckedChange={(v) => setDraft({ ...draft, is_fallback: v })} /></label>
          {draft.id && <label className="flex items-center justify-between gap-3 text-sm">{t("enabled")}
            <Switch checked={draft.enabled} onCheckedChange={(v) => setDraft({ ...draft, enabled: v })} /></label>}
          {check && (
            <div className={cn("rounded-lg border px-3 py-2 text-sm", check.ok ? "border-success/30 bg-success/5" : "border-destructive/30 bg-destructive/5")}>
              {check.ok ? <span className="flex items-center gap-2 text-success"><CheckCircle2 className="size-4" />{t("connOk", { ms: check.latency_ms ?? 0 })}</span> : (
                <><span className="flex items-center gap-2 font-medium text-destructive"><XCircle className="size-4" />{checkText?.title}</span>
                  {checkText?.hint && <span className="mt-1 block text-xs text-muted-foreground">{checkText.hint}</span>}</>
              )}
            </div>
          )}
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={runTest} disabled={testing}><Plug className="size-4" />{t("testConn")}</Button>
          <Button disabled={save.isPending} onClick={() => save.mutate(draft, { onSuccess: (r) => {
            if (r.check && !r.check.ok) { setCheck({ ...r.check, kind: r.last_error }); return; }
            setDraft(null); setCheck(null); onSaved?.();
          } })}>{t("save")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
