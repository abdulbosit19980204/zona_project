"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AtSign, Download, FileDown, FileSignature, Laptop, Phone, Plus, Send, Upload, Users, Workflow } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { AckBadge, AckDetail, useCreateAck } from "./acks";
import { download, inv, type Employee } from "./api";
import { useT } from "./i18n";
import { ImportDialog } from "./import-dialog";
import { Btn, Empty, Field, FilterBar, MoreActions, Overlay, Picker, Spinner, inputCls, useBoot, type FilterChip } from "./ui";

function EmployeeForm(props: { open: boolean; onClose: () => void; emp: Employee | null; onShowItems: (id: number) => void }) {
  return props.open ? <EmployeeFormBody key={props.emp?.id ?? "new"} {...props} /> : null;
}

function EmployeeFormBody({ onClose, emp, onShowItems }: {
  open: boolean; onClose: () => void; emp: Employee | null; onShowItems: (id: number) => void;
}) {
  const boot = useBoot().data!;
  const t = useT();
  const qc = useQueryClient();
  const [f, setF] = useState<Partial<Employee>>(() => emp ?? { branch: boot.me.branches?.length === 1 ? boot.me.branches[0] : null, is_active: true });
  const [busy, setBusy] = useState(false);
  const [ackOpen, setAckOpen] = useState<number | null>(null);
  const { create, dialog } = useCreateAck();
  const set = <K extends keyof Employee>(k: K, v: Employee[K]) => setF((x) => ({ ...x, [k]: v }));
  const save = async () => {
    if ((f.full_name ?? "").trim().length < 3) return toast.error(t("F.I.Sh. ni yozing"));
    setBusy(true);
    try {
      const body = { full_name: f.full_name, position: f.position ?? "", phone: f.phone ?? "", telegram: f.telegram ?? "",
        branch: f.branch ?? null, org: f.org ?? null, project: f.project ?? "", department: f.department ?? "", note: f.note ?? "" };
      if (emp) await inv.updateEmployee(emp.id, body);
      else await inv.createEmployee(body);
      qc.invalidateQueries({ queryKey: ["inv", "employees"] });
      toast.success(t("Saqlandi"));
      onClose();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!emp || !confirm(t("{n} o'chirilsinmi?", { n: emp.full_name }))) return;
    try {
      const r = await inv.deleteEmployee(emp.id);
      toast.success(r?.deactivated ? t("Nofaol qilindi ({n} ta qurilma biriktirilgan)", { n: r.devices ?? 0 }) : t("O'chirildi"));
      qc.invalidateQueries({ queryKey: ["inv", "employees"] });
      onClose();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };
  const canWrite = boot.me.can.write;
  return (
    <Overlay open onClose={onClose} title={emp ? emp.full_name : t("Yangi xodim")}
      footer={canWrite ? <Btn size="lg" className="w-full" loading={busy} onClick={save}>{t("Saqlash")}</Btn> : undefined}>
      <div className="space-y-4 p-4">
        <Field label={t("F.I.Sh.")} required>
          <input className={inputCls} value={f.full_name ?? ""} onChange={(e) => set("full_name", e.target.value)} disabled={!canWrite}
            placeholder={t("Familiya Ism Sharif")} autoFocus={!emp} />
        </Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("Telefon")}>
            <input className={inputCls} inputMode="tel" value={f.phone ?? ""} onChange={(e) => set("phone", e.target.value)} disabled={!canWrite}
              placeholder="+998 90 123 45 67" />
          </Field>
          <Field label="Telegram">
            <input className={inputCls} value={f.telegram ?? ""} onChange={(e) => set("telegram", e.target.value.replace(/^@/, ""))} disabled={!canWrite}
              autoCapitalize="none" autoCorrect="off" spellCheck={false} placeholder="username" />
          </Field>
          <Field label={t("Lavozimi")}>
            <input className={inputCls} value={f.position ?? ""} onChange={(e) => set("position", e.target.value)} disabled={!canWrite} />
          </Field>
          <Field label={t("Filial")}>
            <Picker title={t("Filial")} value={f.branch ? String(f.branch) : ""} disabled={!canWrite || boot.me.branches?.length === 1}
              options={boot.branches.map((b) => ({ value: String(b.id), label: b.name }))}
              onChange={(v) => set("branch", v ? Number(v) : null)} />
          </Field>
          <Field label={t("Tashkilot")}>
            <Picker title={t("Tashkilot")} value={f.org ? String(f.org) : ""} disabled={!canWrite}
              options={boot.orgs.map((o) => ({ value: String(o.id), label: o.name }))} onChange={(v) => set("org", v ? Number(v) : null)} />
          </Field>
          <Field label={t("Loyiha / brend")} hint="Heinz, BIC, L'Oréal…">
            <input className={inputCls} value={f.project ?? ""} onChange={(e) => set("project", e.target.value)} disabled={!canWrite} />
          </Field>
          <Field label={t("Bo'lim")}>
            <input className={inputCls} value={f.department ?? ""} onChange={(e) => set("department", e.target.value)} disabled={!canWrite} />
          </Field>
          <Field label={t("Izoh")}>
            <input className={inputCls} value={f.note ?? ""} onChange={(e) => set("note", e.target.value)} disabled={!canWrite} />
          </Field>
        </div>
        {emp && (
          <div className="space-y-3 border-t pt-4">
            {emp.devices > 0 && (
              <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-muted/30 p-3">
                <FileSignature className="size-4 text-muted-foreground" />
                <span className="text-sm font-medium">{t("Tasdiqnoma")}:</span>
                <AckBadge status={emp.ack?.status ?? "none"} opened={!!emp.ack?.opened_at} />
                <div className="ml-auto flex gap-1.5">
                  {emp.ack && <Btn variant="ghost" size="sm" onClick={() => setAckOpen(emp.ack!.id)}>{t("Ko'rish")}</Btn>}
                  {canWrite && <Btn variant="soft" size="sm" onClick={() => create(emp)}><Send className="size-4" />{t("Tasdiqlash havolasi")}</Btn>}
                </div>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Btn variant="soft" onClick={() => { onClose(); onShowItems(emp.id); }}><Laptop className="size-4" />{t("Qurilmalari ({n})", { n: emp.devices })}</Btn>
              {canWrite && <Btn variant="danger" onClick={remove}>{t("O'chirish")}</Btn>}
            </div>
          </div>
        )}
      </div>
      <AckDetail id={ackOpen} onClose={() => setAckOpen(null)} />
      {dialog}
    </Overlay>
  );
}

export function EmployeesView({ onShowItems, table }: { onShowItems: (employeeId: number) => void; table?: boolean }) {
  const boot = useBoot().data!;
  const t = useT();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [branch, setBranch] = useState("");
  const [org, setOrg] = useState("");
  const [project, setProject] = useState("");
  const [department, setDepartment] = useState("");
  const [devices, setDevices] = useState("");
  const [ack, setAck] = useState("");
  const [edit, setEdit] = useState<Employee | null>(null);
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [limit, setLimit] = useState(100);
  const { create, dialog } = useCreateAck();
  useEffect(() => {
    const tm = setTimeout(() => setQuery(q), 250);
    return () => clearTimeout(tm);
  }, [q]);
  const params = { q: query, branch: branch === "none" ? undefined : branch, no_branch: branch === "none" ? 1 : undefined,
    org, project, department, devices: ack === "contact" ? undefined : devices,
    ack: ack && ack !== "contact" ? ack : undefined, contact: ack === "contact" ? 0 : undefined };
  const list = useQuery({ queryKey: ["inv", "employees", "list", params], queryFn: () => inv.employees({ ...params, limit: 5000 }) });
  const rows = useMemo(() => list.data?.results ?? [], [list.data]);
  const noBranch = t("Filialsiz");
  const byBranch = useMemo(() => {
    const m = new Map<string, number>();
    rows.forEach((e) => m.set(e.branch_name || noBranch, (m.get(e.branch_name || noBranch) ?? 0) + 1));
    return m;
  }, [rows, noBranch]);
  const manage = boot.me.can.manage;
  const orgOpts = boot.orgs.map((o) => ({ value: String(o.id), label: o.name }));
  const deviceOpts = [{ value: "1", label: t("Qurilmasi bor") }, { value: "0", label: t("Qurilmasi yo'q") }];
  const ackOpts = [{ value: "signed", label: t("Imzolangan") }, { value: "pending", label: t("Imzo kutilmoqda") },
    { value: "none", label: t("Havola yuborilmagan") }, { value: "contact", label: t("Telefon yoki Telegram yo'q") }];
  const chips: FilterChip[] = [];
  const label = (opts: { value: string; label: string }[], v: string) => opts.find((o) => o.value === v)?.label ?? v;
  if (branch) chips.push({ label: branch === "none" ? noBranch : label(boot.branches.map((b) => ({ value: String(b.id), label: b.name })), branch), onRemove: () => setBranch("") });
  if (org) chips.push({ label: label(orgOpts, org), onRemove: () => setOrg("") });
  if (project) chips.push({ label: project, onRemove: () => setProject("") });
  if (department) chips.push({ label: department, onRemove: () => setDepartment("") });
  if (devices) chips.push({ label: label(deviceOpts, devices), onRemove: () => setDevices("") });
  if (ack) chips.push({ label: label(ackOpts, ack), onRemove: () => setAck("") });
  const clearFilters = () => { setBranch(""); setOrg(""); setProject(""); setDepartment(""); setDevices(""); setAck(""); };

  const fromStaff = async () => {
    try {
      const dry = await inv.employeesFromStaff(true);
      if (!confirm(t("Xodimlar tuzilmasidan: {c} ta yangi, {u} ta yangilanadi, {m} ta filiali aniqlanmadi. Davom etilsinmi?", { c: dry.created, u: dry.updated, m: dry.unmapped }))) return;
      const r = await inv.employeesFromStaff(false);
      toast.success(t("{c} ta yangi, {u} ta yangilandi", { c: r.created, u: r.updated }));
      qc.invalidateQueries({ queryKey: ["inv", "employees"] });
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  const ackCell = (e: Employee) => e.devices > 0 ? (
    <div className="flex items-center justify-end gap-1.5">
      <AckBadge status={e.ack?.status ?? "none"} opened={!!e.ack?.opened_at} />
      {boot.me.can.write && e.ack?.status !== "signed" && (
        <button onClick={(ev) => { ev.stopPropagation(); create(e); }} title={t("Tasdiqlash havolasi")}
          className="grid size-7 place-items-center rounded-lg text-indigo-600 hover:bg-indigo-500/10"><Send className="size-3.5" /></button>
      )}
    </div>
  ) : null;

  return (
    <div className={cn("mx-auto w-full", table ? "max-w-[1800px]" : "max-w-5xl")}>
      <FilterBar inline={table} search={q} onSearch={setQ} placeholder={t("Ism, telefon, Telegram, lavozim…")} chips={chips}
        onClear={clearFilters} total={list.data?.count}
        right={boot.me.can.write ? <Btn onClick={() => setCreating(true)} className="w-11 px-0 sm:w-auto sm:px-4"><Plus className="size-4" /><span className="hidden sm:inline">{t("Xodim")}</span></Btn> : undefined}>
        {boot.branches.length > 1 && (
          <Field label={table ? "" : t("Filial")}>
            <Picker title={t("Filial")} placeholder={t("Barcha filiallar")} value={branch}
              options={[{ value: "none", label: noBranch }, ...boot.branches.map((b) => ({ value: String(b.id), label: b.name }))]} onChange={setBranch} />
          </Field>
        )}
        <Field label={table ? "" : t("Tashkilot")}>
          <Picker title={t("Tashkilot")} placeholder={t("Barcha tashkilotlar")} value={org} options={orgOpts} onChange={setOrg} />
        </Field>
        <Field label={table ? "" : t("Loyiha")}>
          <Picker title={t("Loyiha")} placeholder={t("Barcha loyihalar")} value={project} options={(list.data?.projects ?? []).map((p) => ({ value: p, label: p }))} onChange={setProject} />
        </Field>
        <Field label={table ? "" : t("Bo'lim")}>
          <Picker title={t("Bo'lim")} placeholder={t("Barcha bo'limlar")} value={department} options={(list.data?.departments ?? []).map((p) => ({ value: p, label: p }))} onChange={setDepartment} />
        </Field>
        <Field label={table ? "" : t("Qurilmasi")}>
          <Picker title={t("Qurilmasi")} placeholder={t("Qurilmasi: hammasi")} value={devices} options={deviceOpts} onChange={setDevices} />
        </Field>
        <Field label={table ? "" : t("Tasdiqnoma")}>
          <Picker title={t("Tasdiqnoma")} placeholder={t("Tasdiqnoma: hammasi")} value={ack} options={ackOpts} onChange={setAck} />
        </Field>
      </FilterBar>

      <div className="flex items-center gap-2 px-4 pt-3">
        <span className="mr-auto text-sm text-muted-foreground">{t("{n} xodim", { n: list.data?.count ?? "…" })}</span>
        <MoreActions inline={table} actions={[
          { label: "Excel", icon: <Download className="size-4" />, onClick: () => download("employees/export/", { fmt: "xlsx", branch: branch && branch !== "none" ? branch : undefined }).catch((e) => toast.error(errorMessage(e))) },
          { label: "CSV", icon: <Download className="size-4" />, onClick: () => download("employees/export/", { fmt: "csv" }).catch((e) => toast.error(errorMessage(e))) },
          { label: t("Shablon"), icon: <FileDown className="size-4" />, onClick: () => download("employees/template/").catch((e) => toast.error(errorMessage(e))) },
          { label: t("Import"), icon: <Upload className="size-4" />, onClick: () => setImporting(true), hidden: !boot.me.can.write },
          { label: t("Tuzilmadan olish"), icon: <Workflow className="size-4" />, onClick: fromStaff, hidden: !manage },
        ]} />
      </div>
      {table && byBranch.size > 1 && !branch && (
        <div className="flex flex-wrap gap-1.5 px-4 pt-2">
          {[...byBranch.entries()].sort((a, b) => b[1] - a[1]).map(([name, n]) => (
            <span key={name} className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">{name}: <b>{n}</b></span>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-2 px-3 pb-28 pt-3 sm:grid-cols-2 sm:px-4">
        {list.isLoading && <Spinner className="sm:col-span-2" />}
        {!list.isLoading && !rows.length && (
          <div className="sm:col-span-2">
            <Empty icon={<Users className="size-6" />} title={t("Xodim topilmadi")}
              hint={t("Shablonni yuklab olib to'ldiring va Import qiling yoki «Xodim» tugmasi bilan qo'shing.")} />
          </div>
        )}
        {table && !!rows.length && (
          <div className="hidden overflow-x-auto rounded-xl border bg-card sm:col-span-2 md:block">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2.5 font-semibold">{t("F.I.Sh.")}</th><th className="px-2 font-semibold">{t("Lavozimi")}</th>
                  <th className="px-2 font-semibold">{t("Telefon")}</th><th className="px-2 font-semibold">Telegram</th>
                  <th className="px-2 font-semibold">{t("Filial")}</th><th className="px-2 font-semibold">{t("Tashkilot")}</th>
                  <th className="px-2 font-semibold">{t("Loyiha")}</th><th className="px-2 text-right font-semibold">{t("Qurilmalar")}</th>
                  <th className="px-3 text-right font-semibold">{t("Tasdiqnoma")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, limit).map((e) => (
                  <tr key={e.id} onClick={() => setEdit(e)} className="cursor-pointer border-b last:border-0 hover:bg-muted/40">
                    <td className="px-3 py-2.5 font-medium">{e.full_name}</td>
                    <td className="px-2 text-muted-foreground">{e.position || "—"}</td>
                    <td className="whitespace-nowrap px-2 text-muted-foreground">{e.phone || <span className="text-amber-600">—</span>}</td>
                    <td className="px-2 text-muted-foreground">{e.telegram ? `@${e.telegram}` : <span className="text-amber-600">—</span>}</td>
                    <td className="px-2">{e.branch_name || <span className="text-amber-600">{t("filialsiz")}</span>}</td>
                    <td className="px-2 text-muted-foreground">{e.org_name || "—"}</td>
                    <td className="px-2 text-muted-foreground">{e.project || "—"}</td>
                    <td className="px-2 text-right">
                      <button onClick={(ev) => { ev.stopPropagation(); onShowItems(e.id); }} disabled={!e.devices}
                        className={cn("rounded-lg px-2 py-1 text-xs font-bold tabular-nums", e.devices ? "bg-emerald-500/12 text-emerald-700 hover:bg-emerald-500/20 dark:text-emerald-400" : "bg-muted text-muted-foreground")}>
                        <Laptop className="mr-1 inline size-3" />{e.devices}
                      </button>
                    </td>
                    <td className="px-3">{ackCell(e)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {rows.slice(0, limit).map((e) => (
          <button key={e.id} onClick={() => setEdit(e)}
            className={cn("flex items-center gap-3 rounded-2xl border bg-card p-3 text-left shadow-xs hover:border-primary/40", table && "md:hidden")}>
            <span className="grid size-11 shrink-0 place-items-center rounded-full bg-indigo-500/10 text-sm font-bold text-indigo-600 dark:text-indigo-400">
              {e.full_name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase()}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate font-semibold">{e.full_name}</div>
              <div className="truncate text-xs text-muted-foreground">{[e.position, e.project, e.department].filter(Boolean).join(" · ") || "—"}</div>
              <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                <span>{e.branch_name || <span className="text-amber-600">{t("filialsiz")}</span>}</span>
                {e.phone && <span className="inline-flex items-center gap-1"><Phone className="size-3" />{e.phone}</span>}
                {e.telegram && <span className="inline-flex items-center gap-1"><AtSign className="size-3" />{e.telegram}</span>}
              </div>
              {e.devices > 0 && <div className="mt-1"><AckBadge status={e.ack?.status ?? "none"} opened={!!e.ack?.opened_at} /></div>}
            </div>
            <span className={cn("shrink-0 rounded-lg px-2 py-1 text-xs font-bold tabular-nums", e.devices ? "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400" : "bg-muted text-muted-foreground")}>
              <Laptop className="mr-1 inline size-3" />{e.devices}
            </span>
          </button>
        ))}
        {rows.length > limit && (
          <Btn variant="outline" className="sm:col-span-2" onClick={() => setLimit((l) => l + 200)}>{t("Yana ko'rsatish")} ({rows.length - limit})</Btn>
        )}
      </div>
      <EmployeeForm open={!!edit || creating} emp={edit} onClose={() => { setEdit(null); setCreating(false); }} onShowItems={onShowItems} />
      <ImportDialog open={importing} onClose={() => setImporting(false)} title={t("Xodimlarni import qilish")}
        hint={t("«Shablon» tugmasi bilan faylni yuklab oling, to'ldiring va shu yerga yuklang. Bir xil ismli xodim (shu filialda) qayta yaratilmaydi — yangilanadi. Inventarizatsiya shablonining «Xodimlar» varag'i ham qabul qilinadi.")}
        run={(file, dry) => inv.importEmployees(file, dry)} />
      {dialog}
    </div>
  );
}
