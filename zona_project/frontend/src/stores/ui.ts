"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { RoleKey } from "@/lib/api/types";

export type Locale = "uz" | "ru" | "en";

/** Interfeys holati (brauzerda saqlanadi): menyu, til, bo'lim doirasi, xarita sozlamalari. */
interface UIState {
  sidebarCollapsed: boolean;
  locale: Locale;
  scope: number | null; // tanlangan bo'lim (company selector); null = butun kompaniya
  hiddenRoles: RoleKey[];
  onlyIssues: boolean;
  collapsedDepts: number[];
  toggleSidebar: () => void;
  setLocale: (locale: Locale) => void;
  setScope: (scope: number | null) => void;
  toggleRole: (role: RoleKey) => void;
  setOnlyIssues: (value: boolean) => void;
  toggleDept: (id: number) => void;
}

export const useUI = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      locale: "uz",
      scope: null,
      hiddenRoles: [],
      onlyIssues: false,
      collapsedDepts: [],
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setLocale: (locale) => set({ locale }),
      setScope: (scope) => set({ scope }),
      toggleRole: (role) =>
        set((s) => ({ hiddenRoles: s.hiddenRoles.includes(role) ? s.hiddenRoles.filter((r) => r !== role) : [...s.hiddenRoles, role] })),
      setOnlyIssues: (onlyIssues) => set({ onlyIssues }),
      toggleDept: (id) =>
        set((s) => ({ collapsedDepts: s.collapsedDepts.includes(id) ? s.collapsedDepts.filter((d) => d !== id) : [...s.collapsedDepts, id] })),
    }),
    { name: "ra-ui", storage: createJSONStorage(() => localStorage) },
  ),
);
