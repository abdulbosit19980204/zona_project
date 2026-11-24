"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, CheckCircle2, Clock, Copy, Download, ExternalLink, FileSignature, Link2, Printer, Send, Share2,
  ShieldCheck, Users, XCircle,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { download, inv, type Ack, type AckStatus, type Employee } from "./api";
import { condLabel, tr, useLang, useT } from "./i18n";
import { Btn, Card, Empty, Kpi, Overlay, Picker, Spinner, ago, dt, useBoot } from "./ui";

/* ------------------------------------------------------------------ havola va xabar */
export function ackLink(path: string) {
  return typeof window === "undefined" ? path : `${window.location.origin}${path}`;
}

/** Xodimga yuboriladigan xabar: ikki tilda (xodim qaysi tilni bilishi noma'lum). */
export function ackMessage(name: string, link: string) {
  return `Assalomu alaykum, ${name}! StarGroup IT inventarizatsiyasi: sizga biriktirilgan qurilmalar ro'yxatini tekshirib, imzo bilan tasdiqlang:\n${link}\n\n`
    + `Здравствуйте, ${name}! ИТ-инвентаризация StarGroup: проверьте список закреплённых за вами устройств и подтвердите подписью:\n${link}`;
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(tr("Nusxa olindi"));
    return true;
  } catch {
    toast.error(tr("Nusxa olib bo'lmadi — matnni qo'lda belgilang"));
    return false;
  }
}

export const ACK_STYLE: Record<AckStatus | "none", string> = {
  signed: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400",
  pending: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  revoked: "bg-zinc-500/15 text-zinc-600",
  none: "bg-zinc-500/12 text-zinc-600 dark:text-zinc-300",
};
const ACK_LABEL: Record<AckStatus | "none", string> = {
  signed: "Imzolangan", pending: "Imzo kutilmoqda", revoked: "Bekor qilingan", none: "Havola yuborilmagan",
};
export function AckBadge({ status, opened }: { status: AckStatus | "none"; opened?: boolean }) {
  const t = useT();
  const Icon = status === "signed" ? CheckCircle2 : status === "pending" ? Clock : Link2;
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold", ACK_STYLE[status])}>
      <Icon className="size-3" />{t(ACK_LABEL[status])}{status === "pending" && opened ? ` · ${t("ochilgan")}` : ""}
    </span>
  );
}

