"use client";

import {
  Archive, Ban, CheckCircle2, Download, FileUp, Link2, Plus, Printer, Search, Send, Unlink, Upload, UserRound, Users,
} from "lucide-react";
import { useRef, useState } from "react";

import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useQr, useQrAction } from "@/hooks/use-qrdrive";
import {
  download, formatBytes, qrApi, type Invite, type QrEmployee, type QrEmployeeDetail, type QrStorage,
} from "@/lib/api/qrdrive";
import { cn } from "@/lib/utils";

import { ConfirmDialog, CopyButton, FormRow, QrGuard, StatusBadge, fmtDate } from "./common";
import { FileSheet } from "./file-sheet";
import { UploadDialog } from "./files";
import { useQt, type QKey } from "./i18n";

const EMP_TONE: Record<string, string> = {
  active: "bg-success/15 text-success", blocked: "bg-destructive/15 text-destructive", archived: "bg-muted text-muted-foreground",
  pending: "bg-warning/15 text-warning", rejected: "bg-muted text-muted-foreground", detached: "bg-muted text-muted-foreground",
};

export function EmpBadge({ status }: { status: string }) {
  const t = useQt();
  return <Badge className={cn("border-0", EMP_TONE[status])}>{t(`st_${status}` as QKey)}</Badge>;
}

type Form = { full_name: string; department: string; position: string; phone: string; folder: string; storage_id: string; note: string };
const EMPTY: Form = { full_name: "", department: "", position: "", phone: "", folder: "", storage_id: "default", note: "" };

