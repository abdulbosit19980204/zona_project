/** Backend (Django REST) javoblari. Maydonlar backend/zona/serializers.py bilan bir xil. */

export type RoleKey = "owner" | "executor" | "approver" | "supervisor" | "contributor" | "backup";
export type ProcessRoleKey = Exclude<RoleKey, "executor">;
export type AppRole = "admin" | "editor" | "viewer";

export interface Department {
  id: number;
  name: string;
  description: string;
  order: number;
}

export interface Team {
  id: number;
  department: number;
  name: string;
  description: string;
  lead: number | null;
  order: number;
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
  email: string;
  phone: string;
  telegram: string;
  location: string;
  order: number;
}

export interface Authority {
  id: number;
  member: number;
  title: string;
  scope: string;
  order: number;
}

export interface SystemItem {
  id: number;
  name: string;
  order: number;
}

export interface Process {
  id: number;
  name: string;
  system: number | null;
  description: string;
  order: number;
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
}

export interface Task {
  id: number;
  title: string;
  process: number | null;
  owner: number | null;
  fallbacks: TaskFallback[];
  note: string;
  is_custom: boolean;
  order: number;
}

export interface EdgeCase {
  id: number;
  situation: string;
  first_owner: number | null;
  then_text: string;
  order: number;
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
  ai: { route: boolean; person: boolean; audit: boolean };
  pending_approvals: number;
}

export interface OrgState {
  meta: Meta;
  me: Me | AnonymousMe;
  departments: Department[];
  teams: Team[];
  members: Member[];
  authorities: Authority[];
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

export interface ChangeRequest {
  id: number;
  kind: ChangeKind;
  payload: ChangePayload;
  title: string;
  reason: string;
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

export type AITaskKey = "route" | "person" | "audit";
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
  models: { provider: string; model: string; calls: number; errors: number; input_tokens: number; output_tokens: number }[];
  tasks: { task: string; calls: number; tokens: number }[];
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
  | { type: "approval"; data: { id: number; status: ChangeStatus; title: string } };