/* ------------------------------------------------------------------ havolani yuborish oynasi */
export function AckShare({ ack, onClose }: { ack: Ack | null; onClose: () => void }) {
  const t = useT();
  if (!ack) return null;
  const link = ackLink(ack.path);
  const msg = ackMessage(ack.employee_name, link);
  const openChat = async () => {
    await copyText(msg);
    window.open(`https://t.me/${ack.telegram}`, "_blank", "noopener");
  };
  const share = async () => {
    if (navigator.share) {
      try { await navigator.share({ text: msg }); return; } catch { /* bekor qilindi */ }
    }
    window.open(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(msg.replace(link, "").trim())}`, "_blank", "noopener");
  };
  return (
    <Overlay open onClose={onClose} title={t("Tasdiqlash havolasi")} subtitle={ack.employee_name} z={80}>
      <div className="space-y-4 p-4">
        <div className="rounded-xl border bg-muted/40 p-3">
          <div className="mb-1 text-xs text-muted-foreground">{t("Havola")}</div>
          <div className="break-all font-mono text-sm">{link}</div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="rounded-xl border p-3"><div className="text-xs text-muted-foreground">{t("Telefon")}</div><div className="font-medium">{ack.phone || "—"}</div></div>
          <div className="rounded-xl border p-3"><div className="text-xs text-muted-foreground">Telegram</div><div className="font-medium">{ack.telegram ? `@${ack.telegram}` : "—"}</div></div>
        </div>
        <div className="space-y-2">
          {ack.telegram && (
            <Btn className="w-full" size="lg" onClick={openChat}><Send className="size-4" />{t("Telegram'da yozish (xabar nusxalanadi)")}</Btn>
          )}
          <Btn variant="outline" className="w-full" size="lg" onClick={share}><Share2 className="size-4" />{t("Ulashish (Telegram, SMS…)")}</Btn>
          <Btn variant="outline" className="w-full" size="lg" onClick={() => copyText(msg)}><Copy className="size-4" />{t("Xabarni nusxalash")}</Btn>
          {ack.phone && (
            <a href={`sms:${ack.phone.replace(/\s/g, "")}?body=${encodeURIComponent(msg)}`}
              className="flex h-11 items-center justify-center gap-2 rounded-xl border text-sm font-semibold hover:bg-muted">{t("SMS yuborish")}</a>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {t("Xodim havolani ochib, o'zidagi qurilmalarni rasmlari bilan ko'radi, har birini «menda bor / yo'q» deb belgilaydi va imzo qo'yadi. Natija shu yerda ko'rinadi.")}
        </p>
      </div>
    </Overlay>
  );
}

/** Xodim uchun yangi havola yaratib, yuborish oynasini ochadi. */
export function useCreateAck() {
  const qc = useQueryClient();
  const [shown, setShown] = useState<Ack | null>(null);
  const create = async (emp: Pick<Employee, "id">) => {
    try {
      const ack = await inv.createAck(emp.id);
      setShown(ack);
      qc.invalidateQueries({ queryKey: ["inv"], predicate: (q) => q.queryKey[1] !== "boot" });
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };
  return { create, dialog: <AckShare ack={shown} onClose={() => setShown(null)} /> };
}

/* ------------------------------------------------------------------ imzolangan dalolatnoma */
function printAct(a: Ack) {
  const w = window.open("", "_blank");
  if (!w) return;
  const esc = (s: unknown) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c]!));
  const rows = (a.items ?? []).map((it, i) => `<tr><td>${i + 1}</td><td>${esc(it.inv_number)}</td><td>${esc(it.type)}</td>
    <td>${esc([it.brand, it.model].filter(Boolean).join(" "))}</td><td>${esc(it.serial)}</td><td>${it.quantity}</td>
    <td>${esc(condLabel(it.condition))}</td><td>${it.result && !it.result.ok ? `<b>${esc(tr("Menda yo'q"))}</b> ${esc(it.result.comment)}` : esc(tr("Tasdiqlandi"))}</td></tr>`).join("");
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(tr("Dalolatnoma"))} — ${esc(a.employee_name)}</title>
  <style>body{font:13px/1.45 system-ui,sans-serif;margin:32px;color:#111}h1{font-size:18px;margin:0 0 4px}table{width:100%;border-collapse:collapse;margin:16px 0}
  td,th{border:1px solid #bbb;padding:5px 7px;text-align:left;vertical-align:top}th{background:#f1f1f1}.muted{color:#555}.sig{height:110px;border-bottom:1px solid #333}</style></head><body>
  <h1>${esc(tr("Qurilmalarni qabul qilish-tasdiqlash dalolatnomasi"))}</h1>
  <div class="muted">StarGroup · ${esc(tr("IT inventarizatsiya"))} · ${esc(a.branch)}</div>
  <p>${esc(tr("Xodim"))}: <b>${esc(a.employee_name)}</b>${a.position ? ` (${esc(a.position)})` : ""} · ${esc(a.phone)} ${a.telegram ? "· @" + esc(a.telegram) : ""}</p>
  <table><tr><th>№</th><th>${esc(tr("Inv. raqam"))}</th><th>${esc(tr("Qurilma"))}</th><th>${esc(tr("Brend / model"))}</th><th>S/N</th><th>${esc(tr("Soni"))}</th><th>${esc(tr("Holati"))}</th><th>${esc(tr("Xodim javobi"))}</th></tr>${rows}</table>
  ${a.comment ? `<p>${esc(tr("Izoh"))}: ${esc(a.comment)}</p>` : ""}
  <p>${esc(tr("Imzoladi"))}: <b>${esc(a.signer_name)}</b> · ${esc(dt(a.signed_at))}</p>
  ${a.signature_url ? `<img class="sig" src="${esc(window.location.origin + a.signature_url)}">` : ""}
  <p class="muted" style="font-size:11px">IP: ${esc(a.ip)} · ${esc(a.user_agent)}</p>
  <script>window.onload=()=>setTimeout(()=>window.print(),300)</script></body></html>`);
  w.document.close();
}