export function QrEmployees() {
  const t = useQt();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("active,blocked");
  const [openId, setOpenId] = useState<number | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [invites, setInvites] = useState<Invite[] | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const list = useQr<QrEmployee[]>(["employees"], "employees", { q: q || undefined, status });
  const storages = useQr<QrStorage[]>(["storages"], "storages");
  const create = useQrAction(async (f: Form) => (await qrApi.post<QrEmployee>("employees", {
    ...f, storage_id: f.storage_id === "default" ? null : Number(f.storage_id) })).data, t("saved"));
  const importer = useQrAction(async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return (await qrApi.post<{ created: number; updated: number }>("employees/import", fd)).data;
  }, (r) => t("imported", r));
  const bulkInvite = useQrAction(async () => (await qrApi.post<Invite[]>("employees/invites", { ids: selected })).data);
  const rows = list.data ?? [];

  return (
    <Page>
      <PageHeader title={t("empTitle")} description={t("empDesc")} actions={
        <>
          <input ref={fileInput} type="file" accept=".xlsx,.csv" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) importer.mutate(f); e.target.value = ""; }} />
          <Button variant="outline" onClick={() => fileInput.current?.click()} title={t("importHint")}><FileUp className="size-4" />{t("import")}</Button>
          <Button variant="outline" onClick={() => download("employees/export.xlsx", "qrdrive-xodimlar.xlsx")}><Download className="size-4" />{t("export")}</Button>
          <Button onClick={() => setForm(EMPTY)}><Plus className="size-4" />{t("addEmployee")}</Button>
        </>
      } />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="pl-8" />
        </div>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="active,blocked">{t("st_active")} + {t("st_blocked")}</SelectItem>
            <SelectItem value="active">{t("st_active")}</SelectItem>
            <SelectItem value="blocked">{t("st_blocked")}</SelectItem>
            <SelectItem value="archived">{t("st_archived")}</SelectItem>
            <SelectItem value="active,blocked,archived">{t("all")}</SelectItem>
          </SelectContent>
        </Select>
        {selected.length > 0 && (
          <Button variant="outline" onClick={() => bulkInvite.mutate(undefined, { onSuccess: setInvites })} title={t("printInvitesHint")}>
            <Printer className="size-4" />{t("printInvites")} ({selected.length})
          </Button>
        )}
      </div>
      <QrGuard query={list}>
        {!rows.length ? <EmptyState icon={Users} title={t("emptyHint")} action={<Button onClick={() => setForm(EMPTY)}><Plus className="size-4" />{t("addEmployee")}</Button>} /> : (
          <Card className="gap-0 overflow-hidden p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10"><Checkbox checked={rows.every((r) => selected.includes(r.id))}
                    onCheckedChange={(v) => setSelected(v ? rows.map((r) => r.id) : [])} /></TableHead>
                  <TableHead>{t("fullName")}</TableHead>
                  <TableHead>{t("department")}</TableHead>
                  <TableHead>{t("accounts")}</TableHead>
                  <TableHead>{t("folder")}</TableHead>
                  <TableHead className="text-right">{t("filesOf")}</TableHead>
                  <TableHead className="w-28">{t("colStatus")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((e) => (
                  <TableRow key={e.id} className="cursor-pointer" onClick={() => setOpenId(e.id)}>
                    <TableCell onClick={(ev) => ev.stopPropagation()}>
                      <Checkbox checked={selected.includes(e.id)} onCheckedChange={(v) => setSelected((s) => (v ? [...s, e.id] : s.filter((x) => x !== e.id)))} />
                    </TableCell>
                    <TableCell><div className="font-medium">{e.full_name}</div><div className="text-xs text-muted-foreground">{e.position}</div></TableCell>
                    <TableCell>{e.department || "—"}</TableCell>
                    <TableCell className="text-sm">{e.accounts.filter((a) => a.status === "active").map((a) => a.username ? `@${a.username}` : a.telegram_id).join(", ")
                      || <span className="text-muted-foreground">{t("noAccount")}</span>}</TableCell>
                    <TableCell className="font-mono text-xs">{e.folder || "—"}</TableCell>
                    <TableCell className="text-right text-sm">{e.files_count}<div className="text-xs text-muted-foreground">{formatBytes(e.files_size)}</div></TableCell>
                    <TableCell><EmpBadge status={e.status} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </QrGuard>
      <EmployeeForm form={form} setForm={setForm} storages={storages.data ?? []} pending={create.isPending}
        onSubmit={(f) => create.mutate(f, { onSuccess: (r) => { setForm(null); setOpenId(r.id); } })} />
      <EmployeeSheet id={openId} onClose={() => setOpenId(null)} storages={storages.data ?? []} />
      <InvitePrint invites={invites} onClose={() => setInvites(null)} />
    </Page>
  );
}

function EmployeeForm({ form, setForm, storages, onSubmit, pending, title }: {
  form: Form | null; setForm: (f: Form | null) => void; storages: QrStorage[]; onSubmit: (f: Form) => void; pending: boolean; title?: string;
}) {
  const t = useQt();
  if (!form) return null;
  const set = (k: keyof Form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  return (
    <Dialog open onOpenChange={(v) => !v && setForm(null)}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>{title ?? t("addEmployee")}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormRow label={t("fullName")} className="sm:col-span-2"><Input value={form.full_name} onChange={set("full_name")} autoFocus /></FormRow>
          <FormRow label={t("department")}><Input value={form.department} onChange={set("department")} /></FormRow>
          <FormRow label={t("position")}><Input value={form.position} onChange={set("position")} /></FormRow>
          <FormRow label={t("phone")}><Input value={form.phone} onChange={set("phone")} placeholder="+998" /></FormRow>
          <FormRow label={t("folder")} help={t("folderHint")}><Input value={form.folder} onChange={set("folder")} /></FormRow>
          <FormRow label={t("storage")} className="sm:col-span-2">
            <Select value={form.storage_id} onValueChange={(v) => setForm({ ...form, storage_id: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="default">{t("storageDefault")}</SelectItem>
                {storages.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </FormRow>
          <FormRow label={t("note")} className="sm:col-span-2"><Textarea value={form.note} onChange={set("note")} rows={2} /></FormRow>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setForm(null)}>{t("cancel")}</Button>
          <Button disabled={!form.full_name.trim() || pending} onClick={() => onSubmit(form)}>{t("save")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EmployeeSheet({ id, onClose, storages }: { id: number | null; onClose: () => void; storages: QrStorage[] }) {
  const t = useQt();
  const q = useQr<QrEmployeeDetail>(["employee", id], `employees/${id}`, undefined, { enabled: id !== null });
  const e = q.data;
  const [edit, setEdit] = useState<Form | null>(null);
  const [invite, setInvite] = useState<Invite | null>(null);
  const [fileId, setFileId] = useState<number | null>(null);
  const [upload, setUpload] = useState(false);
  const [confirm, setConfirm] = useState<null | "archived" | "blocked">(null);
  const save = useQrAction(async (f: Form) => qrApi.patch(`employees/${id}`, {
    ...f, storage_id: f.storage_id === "default" ? 0 : Number(f.storage_id) }), t("saved"));
  const status = useQrAction(async (s: string) => qrApi.post(`employees/${id}/status`, { status: s }), t("saved"));
  const inv = useQrAction(async () => (await qrApi.post<Invite>(`employees/${id}/invite`, { replace: true })).data);
  const detach = useQrAction(async (accId: number) => qrApi.delete(`employees/${id}/accounts/${accId}`), t("saved"));

  return (
    <Sheet open={id !== null} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2"><UserRound className="size-5" />{e?.full_name ?? t("loading")}</SheetTitle>
          {e && <SheetDescription className="flex flex-wrap items-center gap-2"><EmpBadge status={e.status} />{[e.department, e.position, e.phone].filter(Boolean).join(" · ")}</SheetDescription>}
        </SheetHeader>
        <div className="grid gap-5 px-4 pb-6">
          <QrGuard query={q}>
            {e && (
              <>
                <div className="flex flex-wrap gap-1.5">
                  <Button size="sm" onClick={() => inv.mutate(undefined, { onSuccess: setInvite })}><Link2 className="size-4" />{t("invite")}</Button>
                  <Button size="sm" variant="outline" onClick={() => setEdit({ full_name: e.full_name, department: e.department, position: e.position,
                    phone: e.phone, folder: e.folder, storage_id: e.storage_id ? String(e.storage_id) : "default", note: e.note })}>{t("edit")}</Button>
                  <Button size="sm" variant="outline" onClick={() => setUpload(true)}><Upload className="size-4" />{t("uploadBtn")}</Button>
                  {e.status === "active" ? (
                    <Button size="sm" variant="outline" onClick={() => setConfirm("blocked")}><Ban className="size-4" />{t("block")}</Button>
                  ) : (
                    <Button size="sm" variant="outline" onClick={() => status.mutate("active")}><CheckCircle2 className="size-4" />{t("unblock")}</Button>
                  )}
                  {e.status !== "archived" && <Button size="sm" variant="outline" onClick={() => setConfirm("archived")}><Archive className="size-4" />{t("archive")}</Button>}
                </div>

                <div className="grid grid-cols-3 gap-2 text-center">
                  <Stat label={t("filesOf")} value={e.files_count} />
                  <Stat label={t("colSize")} value={formatBytes(e.files_size)} />
                  <Stat label={t("lastFile")} value={e.last_file_at ? fmtDate(e.last_file_at, false) : "—"} />
                </div>

                <div className="grid gap-1 rounded-lg border p-3 text-sm">
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("folder")}</div>
                  <div className="font-mono">{e.folder || <span className="text-muted-foreground">{t("folderHint")}</span>}</div>
                  <div className="text-xs text-muted-foreground">{t("storage")}: {storages.find((s) => s.id === e.storage_id)?.name ?? t("storageDefault")}</div>
                </div>

                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("accounts")}</div>
                  {!e.all_accounts.length && <p className="text-sm text-muted-foreground">{t("noAccount")}</p>}
                  {e.all_accounts.map((a) => (
                    <div key={a.id} className="flex items-center gap-2 border-b py-2 text-sm last:border-0">
                      <span className="flex-1">{a.display}{a.username && <span className="text-muted-foreground"> @{a.username}</span>}
                        <span className="block text-xs text-muted-foreground">ID {a.telegram_id} · {fmtDate(a.last_seen)}</span></span>
                      <EmpBadge status={a.status} />
                      {a.status === "active" && <Button size="icon" variant="ghost" onClick={() => detach.mutate(a.id)} title={t("detach")}><Unlink className="size-4" /></Button>}
                    </div>
                  ))}
                </div>

                {!!e.history.length && (
                  <div>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("accHistory")}</div>
                    <ul className="grid gap-1 text-xs text-muted-foreground">
                      {e.history.slice(0, 15).map((h, i) => (
                        <li key={i}>{fmtDate(h.at)} · {h.account}: {t("fieldChanged", { field: h.field, old: h.old || "—", new: h.new || "—" })}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("filesOf")}</div>
                  {e.recent_files.map((f) => (
                    <button key={f.id} onClick={() => setFileId(f.id)} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-muted">
                      <span className="min-w-0 flex-1 truncate">{f.original_name}</span>
                      <span className="text-xs text-muted-foreground">{fmtDate(f.created_at, false)}</span>
                      <StatusBadge status={f.status} />
                    </button>
                  ))}
                </div>
              </>
            )}
          </QrGuard>
        </div>
        <EmployeeForm form={edit} setForm={setEdit} storages={storages} pending={save.isPending} title={t("edit")}
          onSubmit={(f) => save.mutate(f, { onSuccess: () => setEdit(null) })} />
        <InviteDialog invite={invite} onClose={() => setInvite(null)} />
        <FileSheet fileId={fileId} onClose={() => setFileId(null)} />
        {id !== null && <UploadDialog open={upload} onOpenChange={setUpload} employeeId={id} />}
        <ConfirmDialog open={confirm !== null} onOpenChange={(v) => !v && setConfirm(null)}
          title={confirm === "archived" ? t("archive") : t("block")} description={t("archiveHint")} destructive
          onConfirm={() => confirm && status.mutate(confirm, { onSuccess: () => setConfirm(null) })} />
      </SheetContent>
    </Sheet>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border px-2 py-2.5">
      <div className="font-mono text-lg font-semibold">{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

function InviteDialog({ invite, onClose }: { invite: Invite | null; onClose: () => void }) {
  const t = useQt();
  return (
    <Dialog open={!!invite} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("inviteTitle")}</DialogTitle>
          <DialogDescription>{t("inviteDesc")}</DialogDescription>
        </DialogHeader>
        {invite?.bot_missing ? <p className="text-sm text-warning">{t("inviteNoBot")}</p> : invite && (
          <div className="grid justify-items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`data:image/png;base64,${invite.qr_png}`} alt="QR" className="w-56 rounded-lg border bg-white p-1" />
            <a href={invite.link} target="_blank" rel="noreferrer" className="break-all text-center text-sm text-primary">{invite.link}</a>
            <div className="text-xs text-muted-foreground">{t("expires")}: {fmtDate(invite.expires_at)}</div>
            <div className="flex gap-2">
              <CopyButton text={invite.link} />
              <Button size="sm" variant="outline" asChild><a href={invite.link} target="_blank" rel="noreferrer"><Send className="size-4" />Telegram</a></Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Tanlangan xodimlar uchun taklif varaqlari — brauzerning chop etish oynasi orqali. */
function InvitePrint({ invites, onClose }: { invites: Invite[] | null; onClose: () => void }) {
  const t = useQt();
  const print = () => {
    if (!invites) return;
    const w = window.open("", "_blank");
    if (!w) return;
    const cards = invites.filter((i) => i.link).map((i) => `
      <div class="c"><img src="data:image/png;base64,${i.qr_png}"/><h3>${i.full_name.replace(/</g, "&lt;")}</h3>
      <p>${(i.department || "").replace(/</g, "&lt;")}</p><small>${i.link}</small></div>`).join("");
    w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>QR Drive</title><style>
      body{font-family:system-ui,sans-serif;margin:16px}.g{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
      .c{border:1px dashed #999;border-radius:10px;padding:12px;text-align:center;break-inside:avoid}
      img{width:180px}h3{margin:6px 0 2px;font-size:15px}p{margin:0;color:#555;font-size:12px}small{font-size:9px;word-break:break-all;color:#777}
      </style></head><body><div class="g">${cards}</div><script>onload=()=>print()</script></body></html>`);
    w.document.close();
  };
  return (
    <Dialog open={!!invites} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("printInvites")}</DialogTitle>
          <DialogDescription>{invites?.[0]?.bot_missing ? t("inviteNoBot") : t("printInvitesHint")}</DialogDescription>
        </DialogHeader>
        <p className="text-sm">{invites?.length ?? 0} · {t("expires")}: 24h</p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t("close")}</Button>
          <Button disabled={!invites?.length || invites[0]?.bot_missing} onClick={print}><Printer className="size-4" />{t("print")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
