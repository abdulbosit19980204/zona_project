/** Backend (Django REST) javoblari. Maydonlar backend/zona/serializers.py bilan bir xil. */

export type RoleKey = "owner" | "executor" | "approver" | "supervisor" | "contributor" | "backup";
export type ProcessRoleKey = Exclude<RoleKey, "executor">;
export type AppRole = "admin" | "editor" | "viewer" | "inventory";

/** AI tarjimalari: {"ru": {"title": "..."}, "en": {...}}. Faqat asl matnga mos (yaroqli) tarjimalar keladi. */
export type I18n = Partial<Record<"uz" | "ru" | "en", Record<string, string>>>;

export interface Department {
  id: number;
  name: string;
  description: string;
  order: number;
  i18n?: I18n;
}

export interface Team {
  id: number;
  department: number;
  name: string;
  description: string;
  lead: number | null;
  order: number;
  i18n?: I18n;
}

export interface Member {
  id: number;
  name: string;
  role: string;
  department: number | null;
  team: number | null;
  manager: number | null;
  is_team: boolean;
  trigger: string;
  does: string;
  excludes: string;
  /** Daraja: L1 birinchi yordam, L2, L3, LEAD nazorat, BIZ biznes, EXT tashqi hamkor. */
  level: MemberLevel | "";
  /** Qaysi holatlarda javob beradi — aniq vazifalar. */
  duties: string[];
  /** Hal qila olmasa — kimga o'tkazadi. */
  escalation: string;
  /** Haftalik sig'im, soat (jamoa uchun — jami). */
  capacity: number;
  email: string;
  phone: string;
  telegram: string;
  location: string;
  order: number;
  i18n?: I18n;
  /** Jamoa a'zolari (faqat is_team): aloqa uchun, hisobotlarda jamoa bo'linmaydi. */
  contacts?: TeamContact[];
}

export interface TeamContact {
  id: number;
  member: number;
  name: string;
  role: string;
  phone: string;
  telegram: string;
  telegram_id: number | null;
  note: string;
  order: number;
}

export type MemberLevel = "L1" | "L2" | "L3" | "LEAD" | "BIZ" | "EXT";

export interface Authority {
  id: number;
  member: number;
  title: string;
  scope: string;
  order: number;
  i18n?: I18n;
}

export interface SystemItem {
  id: number;
  name: string;
  order: number;
  i18n?: I18n;
}

export type ZoneIcon = "truck" | "smartphone" | "database" | "plug" | "chart" | "server" | "shield" | "users" | "box";

/** Mas'uliyat zonasi: savollar va jarayonlar guruhi (Distributsiya, ProTarget, 1C...). */
export interface Zone {
  id: number;
  key: string;
  name: string;
  description: string;
  icon: ZoneIcon;
  color: string;
  order: number;
  i18n?: I18n;
}

export interface Process {
  id: number;
  name: string;
  zone: number | null;
  system: number | null;
  description: string;
  order: number;
  i18n?: I18n;
}

export interface ProcessRole {
  id: number;
  process: number;
  member: number;
  role: ProcessRoleKey;
}

/** Navbatdagi mas'ul: asosiy mas'ul qila olmasa, savol unga o'tadi (tartib bilan: 2-, 3-...). */
export interface TaskFallback {
  member: number;
  condition: string;
  i18n?: I18n;
}

export interface Task {
  id: number;
  title: string;
  process: number | null;
  owner: number | null;
  fallbacks: TaskFallback[];
  note: string;
  /** Aniq qoida: savol kelganda kim nima qiladi, qachon keyingisiga o'tadi. */
  rule: string;
  /** Savol qanday so'raladi — AI va bot uchun misollar. */
  examples: string[];
  /** Kim so'raydi: Agent, Supervayzer, Operator... */
  asker: string;
  /** Doimiy tushadigan savol. */
  frequent: boolean;
  /** Bir marta bajarish vaqti, daqiqa. */
  minutes: number;
  /** Haftasiga necha marta tushadi. */
  per_week: number;
  /** Vaqt manbasi: avto taxmin, qo'lda yoki AI. */
  time_source: "" | "auto" | "manual" | "ai";
  is_custom: boolean;
  order: number;
  i18n?: I18n;
}

export interface EdgeCase {
  id: number;
  situation: string;
  first_owner: number | null;
  then_text: string;
  order: number;
  i18n?: I18n;
}

export interface Permissions {
  edit: boolean;
  admin: boolean;
}

export interface Me {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  role: AppRole;
  member: number | null;
  position: string;
  phone: string;
  telegram: string;
  address: string;
  note: string;
  last_login: string | null;
  date_joined: string;
  can: Permissions;
  inventory?: "manager" | "director" | "collector" | null; // IT inventarizatsiya moduliga kirish darajasi
  anonymous?: false;
}

export interface AnonymousMe {
  role: AppRole;
  can: Permissions;
  anonymous: true;
}

export interface Meta {
  company: string;
  title: string;
  ai: { route: boolean; person: boolean; audit: boolean; translate: boolean; workload: boolean; support?: boolean };
  pending_approvals: number;
}

