"use client";
/* eslint-disable react/no-unescaped-entities -- o'zbekcha matnlardagi apostrof (o'z, ma'lumot) */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileDown, Laptop, Phone, Plus, Search, Upload, Users, Workflow, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { download, inv, type Employee } from "./api";
import { ImportDialog } from "./import-dialog";
import { Btn, Empty, Field, Overlay, Picker, Spinner, inputCls, useBoot } from "./ui";

function EmployeeForm(props: { open: boolean; onClose: () => void; emp: Employee | null; onShowItems: (id: number) => void }) {
  return props.open ? <EmployeeFormBody key={props.emp?.id ?? "new"} {...props} /> : null;
}

function EmployeeFormBody({ open, onClose, emp, onShowItems }: {
  open: boolean; onClose: () => void; emp: Employee | null; onShowItems: (id: number) => void;
}) {
  const boot = useBoot().data!;
  const qc = useQueryClient();
  const [f, setF] = useState<Partial<Employee>>(() => emp ?? { branch: boot.me.branches?.length === 1 ? boot.me.branches[0] : null, is_active: true });
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof Employee>(k: K, v: Employee[K]) => setF((x) => ({ ...x, [k]: v }));
  const save = async () => {
    if ((f.full_name ?? "").trim().length < 3) return toast.error("F.I.Sh. ni yozing");
    setBusy(true);
    try {
      const body = { full_name: f.full_name, position: f.position ?? "", phone: f.phone ?? "", branch: f.branch ?? null,
        org: f.org ?? null, project: f.project ?? "", department: f.department ?? "", note: f.note ?? "" };
      if (emp) await inv.updateEmployee(emp.id, body);
      else await inv.createEmployee(body);
      qc.invalidateQueries({ queryKey: ["inv", "employees"] });
      toast.success("Saqlandi");
      onClose();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!emp || !confirm(`${emp.full_name} o'chirilsinmi?`)) return;
    try {
      const r = await inv.deleteEmployee(emp.id);
      toast.success(r?.deactivated ? `Nofaol qilindi (${r.devices} ta qurilma biriktirilgan)` : "O'chirildi");
      qc.invalidateQueries({ queryKey: ["inv", "employees"] });
      onClose();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };
  const canWrite = boot.me.can.write;
  return (
    <Overlay open={open} onClose={onClose} title={emp ? emp.full_name : "Yangi xodim"}
      footer={canWrite ? <Btn size="lg" className="w-full" loading={busy} onClick={save}>Saqlash</Btn> : undefined}>
      <div className="space-y-4 p-4">
        <Field label="F.I.Sh." required>
          <input className={inputCls} value={f.full_name ?? ""} onChange={(e) => set("full_name", e.target.value)} disabled={!canWrite}
            placeholder="Familiya Ism Sharif" autoFocus={!emp} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Lavozimi">
            <input className={inputCls} value={f.position ?? ""} onChange={(e) => set("position", e.target.value)} disabled={!canWrite} />
          </Field>
          <Field label="Telefon">
            <input className={inputCls} inputMode="tel" value={f.phone ?? ""} onChange={(e) => set("phone", e.target.value)} disabled={!canWrite}
              placeholder="+998 90 123 45 67" />
          </Field>
          <Field label="Filial">
            <Picker title="Filial" value={f.branch ? String(f.branch) : ""} disabled={!canWrite || boot.me.branches?.length === 1}
              options={boot.branches.map((b) => ({ value: String(b.id), label: b.name }))}
              onChange={(v) => set("branch", v ? Number(v) : null)} />
          </Field>
          <Field label="Tashkilot">
            <Picker title="Tashkilot" value={f.org ? String(f.org) : ""} disabled={!canWrite}
              options={boot.orgs.map((o) => ({ value: String(o.id), label: o.name }))} onChange={(v) => set("org", v ? Number(v) : null)} />
          </Field>
          <Field label="Loyiha / brend" hint="Heinz, BIC, L'Oréal…">
            <input className={inputCls} value={f.project ?? ""} onChange={(e) => set("project", e.target.value)} disabled={!canWrite} />
          </Field>
          <Field label="Bo'lim">
            <input className={inputCls} value={f.department ?? ""} onChange={(e) => set("department", e.target.value)} disabled={!canWrite} />
          </Field>
        </div>
        <Field label="Izoh">
          <input className={inputCls} value={f.note ?? ""} onChange={(e) => set("note", e.target.value)} disabled={!canWrite} />
        </Field>
        {emp && (
          <div className="flex flex-wrap gap-2 border-t pt-4">
            <Btn variant="soft" onClick={() => { onClose(); onShowItems(emp.id); }}><Laptop className="size-4" />Qurilmalari ({emp.devices})</Btn>
            {canWrite && <Btn variant="danger" onClick={remove}>O'chirish</Btn>}
          </div>
        )}
      </div>
    </Overlay>
  );
}

export function EmployeesView({ onShowItems, table }: { onShowItems: (employeeId: number) => void; table?: boolean }) {
  const boot = useBoot().data!;
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [branch, setBranch] = useState("");
  const [org, setOrg] = useState("");
  const [project, setProject] = useState("");
  const [department, setDepartment] = useState("");
  const [devices, setDevices] = useState("");
  const [edit, setEdit] = useState<Employee | null>(null);
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [limit, setLimit] = useState(100);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 250);
    return () => clearTimeout(t);
  }, [q]);
  const params = { q: query, branch: branch === "none" ? undefined : branch, no_branch: branch === "none" ? 1 : undefined,
    org, project, department, devices };
  const list = useQuery({ queryKey: ["inv", "employees", "list", params], queryFn: () => inv.employees({ ...params, limit: 5000 }) });
  const rows = useMemo(() => list.data?.results ?? [], [list.data]);
  const byBranch = useMemo(() => {
    const m = new Map<string, number>();
    rows.forEach((e) => m.set(e.branch_name || "Filialsiz", (m.get(e.branch_name || "Filialsiz") ?? 0) + 1));
    return m;
  }, [rows]);
  const manage = boot.me.can.manage;

  const fromStaff = async () => {
    try {
      const dry = await inv.employeesFromStaff(true);
      if (!confirm(`Xodimlar tuzilmasidan: ${dry.created} ta yangi, ${dry.updated} ta yangilanadi, ${dry.unmapped} ta filiali aniqlanmadi. Davom etilsinmi?`)) return;
      const r = await inv.employeesFromStaff(false);
      toast.success(`${r.created} ta yangi, ${r.updated} ta yangilandi`);
      qc.invalidateQueries({ queryKey: ["inv", "employees"] });
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  return (
    <div className={cn("mx-auto w-full", table ? "max-w-[1800px]" : "max-w-5xl")}>
      <div className="sticky top-[var(--inv-top,0px)] z-20 space-y-2 border-b bg-background/95 px-3 py-3 backdrop-blur sm:px-4">
        <div className="flex gap-2">
          <div className="flex h-11 min-w-0 flex-1 items-center gap-2 rounded-xl border bg-card px-3 focus-within:border-primary md:h-10 md:rounded-lg">
            <Search className="size-4 shrink-0 text-muted-foreground" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ism, telefon, lavozim…" className="h-full min-w-0 flex-1 bg-transparent text-[15px] outline-none" />
            {q && <button onClick={() => setQ("")}><X className="size-4 text-muted-foreground" /></button>}
          </div>
          {boot.me.can.write && <Btn onClick={() => setCreating(true)}><Plus className="size-4" /><span className="hidden sm:inline">Xodim</span></Btn>}
        </div>
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
          {boot.branches.length > 1 && (
            <Picker title="Filial" placeholder="Barcha filiallar" value={branch}
              options={[{ value: "none", label: "Filialsiz" }, ...boot.branches.map((b) => ({ value: String(b.id), label: b.name }))]} onChange={setBranch} />
          )}
          <Picker title="Tashkilot" placeholder="Barcha tashkilotlar" value={org} options={boot.orgs.map((o) => ({ value: String(o.id), label: o.name }))} onChange={setOrg} />
          <Picker title="Loyiha" placeholder="Barcha loyihalar" value={project} options={(list.data?.projects ?? []).map((p) => ({ value: p, label: p }))} onChange={setProject} />
          <Picker title="Bo'lim" placeholder="Barcha bo'limlar" value={department} options={(list.data?.departments ?? []).map((p) => ({ value: p, label: p }))} onChange={setDepartment} />
          <Picker title="Qurilmasi" placeholder="Qurilmasi: hammasi" value={devices}
            options={[{ value: "1", label: "Qurilmasi bor" }, { value: "0", label: "Qurilmasi yo'q" }]} onChange={setDevices} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
        <span className="mr-auto text-sm text-muted-foreground"><b className="text-foreground">{list.data?.count ?? "…"}</b> xodim</span>
        <Btn variant="ghost" size="sm" onClick={() => download("employees/export/", { fmt: "xlsx", branch: branch && branch !== "none" ? branch : undefined }).catch((e) => toast.error(errorMessage(e)))}><Download className="size-4" />Excel</Btn>
        <Btn variant="ghost" size="sm" onClick={() => download("employees/export/", { fmt: "csv" }).catch((e) => toast.error(errorMessage(e)))}><Download className="size-4" />CSV</Btn>
        <Btn variant="ghost" size="sm" onClick={() => download("employees/template/").catch((e) => toast.error(errorMessage(e)))}><FileDown className="size-4" />Shablon</Btn>
        {boot.me.can.write && <Btn variant="ghost" size="sm" onClick={() => setImporting(true)}><Upload className="size-4" />Import</Btn>}
        {manage && <Btn variant="ghost" size="sm" onClick={fromStaff} title="Zona'dagi Xodimlar tuzilmasidan (loyiha = brend, filial = shahar)"><Workflow className="size-4" />Tuzilmadan olish</Btn>}
      </div>
      {byBranch.size > 1 && !branch && (
        <div className="flex flex-wrap gap-1.5 px-4 pt-2">
          {[...byBranch.entries()].sort((a, b) => b[1] - a[1]).map(([name, n]) => (
            <span key={name} className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">{name}: <b>{n}</b></span>
          ))}
        </div>
      )}

      <div className="grid gap-2 px-3 pb-28 pt-3 sm:grid-cols-2 sm:px-4">
        {list.isLoading && <Spinner className="sm:col-span-2" />}
        {!list.isLoading && !rows.length && (
          <div className="sm:col-span-2">
            <Empty icon={<Users className="size-6" />} title="Xodim topilmadi"
              hint="Shablonni yuklab olib to'ldiring va Import qiling yoki «Xodim» tugmasi bilan qo'shing." />
          </div>
        )}
        {table && !!rows.length && (
          <div className="hidden overflow-x-auto rounded-xl border bg-card sm:col-span-2 md:block">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2.5 font-semibold">F.I.Sh.</th><th className="px-2 font-semibold">Lavozimi</th>
                  <th className="px-2 font-semibold">Telefon</th><th className="px-2 font-semibold">Filial</th>
                  <th className="px-2 font-semibold">Tashkilot</th><th className="px-2 font-semibold">Loyiha</th>
                  <th className="px-2 font-semibold">Bo'lim</th><th className="px-3 text-right font-semibold">Qurilmalar</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, limit).map((e) => (
                  <tr key={e.id} onClick={() => setEdit(e)} className="cursor-pointer border-b last:border-0 hover:bg-muted/40">
                    <td className="px-3 py-2.5 font-medium">{e.full_name}</td>
                    <td className="px-2 text-muted-foreground">{e.position || "—"}</td>
                    <td className="whitespace-nowrap px-2 text-muted-foreground">{e.phone || "—"}</td>
                    <td className="px-2">{e.branch_name || <span className="text-amber-600">filialsiz</span>}</td>
                    <td className="px-2 text-muted-foreground">{e.org_name || "—"}</td>
                    <td className="px-2 text-muted-foreground">{e.project || "—"}</td>
                    <td className="px-2 text-muted-foreground">{e.department || "—"}</td>
                    <td className="px-3 text-right">
                      <button onClick={(ev) => { ev.stopPropagation(); onShowItems(e.id); }} disabled={!e.devices}
                        className={cn("rounded-lg px-2 py-1 text-xs font-bold tabular-nums", e.devices ? "bg-emerald-500/12 text-emerald-700 hover:bg-emerald-500/20 dark:text-emerald-400" : "bg-muted text-muted-foreground")}>
                        <Laptop className="mr-1 inline size-3" />{e.devices}
                      </button>
                    </td>
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
                <span>{e.branch_name || <span className="text-amber-600">filialsiz</span>}</span>
                {e.org_name && <span>{e.org_name}</span>}
                {e.phone && <span className="inline-flex items-center gap-1"><Phone className="size-3" />{e.phone}</span>}
              </div>
            </div>
            <span className={cn("shrink-0 rounded-lg px-2 py-1 text-xs font-bold tabular-nums", e.devices ? "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400" : "bg-muted text-muted-foreground")}>
              <Laptop className="mr-1 inline size-3" />{e.devices}
            </span>
          </button>
        ))}
        {rows.length > limit && (
          <Btn variant="outline" className="sm:col-span-2" onClick={() => setLimit((l) => l + 200)}>Yana ko'rsatish ({rows.length - limit})</Btn>
        )}
      </div>
      <EmployeeForm open={!!edit || creating} emp={edit} onClose={() => { setEdit(null); setCreating(false); }} onShowItems={onShowItems} />
      <ImportDialog open={importing} onClose={() => setImporting(false)} title="Xodimlarni import qilish"
        hint={<>«Shablon» tugmasi bilan faylni yuklab oling, to'ldiring va shu yerga yuklang. Bir xil ismli xodim (shu filialda) qayta yaratilmaydi — yangilanadi. Inventarizatsiya shablonining «Xodimlar» varag'i ham qabul qilinadi.</>}
        run={(file, dry) => inv.importEmployees(file, dry)} />
    </div>
  );
}
