/** Support bot API (/api/support/...). */
import { api } from "@/lib/api/client";

export type Mode = "off" | "shadow" | "live";
export type EntryStatus = "new" | "review" | "approved" | "rejected" | "archived";
export type EntryKind = "template" | "faq";
export type MsgStatus = "new" | "answered" | "drafted" | "escalated" | "ignored" | "closed";

export interface SupportBot {
  id: number; name: string; username: string; enabled: boolean; mode: Mode; admin_chat_id: number | null;
  welcome: string; last_ok_at: string | null; last_error: string; token_masked: string; groups_count: number;
  created_at: string; updated_at: string; token?: string;
}
export interface SupportGroup {
  id: number; bot: number; bot_name: string; chat_id: number; title: string; mode: Mode | "inherit";
  effective_mode: Mode; is_active: boolean; is_admin: boolean; joined_at: string; last_message_at: string | null;
  questions_7d: number;
}
export interface EntryVersion {
  id: number; title: string; questions: string[]; triggers: string[]; extract: string[]; answer: string;
  answer_ru: string; editor: string; note: string; at: string;
}
export interface PendingEdit {
  title?: string; questions?: string[]; triggers?: string[]; extract?: string[]; answer?: string; answer_ru?: string;
  by?: string; at?: string;
}
export interface Entry {
  id: number; kind: EntryKind; title: string; questions: string[]; triggers: string[]; extract: string[];
  answer: string; answer_ru: string; zone: number | null; zone_name: string; responsible: number | null;
  responsible_name: string; status: EntryStatus; source: string; priority: boolean; pending: PendingEdit | null;
  author: string; approved_by: string; approved_at: string | null; uses: number; likes: number; dislikes: number;
  last_used_at: string | null; created_at: string; updated_at: string;
  versions?: EntryVersion[]; messages?: { id: number; text: string; at: string; status: MsgStatus }[];
}
export interface SupportMessage {
  id: number; group: number | null; group_title: string; user_name: string; user_username: string; text: string;
  ocr_text: string; has_photo: boolean; lang: string; status: MsgStatus; stage: string; entry: number | null;
  entry_title: string; confidence: number; answer_text: string; answered_by: string; feedback: number;
  created_at: string; answered_at: string | null; staff_answers: { by: string; text: string; at: string }[];
}
export interface SupportSettings {
  api_id: string; api_hash: string; has_api_hash: boolean; ai_enabled: boolean; ai_daily_limit: number;
  ai_min_confidence: number; faq_threshold: number; route_threshold: number; learn_from_staff: boolean;
  ocr_enabled: boolean; media_days: number; signature: string; ocr_available: boolean; ocr_languages: string;
  ai_ready: boolean; ai_quota_left: number;
}
export interface SupportStats {
  total: number; by_status: Partial<Record<MsgStatus, number>>; by_stage: Record<string, number>;
  entries: Partial<Record<EntryStatus, number>>; pending_edits: number;
  top: { id: number; title: string; uses: number; likes: number; dislikes: number }[];
  bots: { id: number; name: string; username: string; enabled: boolean; mode: Mode; last_ok_at: string | null; last_error: string; admin_chat: boolean }[];
}
export interface StaffRow {
  type: "member" | "contact"; id: number; name: string; role: string; level: string; telegram: string; phone: string;
  team: string; linked?: boolean;
}
export interface TestResult {
  stage: string; confidence: number; text: string; needs_human: boolean; entry: number | null; entry_title: string;
  unapproved: boolean; fields: Record<string, string>; responsible: { name: string; telegram: string[] }[]; note: string; lang: string;
}

const B = "support/";
const get = async <T>(url: string, params?: Record<string, string | number>) => (await api.get<T>(B + url, { params })).data;
const post = async <T>(url: string, body: unknown = {}) => (await api.post<T>(B + url, body)).data;
const patch = async <T>(url: string, body: unknown) => (await api.patch<T>(B + url, body)).data;

export const supportApi = {
  stats: (days = 7) => get<SupportStats>("stats/", { days }),
  staff: () => get<StaffRow[]>("staff/"),
  settings: () => get<SupportSettings>("settings/"),
  saveSettings: (body: Partial<SupportSettings> & { api_hash?: string }) => patch<SupportSettings>("settings/", body),
  bots: () => get<SupportBot[]>("bots/"),
  createBot: (body: Partial<SupportBot>) => post<SupportBot>("bots/", body),
  updateBot: (id: number, body: Partial<SupportBot>) => patch<SupportBot>(`bots/${id}/`, body),
  deleteBot: async (id: number) => { await api.delete(`${B}bots/${id}/`); },
  checkBot: (id: number) => post<{ ok: boolean; username?: string; error?: string; can_read_all_group_messages?: boolean }>(`bots/${id}/check/`),
  groups: () => get<SupportGroup[]>("groups/"),
  updateGroup: (id: number, body: Partial<SupportGroup>) => patch<SupportGroup>(`groups/${id}/`, body),
  entries: (params: Record<string, string | number> = {}) => get<Entry[]>("entries/", params),
  entry: (id: number) => get<Entry>(`entries/${id}/`),
  createEntry: (body: Partial<Entry> & { approve?: boolean }) => post<Entry>("entries/", body),
  updateEntry: (id: number, body: Partial<Entry>) => patch<Entry>(`entries/${id}/`, body),
  deleteEntry: async (id: number) => { await api.delete(`${B}entries/${id}/`); },
  approve: (id: number) => post<Entry>(`entries/${id}/approve/`),
  reject: (id: number) => post<Entry>(`entries/${id}/reject/`),
  archive: (id: number) => post<Entry>(`entries/${id}/archive/`),
  revert: (id: number, vid: number) => post<Entry>(`entries/${id}/revert/${vid}/`),
  merge: (id: number, target: number) => post<Entry>(`entries/${id}/merge/`, { target }),
  bulk: (ids: number[], action: "approve" | "reject" | "archive") => post<{ done: number }>("entries/bulk/", { ids, action }),
  test: (text: string, all = true) => post<TestResult>("entries/test/", { text, all }),
  messages: (params: Record<string, string | number> = {}) => get<SupportMessage[]>("messages/", params),
  answer: (id: number, text: string, save = true, approve = false) =>
    post<{ ok: boolean; entry: number | null }>(`messages/${id}/answer/`, { text, save, approve }),
  close: (id: number) => post<{ ok: boolean }>(`messages/${id}/close/`),
};