export function AckDetail({ id, onClose }: { id: number | null; onClose: () => void }) {
  const t = useT();
  const lang = useLang();
  const q = useQuery({ queryKey: ["inv", "ack", id], queryFn: () => inv.ack(id!), enabled: !!id });
  const a = q.data;
  if (!id) return null;
  return (
    <Overlay open onClose={onClose} wide title={a?.employee_name ?? t("Tasdiqnoma")} subtitle={a ? `${a.branch} · ${a.items_count} ${t("ta qurilma")}` : undefined}
      footer={a?.status === "signed" ? <Btn className="w-full" onClick={() => printAct(a)}><Printer className="size-4" />{t("Dalolatnomani chop etish / PDF")}</Btn> : undefined}>
      {!a ? <Spinner /> : (
        <div className="space-y-4 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <AckBadge status={a.status} opened={!!a.opened_at} />
            {a.outdated && <span className="rounded-full bg-orange-500/12 px-2 py-0.5 text-[11px] font-semibold text-orange-700">{t("Qurilmalar o'zgargan — yangi havola kerak")}</span>}
            {a.issues > 0 && <span className="rounded-full bg-red-500/12 px-2 py-0.5 text-[11px] font-semibold text-red-700">{t("{n} ta e'tiroz", { n: a.issues })}</span>}
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground sm:grid-cols-4">
            <div>{t("Yaratildi")}<br /><b className="text-foreground">{dt(a.created_at)}</b></div>
            <div>{t("Ochildi")}<br /><b className="text-foreground">{dt(a.opened_at)}</b></div>
            <div>{t("Imzolandi")}<br /><b className="text-foreground">{dt(a.signed_at)}</b></div>
            <div>{t("Yaratgan")}<br /><b className="text-foreground">{a.created_by || "—"}</b></div>
          </div>
          <div className="space-y-2">
            {(a.items ?? []).map((it) => (
              <div key={it.id} className={cn("flex gap-3 rounded-xl border p-3", it.result && !it.result.ok && "border-red-500/40 bg-red-500/5")}>
                <div className="size-14 shrink-0 overflow-hidden rounded-lg bg-muted">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {it.photos[0] && <img src={it.photos[0].thumb} alt="" className="size-full object-cover" />}
                </div>
                <div className="min-w-0 flex-1 text-sm">
                  <div className="font-semibold">{(lang === "ru" && it.type_ru) || it.type} <span className="font-mono text-xs text-primary">{it.inv_number}</span></div>
                  <div className="text-xs text-muted-foreground">{[it.brand, it.model, it.serial && `S/N ${it.serial}`, `×${it.quantity}`].filter(Boolean).join(" · ")}</div>
                  {it.result && (it.result.ok
                    ? <div className="mt-1 text-xs font-semibold text-emerald-600">✓ {t("Tasdiqlandi")}</div>
                    : <div className="mt-1 text-xs font-semibold text-red-600">✕ {t("Menda yo'q")}{it.result.comment && `: ${it.result.comment}`}</div>)}
                </div>
              </div>
            ))}
          </div>
          {a.comment && <div className="rounded-xl bg-muted/50 p-3 text-sm"><b>{t("Izoh")}:</b> {a.comment}</div>}
          {a.status === "signed" && (
            <div className="rounded-xl border p-3">
              <div className="text-xs text-muted-foreground">{t("Imzoladi")}: <b className="text-foreground">{a.signer_name}</b></div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {a.signature_url && <img src={a.signature_url} alt={t("Imzo")} className="mt-2 h-28 w-full rounded-lg border bg-white object-contain" />}
              <div className="mt-1 text-[11px] text-muted-foreground">IP {a.ip} · {a.user_agent}</div>
            </div>
          )}
        </div>
      )}
    </Overlay>
  );
}

/* ------------------------------------------------------------------ ro'yxat */
type Tab = "all" | "pending" | "signed" | "issues" | "outdated" | "none";

