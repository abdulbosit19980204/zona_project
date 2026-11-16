"use client";

import { useTranslations } from "next-intl";

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
const haystack = (p: StaffPerson, project?: StaffProject, unit?: string, manager?: StaffPerson) =>
  fold([p.name, p.is_vacancy ? "vakansiya vacancy" : "", p.role, p.position, p.territory, p.region, p.city, p.phone, p.email, p.note,
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
