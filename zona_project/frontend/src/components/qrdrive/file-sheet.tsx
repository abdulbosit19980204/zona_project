"use client";

import {
  CheckCircle2, CircleX, Download, ExternalLink, FileText, FileWarning, FolderInput, FolderOpen, KeyRound, Link2, Link2Off, Pencil,
  Printer, RefreshCw, RotateCcw, Trash2, type LucideIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useQr, useQrAction } from "@/hooks/use-qrdrive";
import { blobUrl, download, formatBytes, qrApi, type QrFileDetail, type QrStorage } from "@/lib/api/qrdrive";
import { cn } from "@/lib/utils";

import { FolderPicker } from "./folder-picker";
import { AuthImage, ConfirmDialog, CopyButton, FormRow, QrGuard, StatusBadge, fmtDate, useAuthBlob, useDuration } from "./common";
import { errorText, useQt, type QKey } from "./i18n";

function Preview({ file }: { file: QrFileDetail }) {
  const t = useQt();
  const kind = file.mime.startsWith("image/") ? "image" : file.mime === "application/pdf" ? "pdf"
    : file.mime.startsWith("video/") ? "video" : file.mime.startsWith("audio/") ? "audio" : null;
  const small = (file.size ?? 0) < 60 * 1024 * 1024;
  const { url, error } = useAuthBlob(kind && small && file.remote_path ? `files/${file.id}/content` : null);
  if (!kind || !small || !file.remote_path) return <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">{t("previewNA")}</p>;
  if (error) return <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">{t("err_storage_down")}</p>;
  if (!url) return <Skeleton className="h-56 rounded-lg" />;
  if (kind === "image") {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt={file.original_name} className="max-h-80 w-full rounded-lg border object-contain" />;
  }
  if (kind === "pdf") return <iframe src={url} title={file.original_name} className="h-96 w-full rounded-lg border" />;
  if (kind === "video") return <video src={url} controls className="max-h-80 w-full rounded-lg border" />;
  return <audio src={url} controls className="w-full" />;
}

async function printQr(id: number) {
  const url = await blobUrl(`files/${id}/qr.pdf`);
  const w = window.open(url, "_blank");
  if (w) w.addEventListener("load", () => w.print());
}

