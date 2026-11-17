"use client";

import {
  ChevronLeft, ChevronRight, Download, FileIcon, Folder, FolderOpen, RefreshCw, RotateCcw, Search, Table2, Trash2, Upload,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useRef, useState } from "react";

import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useQr, useQrAction } from "@/hooks/use-qrdrive";
import {
  download, formatBytes, qrApi, type Paged, type QrEmployee, type QrFile, type QrSettings, type QrStorage,
} from "@/lib/api/qrdrive";
import { cn } from "@/lib/utils";

import { ConfirmDialog, FormRow, QrGuard, StatusBadge, fmtDate } from "./common";
import { FileSheet } from "./file-sheet";
import { useQt, type QKey } from "./i18n";

const PAGE = 50;
const STATUSES = ["delivered", "failed", "retrying", "queued", "processing", "awaiting"] as const;
const TYPES = ["image", "video", "audio", "pdf", "other"] as const;

export function QrFiles() {
  const t = useQt();
  const params = useSearchParams();
  const [view, setView] = useState<"table" | "folders" | "trash">("table");
  const [openId, setOpenId] = useState<number | null>(params.get("file") ? Number(params.get("file")) : null);
  const [upload, setUpload] = useState(false);
  return (
    <Page>
      <PageHeader title={t("filesTitle")} description={t("filesDesc")}
        actions={<Button onClick={() => setUpload(true)}><Upload className="size-4" />{t("uploadBtn")}</Button>} />
      <Tabs value={view} onValueChange={(v) => setView(v as typeof view)} className="mb-4">
        <TabsList>
          <TabsTrigger value="table"><Table2 className="size-4" />{t("viewTable")}</TabsTrigger>
          <TabsTrigger value="folders"><FolderOpen className="size-4" />{t("viewFolders")}</TabsTrigger>
          <TabsTrigger value="trash"><Trash2 className="size-4" />{t("trash")}</TabsTrigger>
        </TabsList>
      </Tabs>
      {view === "folders" ? <FolderBrowser onOpen={setOpenId} /> : <FileTable trash={view === "trash"} onOpen={setOpenId} key={view} />}
      <FileSheet fileId={openId} onClose={() => setOpenId(null)} />
      <UploadDialog open={upload} onOpenChange={setUpload} />
    </Page>
  );
}

