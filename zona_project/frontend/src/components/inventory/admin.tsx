"use client";
/* eslint-disable react/no-unescaped-entities -- o'zbekcha matnlardagi apostrof (o'z, ma'lumot) */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Copy, Download, FileSpreadsheet, FileText, KeyRound, Pencil, Plus, Sheet, ShieldCheck, Trash2, Upload, UserPlus, Users,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { download, inv, type AccessRow, type Branch, type DeviceType, type Level } from "./api";
import { ImportDialog } from "./import-dialog";
import { Btn, Card, Empty, Field, Overlay, Picker, SectionTitle, Spinner, StatusBadge, ago, dt, inputCls, useBoot } from "./ui";

const fail = (e: unknown) => toast.error(errorMessage(e));

/* ====================================================================== import / eksport markazi */
function Tile({ icon, title, hint, onClick, tone = "indigo" }: {
  icon: ReactNode; title: string; hint: string; onClick: () => void; tone?: "indigo" | "emerald" | "amber" | "violet";
}) {
  const tones = { indigo: "bg-indigo-500/10 text-indigo-600", emerald: "bg-emerald-500/10 text-emerald-600", amber: "bg-amber-500/10 text-amber-600", violet: "bg-violet-500/10 text-violet-600" };
  return (
    <button onClick={onClick} className="flex items-start gap-3 rounded-2xl border bg-card p-4 text-left shadow-xs transition-colors hover:border-primary/40">
      <span className={cn("grid size-11 shrink-0 place-items-center rounded-xl", tones[tone])}>{icon}</span>
      <div><div className="font-semibold">{title}</div><div className="mt-0.5 text-xs leading-snug text-muted-foreground">{hint}</div></div>
    </button>
  );
}

export function ExchangeView() {
  const boot = useBoot().data!;
  const [importing, setImporting] = useState(false);
  const [branch, setBranch] = useState("");
  const params = { branch: branch || undefined };
  return (
    <div className="mx-auto w-full max-w-4xl space-y-5 p-3 pb-28 sm:p-4">
      {boot.branches.length > 1 && (
        <Card>
          <Field label="Qaysi filial bo'yicha" hint="Bo'sh — barcha filiallar">
            <Picker title="Filial" placeholder="Barcha filiallar" value={branch} options={boot.branches.map((b) => ({ value: String(b.id), label: b.name }))} onChange={setBranch} />
          </Field>
        </Card>
      )}
      <div>
        <SectionTitle icon={<Download className="size-4" />}>Eksport — yuklab olish</SectionTitle>
        <div className="grid gap-2 sm:grid-cols-2">
          <Tile icon={<Sheet className="size-5" />} tone="emerald" title="Shablon formatida (to'ldirilgan)"
            hint="Asl «IT inventarizatsiya shabloni» — barcha varaqlar, formulalar, Xulosa va ochiluvchi ro'yxatlar bilan"
            onClick={() => download("items/export/", { ...params, fmt: "template" }).catch(fail)} />
          <Tile icon={<FileSpreadsheet className="size-5" />} title="Excel jadval"
            hint="Qurilmalar (rasm havolalari bilan), filiallar holati va xodimlar — alohida varaqlarda"
            onClick={() => download("items/export/", { ...params, fmt: "xlsx" }).catch(fail)} />
          <Tile icon={<FileText className="size-5" />} tone="violet" title="CSV"
            hint="Boshqa tizimlarga yuklash uchun (UTF-8, «;» ajratgich)"
            onClick={() => download("items/export/", { ...params, fmt: "csv" }).catch(fail)} />
          <Tile icon={<FileSpreadsheet className="size-5" />} tone="amber" title="Rahbarlar uchun hisobot"
            hint="Filiallar holati, sust filiallar, xodimlar faolligi, kunlik dinamika"
            onClick={() => download("stats/export/").catch(fail)} />
          <Tile icon={<Sheet className="size-5" />} title="Bo'sh shablon (oflayn to'ldirish)"
            hint="Katalog, filiallar va xodimlar bilan tayyor, qurilmalarsiz — internet yo'q joyda Excelda to'ldirib, keyin import qiling"
            onClick={() => download("items/export/", { ...params, fmt: "template", empty: 1 }).catch(fail)} />
          <Tile icon={<Users className="size-5" />} tone="violet" title="Xodimlar ro'yxati"
            hint="Excel — filial, tashkilot, loyiha va qurilmalar soni bilan"
            onClick={() => download("employees/export/", { ...params, fmt: "xlsx" }).catch(fail)} />
        </div>
      </div>
      {boot.me.can.write && (
        <div>
          <SectionTitle icon={<Upload className="size-4" />}>Import — fayldan yuklash</SectionTitle>
          <div className="grid gap-2 sm:grid-cols-2">
            <Tile icon={<Upload className="size-5" />} tone="emerald" title="Qurilmalarni import qilish"
              hint="To'ldirilgan shablon, yuqoridagi Excel/CSV eksporti. Avval tekshiriladi, keyin tasdiqlaysiz."
              onClick={() => setImporting(true)} />
            <Tile icon={<FileSpreadsheet className="size-5" />} title="Xodimlar shablonini olish"
              hint="Xodimlar bo'limidagi Import bilan yuklanadi"
              onClick={() => download("employees/template/").catch(fail)} />
          </div>
        </div>
      )}
      <ImportDialog open={importing} onClose={() => setImporting(false)} title="Qurilmalarni import qilish"
        hint={<>Qabul qilinadi: <b>to'ldirilgan shablon</b> (Inventarizatsiya + Xodimlar varaqlari) yoki shu yerdan olingan <b>Excel/CSV</b>. Inventar raqami yoki (filial + tur + seriya) mos kelsa — qator yangilanadi, dublikat yaratilmaydi. Ro'yxatda yo'q xodim avtomatik qo'shiladi.</>}
        run={(file, dry) => inv.importItems(file, dry, branch ? Number(branch) : null)} />
    </div>
  );
}