/** Fayl paneli: ko'rish, QR, havola, nom/ko'chirish, savat, tarix. */
export function FileSheet({ fileId, onClose }: { fileId: number | null; onClose: () => void }) {
  const t = useQt();
  const dur = useDuration();
  const q = useQr<QrFileDetail>(["file", fileId], `files/${fileId}`, undefined, { enabled: fileId !== null });
  const f = q.data;
  const [dialog, setDialog] = useState<null | "link" | "rename" | "move" | "purge" | "revoke">(null);
  const [days, setDays] = useState("");
  const [vis, setVis] = useState<string>("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [folder, setFolder] = useState("");
  const storages = useQr<QrStorage[]>(["storages"], "storages", undefined, { enabled: dialog === "move" });

  const act = useQrAction(async (fn: () => Promise<unknown>) => fn(), t("saved"));
  const run = (fn: () => Promise<unknown>) => act.mutate(fn, { onSuccess: () => setDialog(null) });
  const err = errorText(t, f?.error);

  return (
    <Sheet open={fileId !== null} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader className="border-b pb-4">
          <SheetTitle className="flex items-start gap-2 pr-6 text-base leading-snug">
            {f?.kind === "folder" ? <FolderOpen className="mt-0.5 size-5 shrink-0 text-primary" /> : <FileText className="mt-0.5 size-5 shrink-0 text-muted-foreground" />}
            <span className="break-words">{f?.original_name ?? t("loading")}</span>
          </SheetTitle>
          {f && (
            <SheetDescription asChild>
              <div className="grid gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <StatusBadge status={f.status} />
                  {f.visibility && <Chip tone={f.visibility === "private" ? "violet" : "success"}>{f.visibility === "private" ? "🔒 " + t("visPrivateShort") : "🌐 " + t("visPublicShort")}</Chip>}
                  {f.kind === "folder" && <Chip tone="primary">{t("folderKind")} · {f.items.length}</Chip>}
                  {f.version > 1 && <Chip>{t("versionN", { n: f.version })}</Chip>}
                  {f.has_password && <Chip><KeyRound className="size-3" />{t("password")}</Chip>}
                </div>
                <div className="text-xs text-muted-foreground">{[f.employee_name, formatBytes(f.size), fmtDate(f.created_at)].filter(Boolean).join(" · ")}</div>
              </div>
            </SheetDescription>
          )}
        </SheetHeader>
        <div className="grid gap-4 px-4 pb-6">
          <QrGuard query={q}>
            {f && (
              <>
                {err && (
                  <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm">
                    <div className="flex items-center gap-2 font-medium text-destructive"><FileWarning className="size-4" />{err.title}</div>
                    <div className="mt-1 text-muted-foreground">{err.hint}</div>
                    {f.status === "failed" && (
                      <Button size="sm" className="mt-2" onClick={() => run(() => qrApi.post(`files/${f.id}/retry`))}><RefreshCw className="size-4" />{t("retryOne")}</Button>
                    )}
                  </div>
                )}
                {f.duplicate_of && <p className="text-xs text-muted-foreground">{t("duplicateOf", { id: f.duplicate_of })}</p>}

                {f.url ? (
                  <div className="grid gap-4 rounded-xl border bg-card p-4 sm:grid-cols-[136px_minmax(0,1fr)]">
                    <div className="grid content-start gap-2">
                      <AuthImage path={`files/${f.id}/qr.png`} params={{ size: 400 }} alt="QR" className="aspect-square w-full rounded-lg border bg-white p-1.5" />
                      <div className="grid grid-cols-2 gap-1.5">
                        <Button size="sm" variant="outline" className="px-0" onClick={() => download(`files/${f.id}/qr.png`, `qr-${f.id}.png`)}><Download className="size-3.5" />PNG</Button>
                        <Button size="sm" variant="outline" className="px-0" onClick={() => printQr(f.id)}><Printer className="size-3.5" />PDF</Button>
                      </div>
                    </div>
                    <div className="grid min-w-0 content-start gap-2.5">
                      <div className="text-xs font-medium text-muted-foreground">{f.link_kind === "system" ? t("linkSystem") : t("linkProvider")}</div>
                      <div className="flex min-w-0 items-center gap-1 rounded-lg border bg-muted/40 py-1 pl-2.5 pr-1">
                        <a href={f.url} target="_blank" rel="noreferrer" title={f.url} className="min-w-0 flex-1 truncate font-mono text-xs text-primary hover:underline">{f.url}</a>
                        <CopyButton text={f.url} size="icon" />
                        <Button size="icon" variant="ghost" asChild aria-label={t("open")}><a href={f.url} target="_blank" rel="noreferrer"><ExternalLink className="size-4" /></a></Button>
                      </div>
                      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                        <dt className="text-muted-foreground">{t("expires")}</dt><dd>{f.expires_at ? fmtDate(f.expires_at, false) : t("noExpiry")}</dd>
                        {f.link_kind === "system" && <><dt className="text-muted-foreground">{t("downloadsLabel")}</dt><dd>{f.downloads}</dd></>}
                        <dt className="text-muted-foreground">{t("where")}</dt><dd className="truncate" title={f.remote_path}>{f.remote_path}</dd>
                      </dl>
                    </div>
                  </div>
                ) : (
                  f.status === "delivered" && <p className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">{t("linkNone")}</p>
                )}

                {f.status === "delivered" && !f.deleted_at && (
                  <Section title={t("actions")}>
                    <div className="grid grid-cols-2 gap-2">
                      <ActionButton icon={RefreshCw} onClick={() => { setDays(""); setPassword(""); setVis(f.visibility || ""); setDialog("link"); }}>{t("refreshLink")}</ActionButton>
                      <ActionButton icon={Link2Off} disabled={!f.url} onClick={() => setDialog("revoke")}>{t("revokeLink")}</ActionButton>
                      <ActionButton icon={Pencil} onClick={() => { setName(f.stored_name || f.original_name); setDialog("rename"); }}>{t("rename")}</ActionButton>
                      <ActionButton icon={FolderInput} onClick={() => { setFolder(f.remote_path.split("/").slice(0, -1).join("/")); setDialog("move"); }}>{t("move")}</ActionButton>
                      {f.kind !== "folder" && <ActionButton icon={Download} onClick={() => download(`files/${f.id}/content`, f.stored_name || f.original_name, { download: true })}>{t("download")}</ActionButton>}
                      <ActionButton icon={Trash2} danger onClick={() => run(() => qrApi.delete(`files/${f.id}`))}>{t("toTrash")}</ActionButton>
                    </div>
                  </Section>
                )}

                {f.kind === "folder" && (
                  <Section title={t("folderItems", { n: f.items.length })}>
                    <ul className="max-h-72 overflow-y-auto rounded-lg border text-sm">
                      {f.items.map((it, i) => (
                        <li key={it.name} className="flex items-center gap-2 border-b px-3 py-1.5 last:border-0">
                          <span className="min-w-0 flex-1 truncate" title={it.name}>{it.name}</span>
                          <span className="font-mono text-xs text-muted-foreground">{formatBytes(it.size)}</span>
                          <Button size="icon" variant="ghost" className="size-7" aria-label={t("download")}
                            onClick={() => download(`files/${f.id}/items/${i}`, it.name.split("/").pop() || it.name, { download: true })}>
                            <Download className="size-3.5" />
                          </Button>
                        </li>
                      ))}
                    </ul>
                  </Section>
                )}

                {f.versions.length > 0 && (
                  <Section title={t("versions")}>
                    <ul className="grid gap-1 text-sm">
                      {f.versions.map((v) => (
                        <li key={v.id} className={cn("flex items-center gap-2 rounded-md px-2 py-1", v.id === f.id && "bg-muted")}>
                          <span className="font-mono text-xs">{t("versionN", { n: v.version })}</span>
                          {v.current && <span className="rounded-full bg-success/15 px-1.5 text-[10px] text-success">{t("currentVersion")}</span>}
                          <span className="text-xs text-muted-foreground">{fmtDate(v.created_at)} · {v.actor || "—"} · {formatBytes(v.size)}</span>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-1 text-xs text-muted-foreground">{t("replaceHint")}</p>
                  </Section>
                )}

                {f.status === "delivered" && f.kind !== "folder" && <Section title={t("preview")}><Preview file={f} /></Section>}

                <Section title={t("info")}>
                  <div className="grid gap-1 rounded-lg border p-3 text-sm">
                  <Row k={t("where")} v={f.remote_path || "—"} />
                  <Row k={t("colStorage")} v={f.storage_name || "—"} />
                  <Row k={t("colSource")} v={t(`src_${f.source}` as QKey) + (f.actor ? ` · ${f.actor}` : "")} />
                  {f.caption && <Row k="Caption" v={f.caption} />}
                  {f.attempts > 0 && <Row k="" v={t("attempts", { n: f.attempts })} />}
                  </div>
                </Section>

                <Section title={t("history")}>
                  <ol className="relative ml-2 border-l">
                    {f.events.map((e, i) => (
                      <li key={i} className="mb-3 ml-4">
                        <span className={cn("absolute -left-[7px] grid size-3.5 place-items-center rounded-full bg-background")}>
                          {e.ok ? <CheckCircle2 className="size-3.5 text-success" /> : <CircleX className="size-3.5 text-destructive" />}
                        </span>
                        <div className="text-sm">{t(`stage_${e.stage}` as QKey)}{e.duration_ms !== null && <span className="text-muted-foreground"> · {dur(e.duration_ms)}</span>}</div>
                        <div className="text-xs text-muted-foreground">{fmtDate(e.at)}{e.message && !e.ok ? ` · ${e.message}` : ""}</div>
                      </li>
                    ))}
                  </ol>
                </Section>

                {f.deleted_at && (
                  <div className="flex flex-wrap gap-2 border-t pt-4">
                    <Button variant="outline" onClick={() => run(() => qrApi.post(`files/${f.id}/restore`))}><RotateCcw className="size-4" />{t("restore")}</Button>
                    <Button variant="destructive" onClick={() => setDialog("purge")}><Trash2 className="size-4" />{t("purge")}</Button>
                  </div>
                )}

                <Dialog open={dialog === "link" || dialog === "rename" || dialog === "move"} onOpenChange={(v) => !v && setDialog(null)}>
                  <DialogContent className="sm:max-w-md">
                    <DialogHeader><DialogTitle>{dialog === "link" ? t("linkSettings") : dialog === "rename" ? t("rename") : t("move")}</DialogTitle></DialogHeader>
                    {dialog === "link" && (
                      <div className="grid gap-3">
                        <FormRow label={t("visibility")} hint={t("visHint")}>
                          <Select value={vis || "public"} onValueChange={setVis}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="public">{t("visPublic")}</SelectItem>
                              <SelectItem value="private">{t("visPrivate")}</SelectItem>
                            </SelectContent>
                          </Select>
                        </FormRow>
                        <FormRow label={t("expireDays")}><Input type="number" min={0} value={days} onChange={(e) => setDays(e.target.value)} placeholder="0" /></FormRow>
                        <FormRow label={t("newPassword")}><Input value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" /></FormRow>
                      </div>
                    )}
                    {dialog === "rename" && <FormRow label={t("newName")}><Input value={name} onChange={(e) => setName(e.target.value)} /></FormRow>}
                    {dialog === "move" && (f.storage_id ? (
                      <FolderPicker storageId={f.storage_id} root={storages.data?.find((x) => x.id === f.storage_id)?.base_folder || "/"}
                        current={f.remote_path.split("/").slice(0, -1).join("/")} value={folder} onChange={setFolder} />
                    ) : <FormRow label={t("targetFolder")}><Input value={folder} onChange={(e) => setFolder(e.target.value)} /></FormRow>)}
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setDialog(null)}>{t("cancel")}</Button>
                      <Button disabled={act.isPending} onClick={() => run(() =>
                        dialog === "link" ? qrApi.post(`files/${f.id}/link`, { expire_days: days === "" ? null : Number(days), password, visibility: vis || null })
                          : dialog === "rename" ? qrApi.post(`files/${f.id}/rename`, { name })
                            : qrApi.post(`files/${f.id}/move`, { folder }))}>
                        {dialog === "link" ? <Link2 className="size-4" /> : null}{t("save")}
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
                <ConfirmDialog open={dialog === "revoke"} onOpenChange={(v) => !v && setDialog(null)} title={t("revokeLink")}
                  description={t("areYouSure")} destructive pending={act.isPending}
                  onConfirm={() => run(() => qrApi.delete(`files/${f.id}/link`))} />
                <ConfirmDialog open={dialog === "purge"} onOpenChange={(v) => !v && setDialog(null)} title={t("purge")}
                  description={t("purgeHint")} destructive pending={act.isPending} confirmLabel={t("purge")}
                  onConfirm={() => act.mutate(() => qrApi.delete(`files/${f.id}/purge`), { onSuccess: onClose })} />
              </>
            )}
          </QrGuard>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-2">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">{title}</h3>
      {children}
    </section>
  );
}

const CHIP_TONE = { default: "bg-muted text-foreground", success: "bg-success/15 text-success", violet: "bg-violet/15 text-violet", primary: "bg-primary/15 text-primary" };

function Chip({ tone = "default", children }: { tone?: keyof typeof CHIP_TONE; children: ReactNode }) {
  return <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium", CHIP_TONE[tone])}>{children}</span>;
}

function ActionButton({ icon: Icon, children, onClick, disabled, danger }: {
  icon: LucideIcon; children: ReactNode; onClick: () => void; disabled?: boolean; danger?: boolean;
}) {
  return (
    <Button variant="outline" disabled={disabled} onClick={onClick}
      className={cn("h-9 justify-start gap-2 px-3 text-left font-normal", danger && "text-destructive hover:text-destructive")}>
      <Icon className="size-4 shrink-0" /><span className="truncate">{children}</span>
    </Button>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-2">
      <span className="text-muted-foreground">{k}</span>
      <span className="break-all">{v}</span>
    </div>
  );
}