export function AcksView({ table }: { table?: boolean }) {
  const boot = useBoot().data!;
  const t = useT();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("all");
  const [branch, setBranch] = useState("");
  const [detail, setDetail] = useState<number | null>(null);
  const [share, setShare] = useState<Ack | null>(null);
  const [busy, setBusy] = useState(false);
  const { create, dialog } = useCreateAck();
  const stats = useQuery({ queryKey: ["inv", "stats", 30], queryFn: () => inv.stats({ days: 30 }) });
  const params = { branch, status: tab === "pending" || tab === "signed" ? tab : undefined, issues: tab === "issues" ? 1 : undefined, outdated: tab === "outdated" ? 1 : undefined };
  const list = useQuery({ queryKey: ["inv", "acks", params], queryFn: () => inv.acks(params), enabled: tab !== "none" });
  const none = useQuery({ queryKey: ["inv", "employees", "ack-none", branch], queryFn: () => inv.employees({ ack: "none", branch, limit: 5000 }), enabled: tab === "none" });
  const tt = stats.data?.totals;

  const bulk = async () => {
    if (!confirm(t("Qurilmasi bor, lekin amaldagi havolasi yo'q barcha xodimlarga havola yaratilsinmi?"))) return;
    setBusy(true);
    try {
      const r = await inv.acksBulk(branch ? Number(branch) : null);
      toast.success(t("{n} ta havola yaratildi", { n: r.created }));
      qc.invalidateQueries({ queryKey: ["inv"], predicate: (q) => q.queryKey[1] !== "boot" });
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const revoke = async (a: Ack) => {
    if (!confirm(t("Havola bekor qilinsinmi? Xodim uni ocha olmaydi."))) return;
    await inv.revokeAck(a.id).catch((e) => toast.error(errorMessage(e)));
    qc.invalidateQueries({ queryKey: ["inv", "acks"] });
  };

  const TABS: [Tab, string][] = [["all", "Hammasi"], ["pending", "Kutilmoqda"], ["signed", "Imzolangan"], ["issues", "E'tirozli"],
    ["outdated", "Eskirgan"], ["none", "Havola yuborilmagan"]];
  const rows = list.data?.results ?? [];

  return (
    <div className={cn("mx-auto w-full space-y-3 p-3 pb-28 sm:p-4", table ? "max-w-[1800px]" : "max-w-5xl")}>
      {tt && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Kpi label={t("Qurilmasi bor xodimlar")} value={tt.employees_with_devices} tone="slate" />
          <Kpi label={t("Imzolagan")} value={tt.acks_signed} tone="green" />
          <Kpi label={t("Imzo kutilmoqda")} value={tt.acks_pending} tone="amber" />
          <Kpi label={t("Havola yuborilmagan")} value={Math.max(0, tt.employees_with_devices - tt.acks_signed - tt.acks_pending)} tone="red" onClick={() => setTab("none")} />
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {boot.branches.length > 1 && (
          <div className="w-full sm:w-56"><Picker title={t("Filial")} placeholder={t("Barcha filiallar")} value={branch}
            options={boot.branches.map((b) => ({ value: String(b.id), label: b.name }))} onChange={setBranch} /></div>
        )}
        <div className="ml-auto flex flex-wrap gap-2">
          <Btn variant="outline" size="sm" onClick={() => download("acks/export/", { branch }).catch((e) => toast.error(errorMessage(e)))}><Download className="size-4" />{t("Excel (havolalar bilan)")}</Btn>
          {boot.me.can.write && <Btn size="sm" loading={busy} onClick={bulk}><Link2 className="size-4" />{t("Barchasiga havola yaratish")}</Btn>}
        </div>
      </div>
      <div className="-mx-3 flex gap-1.5 overflow-x-auto px-3 [scrollbar-width:none] sm:mx-0 sm:px-0">
        {TABS.map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)} className={cn("h-9 shrink-0 rounded-full border px-3 text-[13px] font-medium md:h-8 md:text-xs",
            tab === k ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground")}>{t(label)}</button>
        ))}
      </div>

      {tab === "none" ? (
        none.isLoading ? <Spinner /> : !none.data?.results.length ? (
          <Empty icon={<ShieldCheck className="size-6" />} title={t("Hammaga havola yuborilgan")} />
        ) : (
          <div className="space-y-2">
            {none.data.results.map((e) => (
              <div key={e.id} className="flex items-center gap-3 rounded-2xl border bg-card p-3">
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{e.full_name}</div>
                  <div className="text-xs text-muted-foreground">{[e.branch_name, e.phone, e.telegram && `@${e.telegram}`, t("{n} ta qurilma", { n: e.devices })].filter(Boolean).join(" · ")}</div>
                  {(!e.phone || !e.telegram) && <div className="text-xs text-amber-600">{t("Telefon yoki Telegram yozilmagan")}</div>}
                </div>
                {boot.me.can.write && <Btn size="sm" onClick={() => create(e)}><Send className="size-4" />{t("Havola")}</Btn>}
              </div>
            ))}
          </div>
        )
      ) : list.isLoading ? <Spinner /> : !rows.length ? (
        <Empty icon={<FileSignature className="size-6" />} title={t("Hali tasdiqnoma yo'q")}
          hint={t("Xodimlar bo'limida xodimni ochib «Tasdiqlash havolasi» ni bosing yoki «Barchasiga havola yaratish».")} />
      ) : (
        <div className="space-y-2">
          {rows.map((a) => (
            <div key={a.id} className={cn("rounded-2xl border bg-card p-3 shadow-xs", a.issues > 0 && "border-red-500/30")}>
              <div className="flex flex-wrap items-start gap-2">
                <button onClick={() => setDetail(a.id)} className="min-w-0 flex-1 text-left">
                  <div className="font-semibold">{a.employee_name}</div>
                  <div className="text-xs text-muted-foreground">{[a.branch, a.phone, a.telegram && `@${a.telegram}`, t("{n} ta qurilma", { n: a.items_count })].filter(Boolean).join(" · ")}</div>
                </button>
                <div className="flex flex-wrap items-center gap-1.5">
                  <AckBadge status={a.status} opened={!!a.opened_at} />
                  {a.outdated && <span className="rounded-full bg-orange-500/12 px-2 py-0.5 text-[11px] font-semibold text-orange-700">{t("eskirgan")}</span>}
                  {a.issues > 0 && <span className="inline-flex items-center gap-1 rounded-full bg-red-500/12 px-2 py-0.5 text-[11px] font-semibold text-red-700"><AlertTriangle className="size-3" />{t("{n} ta e'tiroz", { n: a.issues })}</span>}
                </div>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <span className="mr-auto">{a.status === "signed" ? `${t("Imzolandi")}: ${dt(a.signed_at)}` : `${t("Yuborildi")}: ${ago(a.created_at)}${a.opened_at ? ` · ${t("ochilgan")} ${ago(a.opened_at)}` : ""}`}</span>
                <Btn variant="ghost" size="sm" onClick={() => setDetail(a.id)}><ExternalLink className="size-3.5" />{t("Ko'rish")}</Btn>
                {a.status === "pending" && <Btn variant="ghost" size="sm" onClick={() => setShare(a)}><Send className="size-3.5" />{t("Yuborish")}</Btn>}
                {boot.me.can.write && (a.outdated || a.status === "signed") && <Btn variant="ghost" size="sm" onClick={() => create({ id: a.employee })}><Link2 className="size-3.5" />{t("Yangi havola")}</Btn>}
                {boot.me.can.write && a.status === "pending" && <Btn variant="ghost" size="sm" className="text-destructive" onClick={() => revoke(a)}><XCircle className="size-3.5" /></Btn>}
              </div>
            </div>
          ))}
        </div>
      )}
      <AckDetail id={detail} onClose={() => setDetail(null)} />
      <AckShare ack={share} onClose={() => setShare(null)} />
      {dialog}
      {!rows.length && tab === "all" && !list.isLoading && <Card className="text-sm text-muted-foreground"><Users className="mb-1 size-4" />{t("Xodim telefoni va Telegrami qurilma kiritilayotganda yoziladi. Shundan keyin havola yuboriladi.")}</Card>}
    </div>
  );
}
