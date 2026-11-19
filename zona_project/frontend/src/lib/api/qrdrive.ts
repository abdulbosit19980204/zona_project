import axios, { type AxiosError } from "axios";

import { useAuth } from "@/stores/auth";

import { retryWithRefresh } from "./client";

/** QR Drive mikroservisi (alohida jarayon). Next.js /qrdrive/... ni servisga yo'naltiradi (next.config.ts). */
export const QR_BASE = "/qrdrive";

export const qrApi = axios.create({ baseURL: `${QR_BASE}/api/admin/` });

qrApi.interceptors.request.use((config) => {
  const token = useAuth.getState().access;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
qrApi.interceptors.response.use((r) => r, (error: AxiosError) => retryWithRefresh(error, qrApi));

/** Servis ishlamayaptimi (proksi 502/503/504 yoki tarmoq xatosi). */
export function isQrDown(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false;
  const s = error.response?.status;
  return !error.response || s === 502 || s === 503 || s === 504 || (s === 500 && typeof error.response.data === "string");
}

export function qrError(error: unknown): string {
  if (isQrDown(error)) return "QR Drive servisi vaqtincha ishlamayapti. Boshqa bo'limlar ishlashda davom etadi.";
  if (axios.isAxiosError(error)) {
    const d = (error.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof d === "string") return d;
  }
  return error instanceof Error ? error.message : String(error);
}

/** Avtorizatsiya bilan fayl (rasm/PDF/video) olib, brauzer URL'iga aylantirish. */
export async function blobUrl(path: string, params?: Record<string, unknown>): Promise<string> {
  const { data } = await qrApi.get<Blob>(path, { params, responseType: "blob" });
  return URL.createObjectURL(data);
}

export async function download(path: string, filename: string, params?: Record<string, unknown>) {
  const url = await blobUrl(path, params);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

// ---------------- turlar ----------------
export type FileStatus = "merged" | "awaiting" | "queued" | "processing" | "retrying" | "delivered" | "failed";
export type Visibility = "" | "public" | "private";

export interface HumanError { kind: string; title: string; hint: string }

export interface QrFile {
  id: number; status: FileStatus; status_label: string; stage: string; source: "telegram" | "web" | "api";
  original_name: string; stored_name: string; size: number | null; mime: string; caption: string;
  employee_id: number | null; employee_name: string; department: string; storage_id: number | null; storage_name: string;
  remote_path: string; url: string; link_kind: "" | "provider" | "system"; visibility: Visibility;
  kind: "file" | "folder"; items: { name: string; size: number }[]; version: number; replaced_by: number | null; expires_at: string | null; has_password: boolean;
  downloads: number; attempts: number; created_at: string; finished_at: string | null; deleted_at: string | null;
  duplicate_of: number | null; durations: Record<string, number>; error: HumanError | null;
}

export interface FileEvent { stage: string; ok: boolean; message: string; duration_ms: number | null; at: string }
export interface FileVersion { id: number; version: number; size: number | null; created_at: string; actor: string; current: boolean; original_name: string }
export interface ExtraLink { token: string; url: string; expires_at: string | null; has_password: boolean; downloads: number; created_at: string }
export interface QrFileDetail extends QrFile { versions: FileVersion[]; events: FileEvent[]; extra_links?: ExtraLink[]; options: Record<string, unknown>; external_user: string; actor: string }
export interface Paged<T> { items: T[]; total: number }

export interface TgAccount {
  id: number; telegram_id: number; username: string; first_name: string; last_name: string; display: string; lang: string;
  status: "registering" | "pending" | "active" | "blocked" | "rejected" | "detached"; employee_id: number | null; first_seen: string; last_seen: string;
  phone: string; is_premium: boolean; has_photo: boolean; reg_state: string; registered_at: string | null;
  reg: { full_name?: string; department?: string; position?: string };
  telegram: { language_code?: string | null; bio?: string | null; birthdate?: { day: number; month: number; year?: number } | null;
    personal_chat?: string | null };
}

export interface QrEmployee {
  id: number; full_name: string; department: string; position: string; phone: string; folder: string; storage_id: number | null;
  status: "active" | "blocked" | "archived"; note: string; created_at: string; accounts: TgAccount[];
  files_count: number; files_size: number; last_file_at: string | null;
}

export interface QrEmployeeDetail extends QrEmployee {
  all_accounts: TgAccount[]; recent_files: QrFile[]; by_status: Record<string, number>;
  history: { account: string; field: string; old: string; new: string; at: string }[];
}

export interface Invite {
  employee_id: number; full_name: string; department: string; code: string; link: string; expires_at: string; qr_png: string;
  bot_missing: boolean;
}

export interface FieldDef {
  key: string; label: string; help?: string; placeholder?: string; secret?: boolean;
  type?: "bool" | "select" | "textarea"; default?: unknown; options?: [string, string][]; when?: string;
}
export interface StorageKind { kind: string; label: string; links: boolean; fields: FieldDef[]; guide: string[] }

export interface DiagStep { key: string; ok: boolean | null; detail: string; ms: number | null; error?: HumanError; technical?: string }
export interface DiagResult { ok: boolean; steps: DiagStep[]; storage?: QrStorage }

export interface QrStorage {
  id: number; name: string; kind: string; kind_label: string; base_folder: string; link_mode: "provider" | "system";
  is_primary: boolean; is_fallback: boolean; enabled: boolean; status: "unknown" | "ok" | "down"; last_check_at: string | null;
  last_error: string; latency_ms: number | null; quota_used: number | null; quota_total: number | null;
  config: Record<string, unknown>; files: number; check?: { ok: boolean; title?: string; hint?: string; latency_ms?: number } | null;
}

export interface QrStyle { size: number; fg: string; bg: string; logo: boolean; caption: "filename" | "company" | "custom" | "none"; caption_text: string }

export interface QrSettings {
  setup_done: boolean; company_name: string; public_base_url: string; bot_username: string; bot_api_url: string; bot_api_local: boolean;
  max_file_mb: number; allowed_types: string; folder_template: string; filename_template: string; link_expire_days: number;
  registration_required: boolean; approval_mode: "manual" | "auto"; bot_admins: string; admin_notify: Record<string, boolean>; visibility_mode: "ask" | "public" | "private";
  multi_mode: "ask" | "folder" | "separate"; replace_mode: "ask" | "replace" | "new"; archive_mode: "ask" | "archive" | "folder"; archive_max_files: number; archive_max_mb: number; default_visibility: "public" | "private"; visibility_timeout_min: number;
  duplicate_policy: "reuse" | "upload"; auto_fallback: boolean; qr_style: QrStyle; bot_texts: Record<string, Record<string, string>>;
  default_lang: string; timezone: string; notify_chat_ids: string; notify: Record<string, boolean>; daily_report_time: string;
  saved_minutes_per_file: number; retention_days: number; trash_days: number; backup_keep_days: number;
  bot_token_set: boolean; link_password_set: boolean; logo: boolean; default_texts: Record<string, Record<string, string>>;
}

export interface Dashboard {
  kpi: { today: number; week: number; month: number; total: number; total_size: number; active_employees: number;
    success_rate: number | null; avg_ms: number | null; saved_minutes: number; queue: number };
  daily: { date: string; delivered: number; failed: number }[];
  storages: { id: number; name: string; status: string; used: number | null; total: number | null; is_primary: boolean }[];
  attention: { pending_requests: number; failed_files: number; links_expiring: number; storages_down: string[];
    quota_high: string[]; no_storage: boolean; worker_down: boolean; bot_down: boolean };
  setup_done: boolean; bot_username: string;
}

export interface ApiKeyRow {
  id: number; name: string; prefix: string; scopes: string[]; rate_limit: number; allowed_ips: string[]; storage_id: number | null;
  expires_at: string | null; webhook_url: string; webhook_secret_set: boolean; created_by: string; created_at: string;
  last_used_at: string | null; uses: number; revoked: boolean; key?: string; webhook_secret?: string;
}

export interface Notif { id: number; at: string; kind: string; level: string; title: string; body: string; link: string; read: boolean }
export interface NotifResponse { unread: number; pending_requests: number; failed_files: number; items: Notif[] }

export interface SystemStatus {
  version: string;
  services: { name: string; label: string; ok: boolean; last_seen: string | null; started_at: string | null; info: Record<string, unknown> }[];
  queue: Record<string, number>; database: { size: number }; disk: { free: number; total: number };
  telegram_api: { mode: string; bot: string };
  runtime: { port: number; host: string; data_dir: string; debug: boolean; public_base_url: string; timezone: string;
    master_key_set: boolean; sso_set: boolean };
  storages: { id: number; name: string; status: string; latency_ms: number | null; last_check_at: string | null; error: string; error_kind: string }[];
  backups: { name: string; size: number; created_at: string }[];
}

export interface AuditRow { id: number; at: string; actor: string; actor_kind: string; action: string; target: string; details: Record<string, unknown> }

export interface SetupStatus {
  done: boolean; steps: Record<"admin" | "bot" | "storage" | "employees" | "test", boolean>;
  bot_username: string; storages: number; employees: number;
}

export function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v >= 10 || i === 0 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
}
