"use client";

import { Copy, MessageCircle, MessageSquareText, Phone, Send } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import type { StaffPerson, StaffProject, StaffRole, StaffState } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const STAFF_KEY = ["staff"] as const;

export const ROLE_TONE: Record<StaffRole, string> = {
  ROP: "bg-foreground text-background",
  ASM: "bg-foreground text-background",
  RSM: "bg-primary/15 text-primary",
  SVR: "bg-success/15 text-success",
  KAM: "bg-violet/15 text-violet",
  TP: "bg-muted text-muted-foreground",
  MER: "bg-warning/15 text-warning",
  OTHER: "bg-muted text-muted-foreground",
};

/** Qidiruv uchun: kichik harf, apostroflarsiz, kirill → lotin (Ташкент = tashkent), telefon raqamlari bo'shliqsiz. */
const CYR: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "yo", ж: "j", з: "z", и: "i", й: "y", к: "k", л: "l", м: "m", н: "n",
  о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "x", ц: "ts", ч: "ch", ш: "sh", щ: "sh", ъ: "", ы: "i", ь: "",
  э: "e", ю: "yu", я: "ya", қ: "q", ғ: "g", ҳ: "h", ў: "o",
};
export function fold(text: string) {
  return text.toLowerCase().replace(/[ʻʼ’‘`´']/g, "").replace(/[а-яёқғҳў]/g, (c) => CYR[c] ?? c).replace(/h/g, "x").replace(/\s+/g, " ").trim();
}
/** Rol nomlari ham qidiriladi: "supervayzer" -> SVR, "agent" -> TP. */
const ROLE_WORDS: Record<StaffRole, string> = {
  ROP: "rop rahbar руководитель head", ASM: "asm menejer manager", RSM: "rsm menejer manager",
  SVR: "supervayzer supervisor супервайзер", KAM: "kam key account", TP: "agent savdo vakili торговый представитель sales",
  MER: "merchendayzer мерчендайзер merchandiser", OTHER: "",
};
const haystack = (p: StaffPerson, project?: StaffProject, unit?: string, manager?: StaffPerson) =>
  fold([p.name, p.is_vacancy ? "vakansiya vacancy" : "", p.role, ROLE_WORDS[p.role], p.position, p.territory, p.region, p.city, p.phone, p.email, p.note,
    project?.name, unit, manager?.name].join(" "))
  + " " + p.phone.replace(/\D/g, "");

export const searchTerms = (q: string) => fold(q).split(" ").filter(Boolean);

export interface Index {
  person: Map<number, StaffPerson>;
  children: Map<number, StaffPerson[]>;
  byProject: Map<number, StaffPerson[]>;
  project: Map<number, StaffProject>;
  unit: Map<number, string>;
  text: Map<number, string>;
}

export function buildIndex(data?: StaffState): Index {
  const idx: Index = { person: new Map(), children: new Map(), byProject: new Map(), project: new Map(), unit: new Map(), text: new Map() };
  if (!data) return idx;
  for (const pr of data.projects) {
    idx.project.set(pr.id, pr);
    for (const u of pr.units) idx.unit.set(u.id, u.title);
  }
  const people = [...data.people].sort((a, b) => a.order - b.order);
  for (const p of people) {
    idx.person.set(p.id, p);
    idx.byProject.set(p.project, [...(idx.byProject.get(p.project) ?? []), p]);
    if (p.manager) idx.children.set(p.manager, [...(idx.children.get(p.manager) ?? []), p]);
  }
  for (const p of people) {
    idx.text.set(p.id, haystack(p, idx.project.get(p.project), p.unit ? idx.unit.get(p.unit) : undefined, p.manager ? idx.person.get(p.manager) : undefined));
  }
  return idx;
}

export const matchesTerms = (index: Index, p: StaffPerson, terms: string[]) => terms.every((term) => index.text.get(p.id)?.includes(term));

export function RoleChip({ role, vacancy, className }: { role: StaffRole; vacancy?: boolean; className?: string }) {
  const t = useTranslations("staff.roles");
  return (
    <span
      title={t(role)}
      className={cn("inline-flex min-w-11 justify-center rounded-full px-2 py-0.5 font-mono text-[11px] font-semibold",
        vacancy ? "bg-destructive/12 text-destructive" : ROLE_TONE[role], className)}
    >
      {role}
    </span>
  );
}

/** Rahbar nomi (vakansiya bo'lsa — hudud kodi bilan). */
export function personLabel(p: StaffPerson, vacancy: string) {
  return p.is_vacancy ? `${vacancy} · ${p.territory}` : p.name;
}

/* ------------------------------------------------------------------ aloqa */
/** Telefon raqami -> xalqaro raqamlar (998901234567); tanilmasa — bo'sh. */
export function phoneDigits(phone: string) {
  let d = (phone || "").replace(/\D/g, "");
  if (d.length === 9) d = `998${d}`;
  return d.length >= 11 ? d : "";
}

/** Telegram havolasi: @username bo'lsa — unga, bo'lmasa telefon raqami orqali (t.me/+998...). */
export function telegramUrl(p: { phone: string; telegram?: string }) {
  const user = (p.telegram || "").replace(/^@/, "");
  if (user) return `https://t.me/${user}`;
  const d = phoneDigits(p.phone);
  return d ? `https://t.me/+${d}` : "";
}

export function contactLinks(p: { phone: string; telegram?: string }) {
  const d = phoneDigits(p.phone);
  return {
    tel: d ? `tel:+${d}` : p.phone ? `tel:${p.phone.replace(/[^\d+]/g, "")}` : "",
    telegram: telegramUrl(p),
    whatsapp: d ? `https://wa.me/${d}` : "",
    sms: d ? `sms:+${d}` : "",
  };
}

/**
 * Bir bosishda bog'lanish: qo'ng'iroq, Telegram, WhatsApp, SMS, raqamdan nusxa.
 * compact — faqat ikonkalar (ro'yxat qatorlari uchun).
 */
export function StaffContacts({ person, compact, className }: { person: { phone: string; telegram?: string }; compact?: boolean; className?: string }) {
  const t = useTranslations("staff.contact");
  const links = contactLinks(person);
  if (!links.tel && !links.telegram) return null;
  const items = [
    links.tel && { key: "tel", href: links.tel, icon: Phone, label: t("call"), tone: "hover:text-primary hover:border-primary/50" },
    links.telegram && { key: "tg", href: links.telegram, icon: Send, label: t("telegram"), tone: "text-[#229ED9] hover:border-[#229ED9]/60" },
    links.whatsapp && { key: "wa", href: links.whatsapp, icon: MessageCircle, label: t("whatsapp"), tone: "text-[#25D366] hover:border-[#25D366]/60" },
    links.sms && !compact && { key: "sms", href: links.sms, icon: MessageSquareText, label: t("sms"), tone: "hover:text-primary hover:border-primary/50" },
  ].filter(Boolean) as { key: string; href: string; icon: typeof Phone; label: string; tone: string }[];
  const copy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(person.phone);
      toast.success(t("copied"));
    } catch {
      toast.error(person.phone);
    }
  };
  const external = (href: string) => href.startsWith("http");
  if (compact) {
    return (
      <span className={cn("inline-flex items-center gap-0.5", className)} onClick={(e) => e.stopPropagation()}>
        {items.map(({ key, href, icon: Icon, label, tone }) => (
          <a
            key={key} href={href} title={label} aria-label={label}
            target={external(href) ? "_blank" : undefined} rel={external(href) ? "noopener noreferrer" : undefined}
            className={cn("grid size-7 place-items-center rounded-md border border-transparent text-muted-foreground hover:bg-muted", tone)}
          >
            <Icon className="size-3.5" />
          </a>
        ))}
      </span>
    );
  }
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {items.map(({ key, href, icon: Icon, label, tone }) => (
        <a
          key={key} href={href}
          target={external(href) ? "_blank" : undefined} rel={external(href) ? "noopener noreferrer" : undefined}
          className={cn("inline-flex h-8 items-center gap-1.5 rounded-lg border bg-card px-2.5 text-xs font-medium transition-colors", tone)}
        >
          <Icon className="size-3.5" />{label}
        </a>
      ))}
      {person.phone && (
        <button type="button" onClick={copy} title={t("copy")} className="inline-flex h-8 items-center gap-1.5 rounded-lg border bg-card px-2.5 font-mono text-xs hover:border-primary/50">
          <Copy className="size-3.5" />{person.phone}
        </button>
      )}
    </div>
  );
}

