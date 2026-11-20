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
  answer_mode?: "" | "on" | "off";
  creates_task?: boolean; task_assignee?: string; variants?: { uz: string; ru: string }[] | null;
  image_examples_count?: number; zone: number | null; zone_name: string; responsible: number | null;
  responsible_name: string; status: EntryStatus; source: string; priority: boolean; pending: PendingEdit | null;
  author: string; approved_by: string; approved_at: string | null; uses: number; likes: number; dislikes: number;
  last_used_at: string | null; created_at: string; updated_at: string;
  sources_info?: EntrySource[];
  versions?: EntryVersion[]; messages?: { id: number; text: string; at: string; status: MsgStatus }[];
}
/** Yozuv o'rganilgan savol: matni, guruhi, muallifi va barcha fayllari (albom va qo'shimcha skrinshotlar). */
export interface EntrySource {
  id: number; text: string; ocr: string; info: string[]; group: string; user: string; link: string; at: string; media: MediaInfo[];
}
export interface SupportMessage {
  id: number; group: number | null; group_title: string; user_name: string; user_username: string; text: string;
  ocr_text: string; has_photo: boolean; media: MediaInfo[]; link: string; lang: string; status: MsgStatus; stage: string; entry: number | null;
  entry_title: string; confidence: number; answer_text: string; answered_by: string; feedback: number;
  created_at: string; answered_at: string | null;
  staff_answers: { by: string; text: string; at: string; kind: "staff" | "clarify" | "info"; ocr: string; media: MediaInfo[] }[];
  task?: { id: number; status: string; assignee: string; reply: string; error: string } | null;
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
  ai_primary: boolean; ai_primary_below: number; album_window: number;
  tasks_enabled: boolean; task_bot: string; task_default_assignee: string; task_departments: number[]; task_members: number[];
  task_daily_limit: number; task_gap: number; task_attach: boolean;
  task_mode: "command" | "remind" | "account"; task_remind_group: boolean; task_remind_dm: boolean; merge_window: number;
  self_learning: boolean; auto_approve_level: "off" | "lead" | "l2" | "all"; answer_variety: boolean; progress_messages: boolean;
  answer_policy: "standard" | "kb" | "all";
}
export interface SupportTaskInfo {
  id: number; status: "queued" | "sent" | "failed" | "skipped" | "reminded"; assignee: string; title: string; text: string; link: string;
  reason: string; reply: string; error: string; attempts: number; files: number; duplicates: number; created_at: string;
  sent_at: string | null; created_by: string; post_id?: number | null; message: number | null; asker: string; group: string; entry: number | null; entry_title: string;
}
export interface TasksPayload {
  tasks: SupportTaskInfo[]; counts: Record<string, number>; sent_today: number; entries_with_task: number;
  departments: { id: number; name: string }[];
  members: { id: number; name: string; department: string; telegram: string; is_team: boolean; level: string }[];
}
export interface SpeedRow { n: number; p50: number | null; p90: number | null; max: number }
export interface Speed {
  days: number; answered: number; p50: number | null; p90: number | null; p99: number | null; max: number | null; within_5: number | null;
  within_3?: number | null;
  buckets: { label: string; n: number }[];
  by_stage: (SpeedRow & { stage: string })[]; by_kind: (SpeedRow & { kind: string })[]; by_group: (SpeedRow & { group: string })[];
  by_hour: { hour: number; n: number; p50: number | null; p90: number | null }[];
  by_day: { date: string; n: number; p50: number | null; p90: number | null }[];
  parts: Record<string, { avg: number; p90: number | null }>;
  slowest: { id: number; secs: number; stage: string; photo: boolean; group: string; text: string; timing: Record<string, number>; at: string }[];
  workers: number; cpu: number | null;
}
export interface WorkloadRow { questions: number; bot: number; bot_rate: number; median: number | null; p90: number | null; unanswered?: number }
/** Hisobot davri: oxirgi N kun (bugun ham to'liq) yoki istalgan sanalar oralig'i. Kunlar Toshkent vaqti bilan. */
export type Range = { days?: number; from?: string; to?: string };
export interface Period { from: string; to: string; days: number; tz: string }
export interface Workload extends Period {
  questions: number; answered_by_human: number; answered_any: number; first_median: number | null; first_p90: number | null;
  within_15: number | null; within_60s: number | null; human_median: number | null; human_p90: number | null; human_needed: number;
  staff_median: number | null; heatmap: number[][]; by_weekday: number[]; busiest_dates: { date: string; n: number }[];
  buckets: { label: string; n: number }[];
  weeks: { week: string; questions: number; bot: number; human: number; unanswered: number; median: number | null }[];
  groups: (WorkloadRow & { group: string })[]; types: (WorkloadRow & { type: string })[];
  staff: { name: string; answers: number; clarifications: number; active_days: number; per_day: number; per_week: number;
    active_hours_avg: number; first_answers: number; first_median: number | null; first_p90: number | null; within_15: number | null;
    hours: number[]; weekdays: number[]; weeks: number[]; peak_hour: number | null }[];
  week_keys: string[]; tasks: Record<string, number>;
}
export interface DupRow {
  id: number; title: string; answer: string; status: EntryStatus; uses: number; likes: number; dislikes: number; author: string;
  quality: number; question_sim: number; answer_sim: number; questions: number; reasons: string[]; best: boolean;
}
export interface DupGroup { keep: number; similarity: number; entries: DupRow[] }
export interface Duplicates { threshold: number; groups: DupGroup[]; total: number; entries: number }
export interface DedupeDecision { same: boolean; keep: number | null; merge: number[]; title: string; answer: string; answer_ru: string; reason: string }
export interface AIJobInfo {
  id: number; kind: "entries" | "unanswered" | "dedupe" | "variants"; status: "queued" | "running" | "done" | "failed";
  progress: { done?: number; total?: number; suggestions?: number; applied?: number }; error: string; created_by: string; created_at: string;
  finished_at: string | null;
}
export interface AISuggestion {
  id: number; kind: "improve" | "questions" | "merge" | "new" | "archive" | "dedupe"; status: string; reason: string;
  payload: { title?: string; answer?: string; answer_ru?: string; ask_first?: string; questions?: string[]; merge_into?: number;
    keep?: number; merge?: number[] };
  group?: { id: number; title: string; answer: string; status: EntryStatus }[];
  entry: number | null; entry_title: string; current: { answer: string; answer_ru: string; ask_first: string; questions: string[] } | null;
  target: number | null; target_title: string; target_answer?: string; question_ids: number[]; decided_by: string; created_at: string;
}
export interface TgUserInfo {
  id: number; name: string; username: string; is_staff: boolean; staff_name: string; staff_person: number | null;
  staff_person_name: string; staff_person_role: string; project: string; supervisor: string; link: string; questions: number;
  last_seen: string; msg_count?: number;
}
export interface StaffPersonHit { id: number; name: string; role: string; project: string; territory: string; manager: string }
export interface ImageTypes {
  labeled: { entry: number; title: string; status: EntryStatus; count: number; auto: number; samples: MediaInfo[] }[];
  unlabeled: { count: number; ids: number[]; samples: MediaInfo[]; ocr: string; guess: number | null; guess_title: string }[];
  ignored: { count: number; ids: number[]; samples: MediaInfo[] }[];
  threshold: number; total: number;
}
export interface HistoryJob {
  id: number; group: number; group_title: string; days: number; photos: boolean; status: "queued" | "running" | "done" | "failed";
  progress: { stage?: string; messages?: number; photos?: number; processed?: number; questions?: number; staff_answers?: number;
    clarifications?: number; candidates?: number; flood_wait?: number };
  error: string; created_by: string; created_at: string; started_at: string | null; finished_at: string | null;
}
export interface Analytics extends Period {
  days: number; questions: number; unanswered: number; with_photo: number; entries_with_ask_first: number;
  by_source: Record<string, number>; by_stage: Record<string, number>;
  staff: { name: string; answers: number; panel: number; clarifications: number; median_s: number | null; groups: string[];
    candidates: number; approved: number; rejected: number; questions: number; share: number; avg_s: number | null;
    active_days: number; per_day: number; messages: number; last: string | null; topics: { title: string; n: number }[] }[];
  top_asks: { text: string; count: number }[];
  daily: { date: string; total: number; bot: number; staff: number }[];
  groups: { title: string; n: number }[];
  zones: Record<string, number>;
  protarget: { questions: number; by_bot: number; unanswered: number; types: { title: string; n: number }[];
    team_answers: number; team_median_s: number | null };
  images: { total: number; labeled: number; types: number; by_image: number };
  askers: { user: number; name: string; username: string; staff_person: string; questions: number; bot: number; escalated: number;
    groups: string[]; last: string; top_types: { title: string; n: number }[] }[];
  top_types: { entry: number; title: string; n: number }[];
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
  bulk: (ids: number[], action: "approve" | "reject" | "archive" | "review" | "kind_template" | "kind_faq" | "mode_auto" | "mode_on" | "mode_off") => post<{ done: number }>("entries/bulk/", { ids, action }),
  test: (text: string, all = true) => post<TestResult>("entries/test/", { text, all }),
  messages: (params: Record<string, string | number> = {}) => get<SupportMessage[]>("messages/", params),
  answer: (id: number, text: string, save = true, approve = false) =>
    post<{ ok: boolean; entry: number | null }>(`messages/${id}/answer/`, { text, save, approve }),
  close: (id: number) => post<{ ok: boolean }>(`messages/${id}/close/`),
  analytics: (r: Range = { days: 30 }) => get<Analytics>("analytics/", r),
  workload: (r: Range = { days: 30 }) => get<Workload>("analytics/workload/", r),
  speed: (r: Range = { days: 7 }) => get<Speed>("analytics/speed/", r),
  tasks: (status = "all") => get<TasksPayload>("tasks/", { status }),
  taskAction: (id: number, action: "retry" | "skip", assignee?: string) => post<SupportTaskInfo>(`tasks/${id}/${action}/`, assignee ? { assignee } : {}),
  taskTest: (assignee: string) => post<SupportTaskInfo>("tasks/test/", { assignee }),
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
  ignoreImages: (ids: number[], ignored = true) => post<{ done: number }>("images/ignore/", { ids, ignored }),
  duplicates: (threshold: number) => get<Duplicates>("entries/duplicates/", { threshold }),
  dedupeMerge: (body: { keep: number; merge: number[]; answer?: string; answer_ru?: string; title?: string }) =>
    post<{ entry: Entry; merged: number }>("entries/dedupe-merge/", body),
  dedupeAuto: (threshold: number, dryRun = false) => post<{ groups: number; merged: number }>("entries/dedupe-auto/", { threshold, dry_run: dryRun }),
  dedupeCompose: (ids: number[]) => post<DedupeDecision>("entries/dedupe-compose/", { ids }),
  tgUsers: (unlinked = false) => get<TgUserInfo[]>("tg-users/", unlinked ? { unlinked: 1 } : {}),
  linkTgUser: (id: number, staffPerson: number | null) => post<TgUserInfo>(`tg-users/${id}/link/`, { staff_person: staffPerson }),
  staffPeople: (q: string) => get<StaffPersonHit[]>("staff-people/", { q }),
  aiJobs: () => get<AIJobInfo[]>("ai/jobs/"),
  startAIJob: (kind: "entries" | "unanswered" | "dedupe" | "variants", params: Record<string, unknown> = {}) => post<AIJobInfo[]>("ai/jobs/", { kind, ...params }),
  aiSuggestions: (status = "pending") => get<AISuggestion[]>("ai/suggestions/", { status }),
  decideSuggestion: (id: number, action: "approve" | "reject", payload?: Record<string, unknown>) =>
    post<AISuggestion>(`ai/suggestions/${id}/${action}/`, payload ? { payload } : {}),
};
