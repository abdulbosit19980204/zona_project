"use client";

import { useCallback } from "react";

import { useUI } from "@/stores/ui";

import { RU } from "./i18n-ru";

/**
 * Inventarizatsiya moduli tillari: o'zbek (asosiy) va rus. Til — platformaning umumiy til sozlamasi (useUI.locale):
 * "ru" bo'lsa rus, qolgan hollarda o'zbek. Kalit — o'zbekcha matnning o'zi: t("Qurilma qo'shish").
 * Ruscha tarjimalar i18n-ru.ts da; yangi matn qo'shilsa, `node scripts/inv-i18n-check.mjs` yo'qlarini ko'rsatadi.
 */
export type Lang = "uz" | "ru";
export type Vars = Record<string, string | number>;
export type T = (text: string, vars?: Vars) => string;

export function currentLang(): Lang {
  return useUI.getState().locale === "ru" ? "ru" : "uz";
}

export function useLang(): Lang {
  return useUI((s) => (s.locale === "ru" ? "ru" : "uz"));
}

export function tr(text: string, vars?: Vars, lang: Lang = currentLang()): string {
  let s = lang === "ru" ? (RU[text] ?? text) : text;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

export function useT(): T {
  const lang = useLang();
  return useCallback((text: string, vars?: Vars) => tr(text, vars, lang), [lang]);
}

/* ------------------------------------------------------------------ server qiymatlari (kod bo'yicha) */
const COND: Record<string, [string, string]> = {
  ok: ["Ishlayapti", "Работает"], repair: ["Ta'mirga muhtoj", "Требует ремонта"], broken: ["Ishlamaydi", "Не работает"],
  spare: ["Ishlatilmayapti (zaxirada)", "Не используется (в запасе)"], missing: ["Topilmadi", "Не найдено"],
};
const STATUS: Record<string, [string, string]> = {
  planned: ["Rejada", "Запланировано"], active: ["Jarayonda", "В процессе"], done: ["Yakunlandi", "Завершено"],
};
const LEVEL: Record<string, [string, string]> = {
  manager: ["Boshqaruvchi (IT)", "Администратор (ИТ)"], director: ["Rahbar (faqat ko'rish)", "Руководитель (только просмотр)"],
  collector: ["Filial xodimi", "Сотрудник филиала"],
};
const pick = (m: Record<string, [string, string]>, v: string, lang: Lang) => m[v]?.[lang === "ru" ? 1 : 0] ?? v;
export const condLabel = (v: string, lang: Lang = currentLang()) => pick(COND, v, lang);
export const statusLabel = (v: string, lang: Lang = currentLang()) => pick(STATUS, v, lang);
export const levelLabel = (v: string, lang: Lang = currentLang()) => pick(LEVEL, v, lang);

/** Katalog yozuvining shu tildagi maydoni: ruscha bo'sh bo'lsa — o'zbekchasi. */
export function loc<O extends object>(obj: O | null | undefined, field: string, lang: Lang = currentLang()): string {
  if (!obj) return "";
  const rec = obj as Record<string, unknown>;
  const ru = lang === "ru" ? rec[`${field}_ru`] : "";
  return String(ru || rec[field] || "");
}