export interface OrgState {
  meta: Meta;
  me: Me | AnonymousMe;
  departments: Department[];
  teams: Team[];
  members: Member[];
  authorities: Authority[];
  zones: Zone[];
  systems: SystemItem[];
  processes: Process[];
  roles: ProcessRole[];
  tasks: Task[];
  edge_cases: EdgeCase[];
}

export type EventKind = "created" | "moved" | "edited" | "deleted" | "member" | "role" | "approval";

export interface AuditEvent {
  id: number;
  kind: EventKind;
  subject: string;
  from_name: string;
  to_name: string;
  text: string;
  actor: string;
  at: string;
}

export type ChangeKind = "task_owner" | "role_add" | "role_remove";
export type ChangeStatus = "pending" | "approved" | "rejected" | "cancelled";

export type ChangePayload =
  | { task: number; owner: number | null }
  | { process: number; member: number; role: ProcessRoleKey }
  | { role_id: number };

export type ChangeSource = "user" | "rule" | "ai";

export interface ProposalItem {
  task: number;
  owner: number | null;
  reason?: string;
  hours?: number;
}

export interface ChangeRequest {
  id: number;
  kind: ChangeKind;
  payload: ChangePayload;
  title: string;
  reason: string;
  /** Kim taklif qildi: xodim, qoida bo'yicha tavsiya yoki AI. */
  source: ChangeSource;
  /** Taklif qabul qilinsa bo'shaydigan vaqt (soat/hafta). */
  hours: number | null;
  status: ChangeStatus;
  requested_by: number | null;
  requested_by_name: string;
  decided_by: number | null;
  decided_by_name: string;
  decision_note: string;
  created_at: string;
  decided_at: string | null;
}

export type Span = [number, number];

export interface SearchHit {
  id: number;
  score: number;
  hl?: Span[];
}

export interface SearchPerson {
  member: number;
  score: number;
  confidence: number;
  tasks: number[];
  via: string[];
}

export interface SearchResult {
  query: string;
  terms: string[];
  expanded: string[];
  people: SearchPerson[];
  tasks: SearchHit[];
  processes: SearchHit[];
  members: SearchHit[];
  edge_cases: SearchHit[];
  departments: SearchHit[];
}

export interface AIMeta {
  provider: string;
  kind: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  fallback: boolean;
}

export interface AICandidate {
  member: number;
  confidence: number;
  role: string;
  reason: string;
}

export interface AIRouteResult {
  source: "ai" | "search";
  search: SearchResult;
  ai_error?: string;
  ai_unavailable?: boolean;
  language?: string;
  summary?: string;
  answer?: string;
  needs_clarification?: boolean;
  clarifying_question?: string;
  candidates?: AICandidate[];
  task_ids?: number[];
  process_ids?: number[];
  meta?: AIMeta;
}

export interface AIText {
  text: string;
  meta: AIMeta;
}

export interface AIProvider {
  id: number;
  name: string;
  kind: string;
  base_url: string;
  api_version: string;
  is_active: boolean;
  api_key_masked: string;
  has_key: boolean;
  models_cache: string[];
  last_check_at: string | null;
  last_check_ok: boolean | null;
  last_error: string;
  updated_at: string;
}

export interface AIProviderKind {
  kind: string;
  label: string;
  base_url?: string;
  key?: boolean;
  models?: string[];
  docs?: string;
  hint?: string;
  effort?: boolean;
}

export type AITaskKey = "route" | "person" | "audit" | "translate" | "workload" | "support";
export type Effort = "" | "low" | "medium" | "high" | "xhigh" | "max";

export interface AITaskConfig {
  task: AITaskKey;
  label: string;
  enabled: boolean;
  provider: number | null;
  model: string;
  effort: Effort;
  temperature: number | null;
  max_tokens: number;
  fallback_provider: number | null;
  fallback_model: string;
  /** Asosiy va zaxira band bo'lsa navbat bilan sinab ko'riladigan modellar. */
  extra_fallbacks?: { provider: number; model: string }[];
  instructions: string;
  updated_at: string;
}

export interface AIUsage {
  id: number;
  task: string;
  provider: string;
  model: string;
  ok: boolean;
  error: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  user: string;
  prompt: string;
  at: string;
}

export interface AIUsageSummary {
  since: string;
  days?: number;
  models: { provider: string; model: string; calls: number; errors: number; input_tokens: number; output_tokens: number; latency?: number | null }[];
  tasks: { task: string; calls: number; tokens: number; errors?: number }[];
  daily?: { date: string; calls: number; errors: number; tokens: number }[];
  error_kinds?: Partial<Record<"limit" | "busy" | "key" | "other", number>>;
  busy_now?: { provider: string; model: string; n: number }[];
  today?: { calls: number; errors: number; tokens: number | null };
  totals?: { calls: number; errors: number; input_tokens: number | null; output_tokens: number | null; latency: number | null };
  support_limit?: { limit: number; left: number; enabled: boolean } | null;
}

export type AITestResult =
  | { ok: true; result: { answer?: string; text?: string }; meta: AIMeta }
  | { ok: false; error: string };

