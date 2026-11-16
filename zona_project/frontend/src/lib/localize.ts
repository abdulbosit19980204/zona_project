/**
 * Ma'lumotlarni tanlangan tilda ko'rsatish.
 *
 * Xodim matnni istalgan bitta tilda yozadi; backend AI orqali uz/ru/en tarjimalarini `i18n` maydoniga yozadi.
 * Bu yerda butun holat (OrgState) bir marta tanlangan tilga almashtiriladi — barcha sahifa, xarita,
 * forma va infografika avtomatik shu tilda ko'rinadi. Tarjima hali tayyor bo'lmasa — asl matn qoladi.
 */
import type { I18n, OrgState } from "@/lib/api/types";
import type { Locale } from "@/stores/ui";

function pick<T extends { i18n?: I18n }>(obj: T, locale: Locale): T {
  const tr = obj.i18n?.[locale];
  if (!tr) return obj;
  const out: Record<string, unknown> = { ...obj };
  for (const [key, value] of Object.entries(tr)) {
    if (!value) continue;
    if (typeof out[key] === "string") out[key] = value;
    // ro'yxat maydonlari (masalan, xodim vazifalari) i18n da qatorlar bilan birlashtirilgan matn sifatida keladi
    else if (Array.isArray(out[key]) && typeof value === "string") out[key] = value.split("\n");
  }
  return out as T;
}

export function localizeState(state: OrgState, locale: Locale): OrgState {
  const all = <T extends { i18n?: I18n }>(items: T[]) => items.map((i) => pick(i, locale));
  return {
    ...state,
    departments: all(state.departments),
    teams: all(state.teams),
    members: all(state.members),
    authorities: all(state.authorities),
    zones: all(state.zones ?? []),
    systems: all(state.systems),
    processes: all(state.processes),
    tasks: state.tasks.map((t) => ({ ...pick(t, locale), fallbacks: all(t.fallbacks) })),
    edge_cases: all(state.edge_cases),
  };
}
