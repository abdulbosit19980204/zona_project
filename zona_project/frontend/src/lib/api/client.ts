import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

import { useAuth } from "@/stores/auth";
import { useUI } from "@/stores/ui";

import type { TokenPair } from "./types";

/** API manzili. Standart: "/api" — Next.js rewrites orqali Django'ga yo'naltiriladi (next.config.ts). */
export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "/api").replace(/\/$/, "");

export const api = axios.create({
  baseURL: API_BASE + "/",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = useAuth.getState().access;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  // Tanlangan til: backend shu tildagi tahrirni taniydi, qidiruv va Excel shu tilda bo'ladi
  config.headers["X-Lang"] = useUI.getState().locale;
  return config;
});

/* Access token muddati tugasa: refresh bilan bitta marta yangilab, so'rovni qaytaramiz.
   Bir vaqtda kelgan 401 javoblar bitta yangilash so'rovini kutadi. */
let refreshing: Promise<string | null> | null = null;

export async function refreshAccess(): Promise<string | null> {
  const refresh = useAuth.getState().refresh;
  if (!refresh) return null;
  try {
    const { data } = await axios.post<TokenPair>(`${API_BASE}/auth/refresh/`, { refresh });
    useAuth.getState().setTokens(data);
    return data.access;
  } catch (error) {
    // Seans haqiqatan tugagan bo'lsa chiqaramiz; Zona vaqtincha ishlamasa (tarmoq/5xx) — seans saqlanadi
    const status = axios.isAxiosError(error) ? error.response?.status : undefined;
    if (status && status < 500) useAuth.getState().logout();
    return null;
  }
}

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

/** 401 bo'lsa tokenni bir marta yangilab, so'rovni qaytaradi (QR Drive klienti ham shundan foydalanadi). */
export async function retryWithRefresh(error: AxiosError, instance: typeof api) {
  const config = error.config as RetriableConfig | undefined;
  if (error.response?.status === 401 && config && !config._retry && !config.url?.startsWith("auth/")) {
    config._retry = true;
    refreshing ??= refreshAccess().finally(() => {
      refreshing = null;
    });
    const token = await refreshing;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
      return instance(config);
    }
  }
  return Promise.reject(error);
}

api.interceptors.response.use((response) => response, (error: AxiosError) => retryWithRefresh(error, api));

function flatten(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(flatten).join(" ");
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, v]) => (["detail", "non_field_errors"].includes(key) ? flatten(v) : `${key}: ${flatten(v)}`))
      .join("; ");
  }
  return String(value ?? "");
}

/** Har qanday xatoni foydalanuvchiga ko'rsatiladigan matnga aylantiradi. */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) return "Server bilan aloqa yo'q";
    const text = flatten(error.response.data);
    return text || `Xatolik (${error.response.status})`;
  }
  return error instanceof Error ? error.message : String(error);
}
