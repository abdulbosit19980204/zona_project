/** Support bot API (/api/support/...). */
import { api } from "@/lib/api/client";

export type Mode = "off" | "collect" | "shadow" | "live";
export type EntryStatus = "new" | "review" | "approved" | "rejected" | "archived";
export type EntryKind = "template" | "faq";
export type MsgStatus = "new" | "answered" | "drafted" | "escalated" | "ignored" | "closed";
export interface MediaInfo {
  id: number; kind: "photo" | "video" | "video_note" | "animation" | "document"; name: string; mime: string; size: number;
  width: number; height: number; label: number | null; label_title: string; label_auto: boolean; ocr: string; source: string;
  created_at: string; available: boolean;
}

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
  answer: string; answer_ru: string; ask_first: string; attachments: number[]; attachments_info?: MediaInfo[];
  image_examples_count?: number; zone: number | null; zone_name: string; responsible: number | null;
  responsible_name: string; status: EntryStatus; source: string; priority: boolean; pending: PendingEdit | null;
  author: string; approved_by: string; approved_at: string | null; uses: number; likes: number; dislikes: number;
  last_used_at: string | null; created_at: string; updated_at: string;
  versions?: EntryVersion[]; messages?: { id: number; text: string; at: string; status: MsgStatus }[];
}
export interface SupportMessage {
  id: number; group: number | null; group_title: string; user_name: string; user_username: string; text: string;
  ocr_text: string; has_photo: boolean; media: MediaInfo[]; lang: string; status: MsgStatus; stage: string; entry: number | null;
  entry_title: string; confidence: number; answer_text: string; answered_by: string; feedback: number;
  created_at: string; answered_at: string | null;
  staff_answers: { by: string; text: string; at: string; kind: "staff" | "clarify" | "info"; ocr: string; media: MediaInfo[] }[];
}
export interface SupportSettings {
  api_id: string; api_hash: string; has_api_hash: boolean; ai_enabled: boolean; ai_daily_limit: number;
  ai_min_confidence: number; faq_threshold: number; route_threshold: number; learn_from_staff: boolean;
  ocr_enabled: boolean; media_days: number; signature: string; ocr_available: boolean; ocr_languages: string;
  ai_ready: boolean; ai_quota_left: number;
  drafts_to_admin: boolean; escalation_ack: boolean; mention_responsible: boolean; feedback_buttons: boolean;
  notify_candidates: boolean; learn_clarifications: boolean; ask_first_prompt: boolean;
  history_days: number; history_photos: boolean; history_max: number;
  mtproto_available: boolean; mtproto_connected: boolean; mtproto_user: string; mtproto_pending: boolean;
  mtproto_need_password: boolean; mtproto_phone: string;
  image_match: boolean; image_threshold: number; image_autolabel: boolean;
  mention_asker: boolean; mention_supervisor: boolean; workers: number; contact_lookup: boolean;
}
export interface AIJobInfo {
  id: number; kind: "entries" | "unanswered"; status: "queued" | "running" | "done" | "failed";
  progress: { done?: number; total?: number; suggestions?: number }; error: string; created_by: string; created_at: string;
  finished_at: string | null;
}
export interface AISuggestion {
  id: number; kind: "improve" | "questions" | "merge" | "new" | "archive"; status: string; reason: string;
  payload: { title?: string; answer?: string; answer_ru?: string; ask_first?: string; questions?: string[]; merge_into?: number };
  entry: number | null; entry_title: string; current: { answer: string; answer_ru: string; ask_first: string; questions: string[] } | null;
  target: number | null; target_title: string; question_ids: number[]; decided_by: string; created_at: string;
}
export interface TgUserInfo {
  id: number; name: string; username: string; is_staff: boolean; staff_name: string; staff_person: number | null;
  staff_person_name: string; staff_person_role: string; project: string; supervisor: string; link: string; questions: number;
  last_seen: string;
}
export interface StaffPersonHit { id: number; name: string; role: string; project: string; territory: string; manager: string }
export interface ImageTypes {
  labeled: { entry: number; title: string; status: EntryStatus; count: number; auto: number; samples: MediaInfo[] }[];
  unlabeled: { count: number; ids: number[]; samples: MediaInfo[]; ocr: string; guess: number | null; guess_title: string }[];
  threshold: number; total: number;
}
export interface HistoryJob {
  id: number; group: number; group_title: string; days: number; photos: boolean; status: "queued" | "running" | "done" | "failed";
  progress: { stage?: string; messages?: number; photos?: number; processed?: number; questions?: number; staff_answers?: number;
    clarifications?: number; candidates?: number; flood_wait?: number };
  error: string; created_by: string; created_at: string; started_at: string | null; finished_at: string | null;
}
export interface Analytics {
  days: number; questions: number; unanswered: number; with_photo: number; entries_with_ask_first: number;
  by_source: Record<string, number>; by_stage: Record<string, number>;
  staff: { name: string; answers: number; panel: number; clarifications: number; median_minutes: number | null; groups: string[];
    candidates: number; approved: number; rejected: number }[];
  top_asks: { text: string; count: number }[];
  daily: { date: string; total: number; bot: number; staff: number }[];
  groups: { title: string; n: number }[];
  zones: Record<string, number>;
  protarget: { questions: number; by_bot: number; unanswered: number; types: { title: string; n: number }[];
    team_answers: number; team_median_minutes: number | null };
  images: { total: number; labeled: number; types: number; by_image: number };
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
  analytics: (days = 30) => get<Analytics>("analytics/", { days }),
  historyJobs: () => get<HistoryJob[]>("history/"),
  startHistory: (group: number, days: number, photos: boolean) => post<HistoryJob[]>("history/", { group, days, photos }),
  mtSendCode: (phone: string) => post<SupportSettings & { need_password?: boolean }>("mtproto/send-code/", { phone, confirm: true }),
  mtSignIn: (code: string, password = "") => post<SupportSettings & { need_password?: boolean }>("mtproto/sign-in/", { code, password }),
  mtLogout: () => post<SupportSettings>("mtproto/logout/"),
  upload: async (files: File[], opts: { label?: number; source?: string } = {}) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    if (opts.label) fd.append("label", String(opts.label));
    if (opts.source) fd.append("source", opts.source);
    return (await api.post<MediaInfo[]>(B + "media/upload/", fd, { headers: { "Content-Type": "multipart/form-data" } })).data;
  },
  mediaBlob: async (id: number) => (await api.get<Blob>(`${B}media/${id}/file/`, { responseType: "blob" })).data,
  images: () => get<ImageTypes>("images/"),
  label: (ids: number[], entry: number | null) => post<{ done: number }>("images/label/", { ids, entry }),
  tgUsers: (unlinked = false) => get<TgUserInfo[]>("tg-users/", unlinked ? { unlinked: 1 } : {}),
  linkTgUser: (id: number, staffPerson: number | null) => post<TgUserInfo>(`tg-users/${id}/link/`, { staff_person: staffPerson }),
  staffPeople: (q: string) => get<StaffPersonHit[]>("staff-people/", { q }),
  aiJobs: () => get<AIJobInfo[]>("ai/jobs/"),
  startAIJob: (kind: "entries" | "unanswered") => post<AIJobInfo[]>("ai/jobs/", { kind }),
  aiSuggestions: (status = "pending") => get<AISuggestion[]>("ai/suggestions/", { status }),
  decideSuggestion: (id: number, action: "approve" | "reject", payload?: Record<string, unknown>) =>
    post<AISuggestion>(`ai/suggestions/${id}/${action}/`, payload ? { payload } : {}),
};