function FileTable({ trash, onOpen }: { trash: boolean; onOpen: (id: number) => void }) {
  const t = useQt();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const [source, setSource] = useState("all");
  const [type, setType] = useState("all");
  const [employee, setEmployee] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number[]>([]);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const filters = {
    q: q || undefined, status: status === "all" ? undefined : status, source: source === "all" ? undefined : source,
    type: type === "all" ? undefined : type, employee_id: employee === "all" ? undefined : employee,
    date_from: from || undefined, date_to: to || undefined, trash,
  };
  const query = useQr<Paged<QrFile>>(["files"], "files", { ...filters, page, page_size: PAGE }, { refetchInterval: 15_000 });
  const employees = useQr<QrEmployee[]>(["employees"], "employees");
  const settings = useQr<QrSettings>(["settings"], "settings");
  const bulk = useQrAction(async (action: string) => (await qrApi.post<{ done: number }>("files/bulk", { ids: selected, action })).data,
    (r) => `${t("done")}: ${r.done}`);
  const items = query.data?.items ?? [];
  const pages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PAGE));
  const allChecked = items.length > 0 && items.every((f) => selected.includes(f.id));
  const doBulk = (action: string) => bulk.mutate(action, { onSuccess: () => setSelected([]) });

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-64">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder={t("search")} className="pl-8" />
        </div>
        <Filter value={status} onChange={(v) => { setStatus(v); setPage(1); }} label={t("fltStatus")}
          options={STATUSES.map((s) => [s, t(`st_${s}` as QKey)])} />
        <Filter value={source} onChange={(v) => { setSource(v); setPage(1); }} label={t("fltSource")}
          options={(["telegram", "web", "api"] as const).map((s) => [s, t(`src_${s}` as QKey)])} />
        <Filter value={type} onChange={(v) => { setType(v); setPage(1); }} label={t("fltType")}
          options={TYPES.map((s) => [s, t(`type_${s}` as QKey)])} />
        <Filter value={employee} onChange={(v) => { setEmployee(v); setPage(1); }} label={t("fltEmployee")}
          options={(employees.data ?? []).map((e) => [String(e.id), e.full_name])} />
        <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-40" aria-label={t("dateFrom")} />
        <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-40" aria-label={t("dateTo")} />
        {!trash && (
          <Button variant="outline" size="sm" onClick={() => download("files/export.csv", "qrdrive-files.csv", filters)}>
            <Download className="size-4" />{t("export")}
          </Button>
        )}
      </div>
      {trash && <p className="mb-3 text-sm text-muted-foreground">{t("trashHint", { days: settings.data?.trash_days ?? 30 })}</p>}
      {selected.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-sm">
          <span className="font-medium">{t("selected", { n: selected.length })}</span>
          {trash ? (
            <>
              <Button size="sm" variant="outline" onClick={() => doBulk("restore")}><RotateCcw className="size-4" />{t("bulkRestore")}</Button>
              <Button size="sm" variant="destructive" onClick={() => setConfirmPurge(true)}><Trash2 className="size-4" />{t("bulkPurge")}</Button>
            </>
          ) : (
            <>
              <Button size="sm" variant="outline" onClick={() => doBulk("retry")}><RefreshCw className="size-4" />{t("bulkRetry")}</Button>
              <Button size="sm" variant="outline" onClick={() => doBulk("delete")}><Trash2 className="size-4" />{t("bulkDelete")}</Button>
            </>
          )}
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>{t("cancel")}</Button>
        </div>
      )}
      <QrGuard query={query}>
        {!items.length ? (
          <EmptyState icon={FileIcon} title={t("noFiles")} hint={t("noFilesHint")} />
        ) : (
          <Card className="gap-0 overflow-hidden p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox checked={allChecked} onCheckedChange={(v) => setSelected(v ? items.map((f) => f.id) : [])} aria-label={t("all")} />
                  </TableHead>
                  <TableHead className="w-36">{t("colDate")}</TableHead>
                  <TableHead>{t("colFile")}</TableHead>
                  <TableHead>{t("colEmployee")}</TableHead>
                  <TableHead className="w-24 text-right">{t("colSize")}</TableHead>
                  <TableHead className="w-24">{t("colSource")}</TableHead>
                  <TableHead className="w-32">{t("colStatus")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((f) => (
                  <TableRow key={f.id} className="cursor-pointer" onClick={() => onOpen(f.id)}>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Checkbox checked={selected.includes(f.id)}
                        onCheckedChange={(v) => setSelected((s) => (v ? [...s, f.id] : s.filter((x) => x !== f.id)))} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{fmtDate(f.created_at)}</TableCell>
                    <TableCell className="max-w-72"><div className="truncate font-medium">{f.original_name}</div>
                      {f.remote_path && <div className="truncate text-xs text-muted-foreground">{f.remote_path}</div>}</TableCell>
                    <TableCell><div className="truncate">{f.employee_name || "—"}</div><div className="text-xs text-muted-foreground">{f.department}</div></TableCell>
                    <TableCell className="text-right font-mono text-xs">{formatBytes(f.size)}</TableCell>
                    <TableCell className="text-xs">{t(`src_${f.source}` as QKey)}</TableCell>
                    <TableCell><StatusBadge status={f.status} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
        {pages > 1 && (
          <div className="mt-3 flex items-center justify-end gap-2 text-sm">
            <span className="text-muted-foreground">{t("total", { n: query.data?.total ?? 0 })}</span>
            <Button size="icon" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft className="size-4" /></Button>
            <span>{page} / {pages}</span>
            <Button size="icon" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}><ChevronRight className="size-4" /></Button>
          </div>
        )}
      </QrGuard>
      <ConfirmDialog open={confirmPurge} onOpenChange={setConfirmPurge} title={t("bulkPurge")} description={t("purgeHint")} destructive
        pending={bulk.isPending} onConfirm={() => { doBulk("purge"); setConfirmPurge(false); }} />
    </>
  );
}

function Filter({ value, onChange, label, options }: { value: string; onChange: (v: string) => void; label: string; options: [string, string][] }) {
  const t = useQt();
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-40" aria-label={label}><SelectValue placeholder={label} /></SelectTrigger>
      <SelectContent>
        <SelectItem value="all">{label}: {t("all")}</SelectItem>
        {options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

interface Folder { employee_id: number | null; name: string; folder: string; department: string; storage_id: number | null; count: number; size: number }
interface Entry { name: string; path: string; is_dir: boolean; size: number | null; modified: string | null; registered: boolean; file: QrFile | null }

/** Papka brauzeri: chapda xodim papkalari, o'ngda saqlash joyidagi haqiqiy tarkib (Explorer kabi). */
function FolderBrowser({ onOpen }: { onOpen: (id: number) => void }) {
  const t = useQt();
  const storages = useQr<QrStorage[]>(["storages"], "storages");
  const folders = useQr<Folder[]>(["folders"], "files/folders");
  const primary = storages.data?.find((s) => s.is_primary) ?? storages.data?.[0];
  const [storageId, setStorageId] = useState<number | null>(null);
  const storage = storages.data?.find((s) => s.id === storageId) ?? primary;
  const [path, setPath] = useState<string | null>(null);
  const current = path ?? storage?.base_folder ?? "/";
  const listing = useQr<{ entries: Entry[] }>(["browse", storage?.id, current], "files/browse",
    { storage_id: storage?.id, path: current }, { enabled: !!storage });
  const crumbs = current.split("/").filter(Boolean);

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
      <Card className="max-h-[70vh] gap-0 overflow-y-auto p-2">
        <QrGuard query={folders}>
          {(folders.data ?? []).map((f) => (
            <button key={`${f.employee_id}`} disabled={!f.folder}
              onClick={() => { setStorageId(f.storage_id); setPath(`${(storages.data?.find((s) => s.id === f.storage_id) ?? primary)?.base_folder ?? ""}/${f.folder}`.replace(/\/+/g, "/")); }}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm hover:bg-muted disabled:opacity-50">
              <Folder className="size-4 shrink-0 text-primary" />
              <span className="min-w-0 flex-1"><span className="block truncate">{f.name}</span>
                <span className="block text-xs text-muted-foreground">{t("folderFiles", { n: f.count })} · {formatBytes(f.size)}</span></span>
            </button>
          ))}
        </QrGuard>
      </Card>
      <Card className="gap-0 p-0">
        <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2 text-sm">
          {(storages.data?.length ?? 0) > 1 && (
            <Select value={String(storage?.id ?? "")} onValueChange={(v) => { setStorageId(Number(v)); setPath(null); }}>
              <SelectTrigger className="h-8 w-44"><SelectValue placeholder={t("pickStorage")} /></SelectTrigger>
              <SelectContent>{storages.data?.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}</SelectContent>
            </Select>
          )}
          <button className="text-muted-foreground hover:text-foreground" onClick={() => setPath("/")}>/</button>
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-2">
              <button className="hover:text-primary" onClick={() => setPath("/" + crumbs.slice(0, i + 1).join("/"))}>{c}</button>
              {i < crumbs.length - 1 && <span className="text-muted-foreground">/</span>}
            </span>
          ))}
        </div>
        <div className="max-h-[65vh] overflow-y-auto p-2">
          {!storage ? <p className="p-4 text-sm text-muted-foreground">{t("stoEmpty")}</p> : (
            <QrGuard query={listing}>
              {crumbs.length > 0 && (
                <button className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm hover:bg-muted"
                  onClick={() => setPath("/" + crumbs.slice(0, -1).join("/"))}>
                  <Folder className="size-4 text-muted-foreground" />..
                </button>
              )}
              {!listing.data?.entries.length && <p className="p-4 text-sm text-muted-foreground">{t("folderEmpty")}</p>}
              {listing.data?.entries.map((e) => (
                <button key={e.path}
                  onClick={() => (e.is_dir ? setPath(e.path) : e.file ? onOpen(e.file.id)
                    : download(`files/raw/${storage.id}`, e.name, { path: e.path, download: true }))}
                  className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm hover:bg-muted">
                  {e.is_dir ? <Folder className="size-4 shrink-0 text-primary" /> : <FileIcon className="size-4 shrink-0 text-muted-foreground" />}
                  <span className="min-w-0 flex-1 truncate">{e.name}</span>
                  {!e.registered && <Badge variant="outline" className="text-[10px] text-warning">{t("unregistered")}</Badge>}
                  {e.file && <StatusBadge status={e.file.status} />}
                  {!e.is_dir && <span className="w-20 text-right font-mono text-xs text-muted-foreground">{formatBytes(e.size)}</span>}
                  <span className="hidden w-32 text-right text-xs text-muted-foreground md:block">{fmtDate(e.modified)}</span>
                </button>
              ))}
            </QrGuard>
          )}
        </div>
      </Card>
    </div>
  );
}