export interface Synonym {
  id: number;
  words: string;
}

export interface AdminUserInput {
  username: string;
  password?: string;
  first_name: string;
  last_name: string;
  email: string;
  role: AppRole;
  member: number | null;
  position: string;
  phone: string;
  telegram: string;
  address: string;
  note: string;
  is_active: boolean;
}

export interface TokenPair {
  access: string;
  refresh: string;
}

export interface LoginResponse extends TokenPair {
  user: Me;
}

/** WebSocket xabarlari (backend/zona/realtime.py) */
export type RealtimeMessage =
  | { type: "hello"; data: { user: string } }
  | { type: "pong" }
  | { type: "event"; data: AuditEvent }
  | { type: "approval"; data: { id: number; status: ChangeStatus; title: string } }
  | { type: "state"; data: { translated: number } };

/** Fonda AI tarjima holati (Sozlamalar → AI). */
export interface TranslateStatus {
  enabled: boolean;
  running: boolean;
  pending: number;
  last_error: string;
  last_run: string | null;
  translated: number;
  /** Tarjima xotirasidan darhol to'ldirilgan maydonlar (POST javobida). */
  filled?: number;
}

/* ---------------------------------------------------------------- dala jamoalari (brendlar) */
export type StaffRole = "ROP" | "ASM" | "RSM" | "SVR" | "KAM" | "TP" | "MER" | "OTHER";

export interface StaffUnit {
  id: number;
  key: string;
  title: string;
  order: number;
}

export interface StaffProject {
  id: number;
  name: string;
  description: string;
  source_url: string;
  synced_at: string | null;
  order: number;
  units: StaffUnit[];
}

export interface StaffPerson {
  id: number;
  project: number;
  unit: number | null;
  manager: number | null;
  name: string;
  role: StaffRole;
  position: string;
  territory: string;
  region: string;
  city: string;
  phone: string;
  email: string;
  /** @username (bo'sh bo'lsa — telefon raqami orqali). */
  telegram: string;
  /** Shu o'rinda ishlay boshlagan sana (YYYY-MM-DD). */
  since: string | null;
  note: string;
  is_vacancy: boolean;
  /** Bu o'rinda avval ishlaganlar (yangisi birinchi). */
  history: StaffHolder[];
  order: number;
}

export interface StaffHolder {
  name: string;
  phone: string;
  telegram: string;
  since: string;
  until: string;
  reason: string;
}

export interface StaffAssignBody {
  name: string;
  phone?: string;
  telegram?: string;
  email?: string;
  since?: string | null;
  reason?: string;
}

export interface StaffState {
  projects: StaffProject[];
  people: StaffPerson[];
}

export interface StaffDiffItem {
  name: string;
  territory: string;
  role: StaffRole;
  vacancy: boolean;
}

export interface StaffChange {
  field: string;
  from: string;
  to: string;
}

/** Import qilinsa nima o'zgaradi (preview). */
export interface StaffDiff {
  project: { id: number | null; name: string; exists: boolean; source_url: string };
  summary: { total: number; added: number; removed: number; replaced: number; changed: number; same: number; vacancies: number; units: number };
  added: StaffDiffItem[];
  removed: StaffDiffItem[];
  replaced: { territory: string; role: StaffRole; from: string; to: string; changes: StaffChange[] }[];
  changed: (StaffDiffItem & { changes: StaffChange[] })[];
}

export interface StaffImportBody {
  url?: string;
  text?: string;
  file_b64?: string;
  filename?: string;
  name?: string;
  project?: number | null;
  apply?: boolean;
}

/** Bot javobi (POST /api/bot/ask/). */
export interface KnowledgeContact {
  id: number;
  name: string;
  role: string;
  phone: string;
  telegram: string;
  email: string;
  is_team: boolean;
  condition?: string;
}
export interface KnowledgeItem {
  id: number;
  zone: string;
  process: string;
  system: string;
  question: string;
  examples: string[];
  rule: string;
  note: string;
  asker: string;
  frequent: boolean;
  minutes: number;
  per_week: number;
  responsible: KnowledgeContact | null;
  escalation: KnowledgeContact[];
}
export interface BotAnswer {
  question: string;
  found: boolean;
  confidence: number;
  answer_text: string;
  best: KnowledgeItem | null;
  alternatives: KnowledgeItem[];
}
export type KnowledgeFormat = "json" | "jsonl" | "chat" | "md";

/** AI yuklama tahlili (POST /api/ai/workload/). */
export interface AIWorkload {
  summary: string;
  overloaded: { member_id: number; reason: string }[];
  recommendations: {
    kind: "reassign" | "share" | "automate" | "capacity" | "hire" | "rule" | "estimate";
    title: string;
    detail: string;
    task_ids?: number[];
    from_id?: number | null;
    to_id?: number | null;
    hours_per_week?: number;
    priority: "high" | "medium" | "low";
  }[];
  best_fit: { zone: string; member_id: number; why: string }[];
  risks: string[];
  meta: AIText["meta"];
}
