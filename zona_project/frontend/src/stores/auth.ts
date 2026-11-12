"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { Me, TokenPair } from "@/lib/api/types";

/** JWT tokenlar va joriy foydalanuvchi. localStorage'da saqlanadi (faqat brauzerda o'qiladi). */
interface AuthState {
  access: string | null;
  refresh: string | null;
  user: Me | null;
  setTokens: (tokens: TokenPair) => void;
  setSession: (tokens: TokenPair, user: Me) => void;
  setUser: (user: Me) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      access: null,
      refresh: null,
      user: null,
      setTokens: ({ access, refresh }) => set({ access, refresh }),
      setSession: ({ access, refresh }, user) => set({ access, refresh, user }),
      setUser: (user) => set({ user }),
      logout: () => set({ access: null, refresh: null, user: null }),
    }),
    { name: "ra-auth", storage: createJSONStorage(() => localStorage) },
  ),
);