/* ====================================================================== filiallar */
function BranchForm(props: { open: boolean; onClose: () => void; branch: Branch | null }) {
  return props.open ? <BranchFormBody key={props.branch?.id ?? "new"} {...props} /> : null;
}

function BranchFormBody({ open, onClose, branch }: { open: boolean; onClose: () => void; branch: Branch | null }) {
  const qc = useQueryClient();
  const boot = useBoot().data!;
  const [f, setF] = useState<Partial<Branch>>(() => branch ?? {});
  const [busy, setBusy] = useState(false);
  const manage = boot.me.can.manage;
  const save = async () => {
    setBusy(true);
    try {
      const body = manage ? f : { status: f.status, conductor: f.conductor };
      if (branch) await inv.updateBranch(branch.id, body);
      else await inv.createBranch(f);
      qc.invalidateQueries({ queryKey: ["inv"] });
      toast.success("Saqlandi");
      onClose();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!branch || !confirm(`${branch.name} o'chirilsinmi?`)) return;
    try { await inv.deleteBranch(branch.id); qc.invalidateQueries({ queryKey: ["inv"] }); onClose(); } catch (e) { fail(e); }
  };
  return (
    <Overlay open={open} onClose={onClose} title={branch ? branch.name : "Yangi filial"}
      footer={<Btn size="lg" className="w-full" loading={busy} onClick={save}>Saqlash</Btn>}>
      <div className="space-y-4 p-4">
        {manage && (
          <div className="grid grid-cols-[110px_1fr] gap-3">
            <Field label="Kod" required><input className={cn(inputCls, "uppercase")} value={f.code ?? ""} onChange={(e) => setF({ ...f, code: e.target.value })} placeholder="SAM" /></Field>
            <Field label="Nomi" required><input className={inputCls} value={f.name ?? ""} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
            <Field label="Viloyat" className="col-span-2"><input className={inputCls} value={f.region ?? ""} onChange={(e) => setF({ ...f, region: e.target.value })} /></Field>
            <Field label="Izoh" className="col-span-2"><input className={inputCls} value={f.note ?? ""} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
          </div>
        )}
        {branch && (
          <>
            <Field label="Holati">
              <div className="flex flex-wrap gap-2">
                {boot.branch_statuses.map((s) => (
                  <button key={s.value} onClick={() => setF({ ...f, status: s.value })}
                    className={cn("h-11 rounded-xl border px-4 text-sm font-semibold", f.status === s.value ? "border-primary bg-primary text-primary-foreground" : "bg-card")}>{s.label}</button>
                ))}
              </div>
            </Field>
            <Field label="Inventarizatsiya o'tkazuvchi (F.I.Sh.)">
              <input className={inputCls} value={f.conductor ?? ""} onChange={(e) => setF({ ...f, conductor: e.target.value })} />
            </Field>
            <div className="text-xs text-muted-foreground">Boshlangan: {branch.started_at ?? "—"} · Yakunlangan: {branch.finished_at ?? "—"}</div>
            {manage && <Btn variant="danger" onClick={remove}><Trash2 className="size-4" />Filialni o'chirish</Btn>}
          </>
        )}
      </div>
    </Overlay>
  );
}

export function BranchesView({ onOpen }: { onOpen: (id: number) => void }) {
  const boot = useBoot().data!;
  const stats = useQuery({ queryKey: ["inv", "stats", 30], queryFn: () => inv.stats({ days: 30 }) });
  const [edit, setEdit] = useState<Branch | null>(null);
  const [creating, setCreating] = useState(false);
  const statById = new Map((stats.data?.branches ?? []).map((b) => [b.id, b]));
  return (
    <div className="mx-auto w-full max-w-5xl space-y-3 p-3 pb-28 sm:p-4">
      <div className="flex items-center gap-2">
        <h2 className="mr-auto text-lg font-bold">Filiallar ({boot.branches.length})</h2>
        {boot.me.can.manage && <Btn onClick={() => setCreating(true)}><Plus className="size-4" />Filial</Btn>}
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {boot.branches.map((b) => {
          const s = statById.get(b.id);
          return (
            <div key={b.id} className="rounded-2xl border bg-card p-4 shadow-xs">
              <div className="flex items-start gap-2">
                <span className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs font-bold">{b.code}</span>
                <div className="min-w-0 flex-1"><div className="font-semibold">{b.name}</div><div className="text-xs text-muted-foreground">{b.region}{b.note ? ` · ${b.note}` : ""}</div></div>
                <StatusBadge value={b.status} label={b.status_label} />
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-lg bg-muted/50 py-2"><div className="text-base font-bold">{s?.qty ?? "…"}</div>dona</div>
                <div className="rounded-lg bg-muted/50 py-2"><div className="text-base font-bold">{s?.employees ?? "…"}</div>xodim</div>
                <div className="rounded-lg bg-muted/50 py-2"><div className="text-base font-bold">{s?.collectors ?? "…"}</div>login</div>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">O'tkazuvchi: {b.conductor || "—"} · oxirgi: {ago(s?.last_at)}</div>
              <div className="mt-3 flex gap-2">
                <Btn variant="soft" size="sm" className="flex-1" onClick={() => onOpen(b.id)}>Qurilmalari</Btn>
                {boot.me.can.write && <Btn variant="outline" size="sm" onClick={() => setEdit(b)}><Pencil className="size-4" /></Btn>}
              </div>
            </div>
          );
        })}
      </div>
      <BranchForm open={!!edit || creating} branch={edit} onClose={() => { setEdit(null); setCreating(false); }} />
    </div>
  );
}

/* ====================================================================== foydalanuvchilar */
function copy(text: string) {
  navigator.clipboard?.writeText(text).then(() => toast.success("Nusxa olindi"), () => undefined);
}

function UserForm(props: { open: boolean; onClose: () => void; row: AccessRow | null }) {
  return props.open ? <UserFormBody key={props.row?.id ?? "new"} {...props} /> : null;
}

function UserFormBody({ open, onClose, row }: { open: boolean; onClose: () => void; row: AccessRow | null }) {
  const boot = useBoot().data!;
  const qc = useQueryClient();
  const [f, setF] = useState<{ username: string; first_name: string; last_name: string; level: Level; branches: number[]; password: string; existing: boolean; note: string; is_active: boolean }>(
    () => row ? { username: row.username, first_name: row.first_name, last_name: row.last_name, level: row.level, branches: row.branches, password: "", existing: false, note: row.note, is_active: row.is_active }
      : { username: "", first_name: "", last_name: "", level: "collector", branches: [], password: "", existing: false, note: "", is_active: true });
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<{ username: string; password: string } | null>(null);
  const save = async () => {
    setBusy(true);
    try {
      if (row) {
        await inv.updateUser(row.id, { first_name: f.first_name, last_name: f.last_name, level: f.level, branches: f.branches, note: f.note, is_active: f.is_active });
        toast.success("Saqlandi");
        onClose();
      } else {
        const r = await inv.createUser(f.existing ? { existing_username: f.username, level: f.level, branches: f.branches }
          : { username: f.username, first_name: f.first_name, last_name: f.last_name, level: f.level, branches: f.branches, password: f.password, note: f.note });
        if (r.password) setCreated({ username: r.username, password: r.password });
        else { toast.success("Huquq berildi"); onClose(); }
      }
      qc.invalidateQueries({ queryKey: ["inv", "users"] });
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const toggleBranch = (id: number) => setF((x) => ({ ...x, branches: x.branches.includes(id) ? x.branches.filter((b) => b !== id) : [...x.branches, id] }));
  return (
    <Overlay open={open} onClose={onClose} title={row ? row.username : "Yangi foydalanuvchi"}
      footer={created ? <Btn size="lg" className="w-full" onClick={onClose}>Tayyor</Btn> : <Btn size="lg" className="w-full" loading={busy} onClick={save}>Saqlash</Btn>}>
      {created ? (
        <div className="space-y-3 p-4">
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
            <div className="text-sm text-muted-foreground">Login</div><div className="font-mono text-lg font-bold">{created.username}</div>
            <div className="mt-2 text-sm text-muted-foreground">Parol</div><div className="font-mono text-lg font-bold">{created.password}</div>
          </div>
          <Btn variant="outline" className="w-full" onClick={() => copy(`Sayt: ${window.location.origin}/inventory\nLogin: ${created.username}\nParol: ${created.password}`)}><Copy className="size-4" />Nusxa olish (Telegram uchun)</Btn>
        </div>
      ) : (
        <div className="space-y-4 p-4">
          {!row && (
            <div className="flex rounded-xl border bg-card p-0.5 text-sm">
              <button onClick={() => setF({ ...f, existing: false })} className={cn("h-9 flex-1 rounded-lg font-semibold", !f.existing && "bg-primary text-primary-foreground")}>Yangi login</button>
              <button onClick={() => setF({ ...f, existing: true })} className={cn("h-9 flex-1 rounded-lg font-semibold", f.existing && "bg-primary text-primary-foreground")}>Mavjud foydalanuvchiga</button>
            </div>
          )}
          {!row && (
            <Field label={f.existing ? "Mavjud login (platformadagi)" : "Login"} required hint={f.existing ? "Uning platformadagi roli o'zgarmaydi — faqat shu modulga huquq qo'shiladi" : "Yangi login faqat shu modulga kira oladi"}>
              <input className={cn(inputCls, "font-mono")} value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} autoCapitalize="none" placeholder="inv.sam" />
            </Field>
          )}
          {!f.existing && (
            <div className="grid grid-cols-2 gap-3">
              <Field label="Ism"><input className={inputCls} value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} /></Field>
              <Field label="Familiya"><input className={inputCls} value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} /></Field>
            </div>
          )}
          {!row && !f.existing && (
            <Field label="Parol" hint="Bo'sh qoldirsangiz — avtomatik yaratiladi (8 belgi, oson o'qiladi)">
              <input className={cn(inputCls, "font-mono")} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
            </Field>
          )}
          <Field label="Daraja">
            <div className="space-y-2">
              {boot.levels.map((l) => (
                <button key={l.value} onClick={() => setF({ ...f, level: l.value })}
                  className={cn("flex w-full items-center gap-3 rounded-xl border p-3 text-left", f.level === l.value && "border-primary bg-primary/5")}>
                  <span className={cn("size-4 rounded-full border-2", f.level === l.value && "border-[5px] border-primary")} />
                  <div><div className="text-sm font-semibold">{l.label}</div>
                    <div className="text-xs text-muted-foreground">{l.value === "manager" ? "Hamma narsa: filiallar, loginlar, katalog, import/eksport" : l.value === "director" ? "Barcha filiallar natijasi va analitikasini ko'radi, o'zgartira olmaydi" : "Faqat o'z filiali: qurilma va xodim qo'shadi"}</div></div>
                </button>
              ))}
            </div>
          </Field>
          {f.level === "collector" && (
            <Field label="Filiallar" hint="Faqat shu filiallarni ko'radi va to'ldiradi">
              <div className="flex flex-wrap gap-2">
                {boot.branches.map((b) => (
                  <button key={b.id} onClick={() => toggleBranch(b.id)}
                    className={cn("h-10 rounded-xl border px-3 text-sm font-medium", f.branches.includes(b.id) ? "border-primary bg-primary text-primary-foreground" : "bg-card")}>{b.name}</button>
                ))}
              </div>
            </Field>
          )}
          {row && (
            <label className="flex items-center gap-3 rounded-xl border p-3">
              <input type="checkbox" className="size-5" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />
              <span className="text-sm">Faol (o'chirilsa — kira olmaydi)</span>
            </label>
          )}
        </div>
      )}
    </Overlay>
  );
}

export function UsersView() {
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["inv", "users"], queryFn: inv.users });
  const [edit, setEdit] = useState<AccessRow | null>(null);
  const [creating, setCreating] = useState(false);
  const [generated, setGenerated] = useState<{ username: string; password: string; branch: string }[] | null>(null);
  const [busy, setBusy] = useState(false);
  const generate = async () => {
    if (!confirm("Logini yo'q har bir filial uchun bitta login (inv.sam, inv.and…) yaratilsinmi?")) return;
    setBusy(true);
    try {
      const r = await inv.generateUsers();
      setGenerated(r.created);
      qc.invalidateQueries({ queryKey: ["inv", "users"] });
      if (!r.created.length) toast.info("Barcha filiallarda login bor");
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const reset = async (row: AccessRow) => {
    if (!confirm(`${row.username} uchun yangi parol yaratilsinmi? Eski parol ishlamay qoladi.`)) return;
    try {
      const r = await inv.resetPassword(row.id);
      setGenerated([{ username: r.username, password: r.password, branch: row.branch_names.join(", ") }]);
      qc.invalidateQueries({ queryKey: ["inv", "users"] });
    } catch (e) { fail(e); }
  };
  const remove = async (row: AccessRow) => {
    if (!confirm(`${row.username} dan huquq olinsinmi?`)) return;
    try { await inv.deleteUser(row.id); qc.invalidateQueries({ queryKey: ["inv", "users"] }); } catch (e) { fail(e); }
  };
  const rows = users.data ?? [];
  return (
    <div className="mx-auto w-full max-w-5xl space-y-3 p-3 pb-28 sm:p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-lg font-bold">Foydalanuvchilar va huquqlar</h2>
        <Btn variant="outline" size="sm" onClick={() => download("users/credentials/").catch(fail)}><Download className="size-4" />Loginlar fayli (Excel)</Btn>
        <Btn variant="outline" size="sm" loading={busy} onClick={generate}><KeyRound className="size-4" />Filiallarga login yaratish</Btn>
        <Btn size="sm" onClick={() => setCreating(true)}><UserPlus className="size-4" />Foydalanuvchi</Btn>
      </div>
      <p className="text-xs text-muted-foreground">Platforma administratorlari bu modulga avtomatik «Boshqaruvchi» sifatida kiradi. Filial loginlari platformaning boshqa sahifalarini ko'rmaydi.</p>
      {users.isLoading ? <Spinner /> : !rows.length ? (
        <Empty icon={<ShieldCheck className="size-6" />} title="Hali foydalanuvchi yo'q" hint="«Filiallarga login yaratish» — har bir filial uchun tayyor login va parol." />
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {rows.map((r) => (
            <div key={r.id} className={cn("rounded-2xl border bg-card p-3 shadow-xs", !r.is_active && "opacity-60")}>
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <div className="font-mono font-semibold">{r.username}</div>
                  <div className="text-xs text-muted-foreground">{r.name} · {r.level_label}</div>
                  <div className="mt-1 text-xs">{r.branch_names.join(", ") || (r.level === "collector" ? <span className="text-amber-600">filial biriktirilmagan</span> : "Barcha filiallar")}</div>
                  <div className="mt-1 text-[11px] text-muted-foreground">Kirgan: {r.last_login ? dt(r.last_login) : "hali kirmagan"} · {r.items} ta qurilma kiritgan</div>
                </div>
                {!r.is_active && <span className="rounded-full bg-red-500/10 px-2 text-[11px] font-semibold text-red-600">bloklangan</span>}
              </div>
              <div className="mt-2 flex gap-1.5">
                <Btn variant="outline" size="sm" onClick={() => setEdit(r)}><Pencil className="size-3.5" />Tahrirlash</Btn>
                <Btn variant="outline" size="sm" onClick={() => reset(r)}><KeyRound className="size-3.5" />Yangi parol</Btn>
                <Btn variant="ghost" size="sm" className="ml-auto text-destructive" onClick={() => remove(r)}><Trash2 className="size-3.5" /></Btn>
              </div>
            </div>
          ))}
        </div>
      )}
      <UserForm open={!!edit || creating} row={edit} onClose={() => { setEdit(null); setCreating(false); }} />
      <Overlay open={!!generated?.length} onClose={() => setGenerated(null)} title="Yangi loginlar"
        footer={<div className="flex gap-2">
          <Btn variant="outline" className="flex-1" onClick={() => copy((generated ?? []).map((g) => `${g.branch}: ${g.username} / ${g.password}`).join("\n") + `\nSayt: ${window.location.origin}/inventory`)}><Copy className="size-4" />Nusxa</Btn>
          <Btn className="flex-1" onClick={() => download("users/credentials/").catch(fail)}><Download className="size-4" />Excel fayl</Btn>
        </div>}>
        <div className="space-y-2 p-4">
          <p className="text-sm text-muted-foreground">Parollarni hozir saqlab oling. Keyin ham «Loginlar fayli» orqali yuklab olish mumkin (foydalanuvchi parolini o'zi o'zgartirmagan bo'lsa).</p>
          {(generated ?? []).map((g) => (
            <div key={g.username} className="flex items-center gap-3 rounded-xl border p-3">
              <div className="min-w-0 flex-1"><div className="text-xs text-muted-foreground">{g.branch}</div><div className="font-mono font-semibold">{g.username}</div></div>
              <div className="font-mono text-lg font-bold">{g.password}</div>
            </div>
          ))}
        </div>
      </Overlay>
    </div>
  );
}

/* ====================================================================== katalog */
function TypeForm(props: { open: boolean; onClose: () => void; type: DeviceType | null }) {
  return props.open ? <TypeFormBody key={props.type?.id ?? "new"} {...props} /> : null;
}

function TypeFormBody({ open, onClose, type }: { open: boolean; onClose: () => void; type: DeviceType | null }) {
  const qc = useQueryClient();
  const [f, setF] = useState<Partial<DeviceType> & { brandsText?: string }>(() => type ? { ...type, brandsText: type.brands.join(", ") } : { brandsText: "", is_active: true });
  const save = async () => {
    try {
      await inv.saveCatalog({ kind: "device_type", id: type?.id, ...f, brands: f.brandsText ?? "" });
      qc.invalidateQueries({ queryKey: ["inv", "boot"] });
      toast.success("Saqlandi");
      onClose();
    } catch (e) { fail(e); }
  };
  const remove = async () => {
    if (!type || !confirm(`${type.name} o'chirilsinmi?`)) return;
    try { await inv.saveCatalog({ kind: "device_type", id: type.id, delete: true }); qc.invalidateQueries({ queryKey: ["inv", "boot"] }); onClose(); } catch (e) { fail(e); }
  };
  return (
    <Overlay open={open} onClose={onClose} title={type ? type.name : "Yangi qurilma turi"} footer={<Btn size="lg" className="w-full" onClick={save}>Saqlash</Btn>}>
      <div className="space-y-3 p-4">
        <Field label="Qurilma turi" required><input className={inputCls} value={f.name ?? ""} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Guruh" hint="Kompyuter, Printer, Tarmoq…"><input className={inputCls} value={f.group ?? ""} onChange={(e) => setF({ ...f, group: e.target.value })} /></Field>
        <Field label="Bu nima? (oddiy tushuntirish)"><input className={inputCls} value={f.description ?? ""} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="Seriya raqami qayerda?"><input className={inputCls} value={f.serial_hint ?? ""} onChange={(e) => setF({ ...f, serial_hint: e.target.value })} /></Field>
        <Field label="Qo'shimcha nima yozish kerak"><input className={inputCls} value={f.extra_hint ?? ""} onChange={(e) => setF({ ...f, extra_hint: e.target.value })} /></Field>
        <Field label="Brendlar" hint="Vergul bilan: HP, Lenovo, Dell"><input className={inputCls} value={f.brandsText ?? ""} onChange={(e) => setF({ ...f, brandsText: e.target.value })} /></Field>
        {type && <Btn variant="danger" onClick={remove}><Trash2 className="size-4" />O'chirish (ishlatilgan bo'lsa — nofaol qilinadi)</Btn>}
      </div>
    </Overlay>
  );
}

function SimpleList({ title, kind, rows }: { title: string; kind: "org" | "location"; rows: { id: number; name: string }[] }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const add = async () => {
    if (!text.trim()) return;
    try { await inv.saveCatalog({ kind, name: text.trim() }); setText(""); qc.invalidateQueries({ queryKey: ["inv", "boot"] }); } catch (e) { fail(e); }
  };
  const remove = async (id: number, name: string) => {
    if (!confirm(`${name} o'chirilsinmi?`)) return;
    try { await inv.saveCatalog({ kind, id, delete: true }); qc.invalidateQueries({ queryKey: ["inv", "boot"] }); } catch (e) { fail(e); }
  };
  return (
    <Card>
      <SectionTitle>{title}</SectionTitle>
      <div className="flex flex-wrap gap-1.5">
        {rows.map((r) => (
          <span key={r.id} className="inline-flex items-center gap-1 rounded-full border bg-muted/40 py-1 pl-3 pr-1 text-sm">
            {r.name}<button onClick={() => remove(r.id, r.name)} className="grid size-6 place-items-center rounded-full text-muted-foreground hover:bg-muted"><Trash2 className="size-3" /></button>
          </span>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <input className={inputCls} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} placeholder="Yangi qiymat…" />
        <Btn onClick={add}><Plus className="size-4" /></Btn>
      </div>
    </Card>
  );
}

export function CatalogView() {
  const boot = useBoot().data!;
  const [edit, setEdit] = useState<DeviceType | null>(null);
  const [creating, setCreating] = useState(false);
  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 p-3 pb-28 sm:p-4">
      <Card>
        <SectionTitle right={<Btn size="sm" onClick={() => setCreating(true)}><Plus className="size-4" />Tur</Btn>}>Qurilma turlari ({boot.device_types.length})</SectionTitle>
        <div className="divide-y">
          {boot.device_types.map((d) => (
            <button key={d.id} onClick={() => setEdit(d)} className={cn("flex w-full items-start gap-3 py-2.5 text-left hover:bg-muted/30", !d.is_active && "opacity-50")}>
              <span className="w-24 shrink-0 text-xs text-muted-foreground">{d.group}</span>
              <div className="min-w-0 flex-1"><div className="text-sm font-medium">{d.name}{!d.is_active && " (nofaol)"}</div><div className="truncate text-xs text-muted-foreground">{d.brands.join(", ")}</div></div>
              <Pencil className="size-3.5 shrink-0 text-muted-foreground" />
            </button>
          ))}
        </div>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <SimpleList title="Tashkilotlar (loyihalar)" kind="org" rows={boot.orgs} />
        <SimpleList title="Joylar (qayerda turibdi)" kind="location" rows={boot.locations} />
      </div>
      <TypeForm open={!!edit || creating} type={edit} onClose={() => { setEdit(null); setCreating(false); }} />
    </div>
  );
}

/* ====================================================================== tarix */
export function HistoryView({ onOpenItem }: { onOpenItem: (id: number) => void }) {
  const boot = useBoot().data!;
  const [branch, setBranch] = useState("");
  const [user, setUser] = useState("");
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [page, setPage] = useState(1);
  const params = { branch, user, action, entity, page, page_size: 50 };
  const logs = useQuery({ queryKey: ["inv", "logs", params], queryFn: () => inv.logs(params) });
  const d = logs.data;
  const ACT_STYLE: Record<string, string> = { create: "bg-emerald-500/12 text-emerald-700", update: "bg-blue-500/12 text-blue-700", delete: "bg-red-500/12 text-red-700",
    restore: "bg-violet-500/12 text-violet-700", import: "bg-amber-500/15 text-amber-700", status: "bg-sky-500/12 text-sky-700", login: "bg-zinc-500/12 text-zinc-700" };
  return (
    <div className="mx-auto w-full max-w-5xl space-y-3 p-3 pb-28 sm:p-4">
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        {boot.branches.length > 1 && <Picker title="Filial" placeholder="Barcha filiallar" value={branch} options={boot.branches.map((b) => ({ value: String(b.id), label: b.name }))} onChange={(v) => { setBranch(v); setPage(1); }} />}
        <Picker title="Foydalanuvchi" placeholder="Hamma" value={user} options={(d?.users ?? []).map((u) => ({ value: String(u.id), label: u.name }))} onChange={(v) => { setUser(v); setPage(1); }} />
        <Picker title="Amal" placeholder="Barcha amallar" value={action} onChange={(v) => { setAction(v); setPage(1); }}
          options={[["create", "Qo'shdi"], ["update", "O'zgartirdi"], ["delete", "O'chirdi"], ["restore", "Tikladi"], ["import", "Import"], ["status", "Holat"]].map(([value, label]) => ({ value, label }))} />
        <Picker title="Nima" placeholder="Hammasi" value={entity} onChange={(v) => { setEntity(v); setPage(1); }}
          options={[["item", "Qurilmalar"], ["employee", "Xodimlar"], ["branch", "Filiallar"], ["user", "Foydalanuvchilar"], ["catalog", "Katalog"]].map(([value, label]) => ({ value, label }))} />
      </div>
      <div className="text-sm text-muted-foreground"><b className="text-foreground">{d?.count ?? "…"}</b> yozuv</div>
      {logs.isLoading ? <Spinner /> : (
        <div className="space-y-1.5">
          {(d?.results ?? []).map((l) => (
            <button key={l.id} disabled={!l.item} onClick={() => l.item && onOpenItem(l.item)}
              className="flex w-full items-start gap-3 rounded-xl border bg-card px-3 py-2.5 text-left enabled:hover:border-primary/40">
              <span className={cn("mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold dark:text-foreground", ACT_STYLE[l.action] ?? "bg-muted")}>{l.action_label}</span>
              <div className="min-w-0 flex-1">
                <div className="text-sm">{l.summary}</div>
                {Object.entries(l.changes || {}).slice(0, 4).map(([k, v]) => (
                  <div key={k} className="text-xs text-muted-foreground">{k}: <s>{String(v[0] ?? "")}</s> → {String(v[1] ?? "")}</div>
                ))}
                <div className="mt-0.5 text-xs text-muted-foreground">{l.user || "tizim"}{l.branch ? ` · ${l.branch}` : ""} · {dt(l.at)}</div>
              </div>
            </button>
          ))}
          {!d?.results.length && <Empty title="Tarix bo'sh" />}
        </div>
      )}
      {d && d.count > d.page_size && (
        <div className="flex items-center justify-center gap-2">
          <Btn variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Oldingi</Btn>
          <span className="text-sm">{page} / {Math.ceil(d.count / d.page_size)}</span>
          <Btn variant="outline" size="sm" disabled={page * d.page_size >= d.count} onClick={() => setPage(page + 1)}>Keyingi</Btn>
        </div>
      )}
    </div>
  );
}
