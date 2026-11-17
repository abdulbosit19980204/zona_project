"use client";

import {
  CheckCircle2, CircleX, Download, ExternalLink, FileWarning, FolderInput, KeyRound, Link2, Link2Off, Pencil, Printer,
  RefreshCw, RotateCcw, Trash2,
} from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useQr, useQrAction } from "@/hooks/use-qrdrive";
import { blobUrl, download, formatBytes, qrApi, type QrFileDetail } from "@/lib/api/qrdrive";
import { cn } from "@/lib/utils";

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

  const act = useQrAction(async (fn: () => Promise<unknown>) => fn(), t("saved"));
  const run = (fn: () => Promise<unknown>) => act.mutate(fn, { onSuccess: () => setDialog(null) });
  const err = errorText(t, f?.error);

  return (
    <Sheet open={fileId !== null} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="break-all pr-6">{f?.original_name ?? t("loading")}</SheetTitle>
          {f && <SheetDescription className="flex flex-wrap items-center gap-2"><StatusBadge status={f.status} />{f.employee_name} · {formatBytes(f.size)} · {fmtDate(f.created_at)}</SheetDescription>}
        </SheetHeader>
        <div className="grid gap-5 px-4 pb-6">
          <QrGuard query={q}>
            {f && (
              <>
                {err && (
                  <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
                    <div className="flex items-center gap-2 font-medium text-destructive"><FileWarning className="size-4" />{err.title}</div>
                    <div className="mt-1 text-muted-foreground">{err.hint}</div>
                    {f.status === "failed" && (
                      <Button size="sm" className="mt-2" onClick={() => run(() => qrApi.post(`files/${f.id}/retry`))}><RefreshCw className="size-4" />{t("retryOne")}</Button>
                    )}
                  </div>
                )}
                {f.duplicate_of && <p className="text-xs text-muted-foreground">{t("duplicateOf", { id: f.duplicate_of })}</p>}

                {f.url ? (
                  <div className="grid gap-4 sm:grid-cols-[160px_1fr]">
                    <AuthImage path={`files/${f.id}/qr.png`} params={{ size: 400 }} alt="QR" className="w-40 rounded-lg border bg-white p-1" />
                    <div className="grid content-start gap-2 text-sm">
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        {f.link_kind === "system" ? t("linkSystem") : t("linkProvider")}
                        {f.visibility && (
                          <span className={cn("rounded-full px-2 py-0.5 font-medium", f.visibility === "private" ? "bg-violet/15 text-violet" : "bg-success/15 text-success")}>
                            {f.visibility === "private" ? "🔒 " + t("visPrivateShort") : "🌐 " + t("visPublicShort")}
                          </span>
                        )}
                      </div>
                      <a href={f.url} target="_blank" rel="noreferrer" className="break-all text-primary hover:underline">{f.url}</a>
                      <div className="text-xs text-muted-foreground">
                        {t("expires")}: {f.expires_at ? fmtDate(f.expires_at, false) : t("noExpiry")}
                        {f.has_password && <> · <KeyRound className="inline size-3" /> {t("passwordSet")}</>}
                        {f.link_kind === "system" && <> · {t("downloads", { n: f.downloads })}</>}
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        <CopyButton text={f.url} />
                        <Button size="sm" variant="outline" asChild><a href={f.url} target="_blank" rel="noreferrer"><ExternalLink className="size-4" />{t("open")}</a></Button>
                        <Button size="sm" variant="outline" onClick={() => download(`files/${f.id}/qr.png`, `qr-${f.id}.png`)}><Download className="size-4" />{t("qrPng")}</Button>
                        <Button size="sm" variant="outline" onClick={() => printQr(f.id)}><Printer className="size-4" />{t("qrPdf")}</Button>
                      </div>
                    </div>
                  </div>
                ) : (
                  f.status === "delivered" && <p className="text-sm text-muted-foreground">{t("linkNone")}</p>
                )}

                {f.status === "delivered" && !f.deleted_at && (
                  <div className="flex flex-wrap gap-1.5">
                    <Button size="sm" variant="outline" onClick={() => { setDays(""); setPassword(""); setVis(f.visibility || ""); setDialog("link"); }}><RefreshCw className="size-4" />{t("refreshLink")}</Button>
                    {f.url && <Button size="sm" variant="outline" onClick={() => setDialog("revoke")}><Link2Off className="size-4" />{t("revokeLink")}</Button>}
                    <Button size="sm" variant="outline" onClick={() => { setName(f.stored_name || f.original_name); setDialog("rename"); }}><Pencil className="size-4" />{t("rename")}</Button>
                    <Button size="sm" variant="outline" onClick={() => { setFolder(f.remote_path.split("/").slice(0, -1).join("/")); setDialog("move"); }}><FolderInput className="size-4" />{t("move")}</Button>
                    <Button size="sm" variant="outline" onClick={() => download(`files/${f.id}/content`, f.stored_name || f.original_name, { download: true })}><Download className="size-4" />{t("download")}</Button>
                  </div>
                )}

                {f.status === "delivered" && <div><div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("preview")}</div><Preview file={f} /></div>}

                <div className="grid gap-1 rounded-lg border p-3 text-sm">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("info")}</div>
                  <Row k={t("where")} v={f.remote_path || "—"} />
                  <Row k={t("colStorage")} v={f.storage_name || "—"} />
                  <Row k={t("colSource")} v={t(`src_${f.source}` as QKey) + (f.actor ? ` · ${f.actor}` : "")} />
                  {f.caption && <Row k="Caption" v={f.caption} />}
                  {f.attempts > 0 && <Row k="" v={t("attempts", { n: f.attempts })} />}
                </div>

                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("history")}</div>
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
                </div>

                <div className="flex flex-wrap gap-2 border-t pt-4">
                  {f.deleted_at ? (
                    <>
                      <Button variant="outline" onClick={() => run(() => qrApi.post(`files/${f.id}/restore`))}><RotateCcw className="size-4" />{t("restore")}</Button>
                      <Button variant="destructive" onClick={() => setDialog("purge")}><Trash2 className="size-4" />{t("purge")}</Button>
                    </>
                  ) : (
                    <Button variant="outline" onClick={() => run(() => qrApi.delete(`files/${f.id}`))}><Trash2 className="size-4" />{t("toTrash")}</Button>
                  )}
                </div>

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
                    {dialog === "move" && <FormRow label={t("targetFolder")}><Input value={folder} onChange={(e) => setFolder(e.target.value)} /></FormRow>}
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

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-2">
      <span className="text-muted-foreground">{k}</span>
      <span className="break-all">{v}</span>
    </div>
  );
}