/** Necha vaqtdan beri shu o'rinda: "1 yil 3 oy" / "5 oy" / "12 kun". */
export function tenure(since: string | null | undefined, t: (k: string, v: Record<string, number>) => string) {
  if (!since) return "";
  const start = new Date(since);
  const now = new Date();
  const months = (now.getFullYear() - start.getFullYear()) * 12 + now.getMonth() - start.getMonth() - (now.getDate() < start.getDate() ? 1 : 0);
  if (months < 1) return t("days", { count: Math.max(0, Math.floor((now.getTime() - start.getTime()) / 864e5)) });
  const y = Math.floor(months / 12);
  const m = months % 12;
  return [y && t("years", { count: y }), m && t("months", { count: m })].filter(Boolean).join(" ");
}

/** "Ism Familiya +998 90 123 45 67 @user" -> alohida maydonlar (bitta qatorga joylashtirilsa). */
export function splitContact(text: string) {
  let rest = ` ${text} `;
  let telegram = "";
  let phone = "";
  const tg = rest.match(/(?:https?:\/\/)?t\.me\/([A-Za-z0-9_]{3,})|@([A-Za-z0-9_]{3,})/);
  if (tg) {
    telegram = tg[1] || tg[2];
    rest = rest.replace(tg[0], " ");
  }
  const ph = rest.match(/\+?\d[\d\s()-]{7,}\d/);
  if (ph) {
    phone = ph[0].trim();
    rest = rest.replace(ph[0], " ");
  }
  return { name: rest.replace(/[,;|]+/g, " ").replace(/\s+/g, " ").trim(), phone, telegram };
}