export function UploadDialog({ open, onOpenChange, employeeId }: { open: boolean; onOpenChange: (v: boolean) => void; employeeId?: number }) {
  const t = useQt();
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [emp, setEmp] = useState(employeeId ? String(employeeId) : "none");
  const [folder, setFolder] = useState("");
  const [vis, setVis] = useState("default");
  const [drag, setDrag] = useState(false);
  const employees = useQr<QrEmployee[]>(["employees"], "employees", undefined, { enabled: open });
  const send = useQrAction(async () => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    if (emp !== "none") fd.append("employee_id", emp);
    if (folder) fd.append("folder", folder);
    if (vis !== "default") fd.append("visibility", vis);
    return (await qrApi.post<QrFile[]>("files/upload", fd)).data;
  }, (r) => t("uploaded", { n: r.length }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("uploadTitle")}</DialogTitle>
          <DialogDescription>{t("uploadDesc")}</DialogDescription>
        </DialogHeader>
        <div
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); setFiles([...files, ...Array.from(e.dataTransfer.files)]); }}
          onClick={() => input.current?.click()}
          className={cn("grid cursor-pointer place-items-center rounded-xl border-2 border-dashed px-4 py-8 text-center text-sm text-muted-foreground transition-colors",
            drag && "border-primary bg-primary/5")}>
          <Upload className="mb-2 size-6" />{t("dropHere")}
          <input ref={input} type="file" multiple hidden onChange={(e) => setFiles([...files, ...Array.from(e.target.files ?? [])])} />
        </div>
        {files.length > 0 && (
          <ul className="max-h-32 overflow-y-auto text-sm">
            {files.map((f, i) => (
              <li key={i} className="flex items-center gap-2 py-0.5"><FileIcon className="size-3.5" /><span className="flex-1 truncate">{f.name}</span>
                <span className="font-mono text-xs text-muted-foreground">{formatBytes(f.size)}</span></li>
            ))}
          </ul>
        )}
        <FormRow label={t("forEmployee")}>
          <Select value={emp} onValueChange={setEmp}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">{t("noEmployee")}</SelectItem>
              {employees.data?.filter((e) => e.status === "active").map((e) => <SelectItem key={e.id} value={String(e.id)}>{e.full_name}</SelectItem>)}
            </SelectContent>
          </Select>
        </FormRow>
        <FormRow label={t("visibility")}>
          <Select value={vis} onValueChange={setVis}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="default">{t("visDefault")}</SelectItem>
              <SelectItem value="public">{t("visPublic")}</SelectItem>
              <SelectItem value="private">{t("visPrivate")}</SelectItem>
            </SelectContent>
          </Select>
        </FormRow>
        <FormRow label={t("folderOptional")}><Input value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="Buyruqlar/2026" /></FormRow>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t("cancel")}</Button>
          <Button disabled={!files.length || send.isPending}
            onClick={() => send.mutate(undefined, { onSuccess: () => { setFiles([]); onOpenChange(false); } })}>
            <Upload className="size-4" />{send.isPending ? t("uploading") : t("uploadBtn")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
