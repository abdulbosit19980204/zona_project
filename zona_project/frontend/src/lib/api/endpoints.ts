/** Backend API funksiyalari. Har biri tiplangan; komponentlar to'g'ridan-to'g'ri axios chaqirmaydi. */
import { api } from "./client";
import type {
  AdminUserInput, AIProvider, AIProviderKind, AIRouteResult, AITaskConfig, AITaskKey, AITestResult, AIText, AIUsage,
  AIUsageSummary, AuditEvent, Authority, ChangeKind, ChangePayload, ChangeRequest, ChangeStatus, Department,
  EdgeCase, LoginResponse, Me, Member, OrgState, Process, ProcessRole, SearchResult, Synonym, SystemItem, Task, Team,
  StaffDiff, StaffImportBody, StaffPerson, StaffProject, StaffState, TokenPair, TranslateStatus,
} from "./types";

const get = async <T>(url: string, params?: Record<string, string | number | boolean>) => (await api.get<T>(url, { params })).data;
const post = async <T>(url: string, body: unknown = {}) => (await api.post<T>(url, body)).data;
const patch = async <T>(url: string, body: unknown) => (await api.patch<T>(url, body)).data;
const del = async (url: string) => {
  await api.delete(url);
};

/** Oddiy CRUD resurs: list/create/update/remove. */
function resource<T extends { id: number }>(path: string) {
  return {
    create: (body: Partial<T>) => post<T>(`${path}/`, body),
    update: (id: number, body: Partial<T>) => patch<T>(`${path}/${id}/`, body),
    remove: (id: number) => del(`${path}/${id}/`),
  };
}

export const authApi = {
  login: (username: string, password: string) => post<LoginResponse>("auth/login/", { username, password }),
  logout: (refresh: string) => post<null>("auth/logout/", { refresh }),
  me: () => get<Me>("auth/me/"),
  updateMe: (body: Partial<Me>) => patch<Me>("auth/me/", body),
  changePassword: (old_password: string, new_password: string) =>
    post<TokenPair & { ok: boolean }>("auth/password/", { old_password, new_password }),
};

export const orgApi = {
  state: () => get<OrgState>("state/"),
  events: (limit = 100) => get<AuditEvent[]>("events/", { limit }),
  search: (q: string, limit = 12) => get<SearchResult>("search/", { q, limit }),
  departments: resource<Department>("departments"),
  teams: resource<Team>("teams"),
  members: resource<Member>("members"),
  authorities: resource<Authority>("authorities"),
  systems: resource<SystemItem>("systems"),
  processes: resource<Process>("processes"),
  edgeCases: resource<EdgeCase>("edge-cases"),
  tasks: {
    ...resource<Task>("tasks"),
    move: (id: number, owner: number | null) => post<Task>(`tasks/${id}/move/`, { owner }),
    bulkMove: (ids: number[], owner: number | null) => post<{ moved: number }>("tasks/bulk-move/", { ids, owner }),
    /** Jarayonning barcha vazifalariga ijrochi qo'shish / olib tashlash. */
    processExecutor: (process: number, member: number, remove = false) =>
      post<{ changed: number }>("tasks/process-executor/", { process, member, remove }),
  },
  roles: {
    create: (body: Omit<ProcessRole, "id">) => post<ProcessRole>("roles/", body),
    remove: (id: number) => del(`roles/${id}/`),
  },
  exportXlsx: async () => (await api.get<Blob>("export.xlsx", { responseType: "blob" })).data,
};

/** Dala jamoalari: brendlar bo'yicha savdo tuzilmasi, import/eksport. */
export const staffApi = {
  state: () => get<StaffState>("staff/"),
  /** apply=false — faqat farqlar (preview); apply=true — bazaga yoziladi. */
  import: (body: StaffImportBody) => post<{ projects: StaffDiff[]; applied?: boolean }>("staff/import/", body),
  sync: (project: number, apply = false) => post<{ projects: StaffDiff[]; applied?: boolean }>(`staff/projects/${project}/sync/`, { apply }),
  projects: resource<StaffProject>("staff/projects"),
  people: resource<StaffPerson>("staff/people"),
  export: async (fmt: "xlsx" | "json", project?: number) =>
    (await api.get<Blob>(`staff/export.${fmt}`, { params: project ? { project } : {}, responseType: "blob" })).data,
};

export const approvalsApi = {
  list: (params: { status?: ChangeStatus; mine?: boolean } = {}) =>
    get<ChangeRequest[]>("approvals/", { ...(params.status ? { status: params.status } : {}), ...(params.mine ? { mine: 1 } : {}) }),
  create: (kind: ChangeKind, payload: ChangePayload, reason: string) => post<ChangeRequest>("approvals/", { kind, payload, reason }),
  approve: (id: number, note = "") => post<ChangeRequest>(`approvals/${id}/approve/`, { note }),
  reject: (id: number, note = "") => post<ChangeRequest>(`approvals/${id}/reject/`, { note }),
  cancel: (id: number) => post<ChangeRequest>(`approvals/${id}/cancel/`),
};

export const aiApi = {
  route: (question: string) => post<AIRouteResult>("ai/route/", { question }),
  person: (member: number, lang: string) => post<AIText>("ai/person/", { member, lang }),
  audit: (lang: string) => post<AIText>("ai/audit/", { lang }),
};

export const adminApi = {
  users: {
    list: () => get<Me[]>("admin/users/"),
    create: (body: AdminUserInput) => post<Me>("admin/users/", body),
    update: (id: number, body: Partial<AdminUserInput>) => patch<Me>(`admin/users/${id}/`, body),
    remove: (id: number) => del(`admin/users/${id}/`),
  },
  providers: {
    list: () => get<AIProvider[]>("admin/ai/providers/"),
    kinds: () => get<AIProviderKind[]>("admin/ai/providers/kinds/"),
    create: (body: Partial<AIProvider> & { api_key?: string }) => post<AIProvider>("admin/ai/providers/", body),
    update: (id: number, body: Partial<AIProvider> & { api_key?: string }) => patch<AIProvider>(`admin/ai/providers/${id}/`, body),
    remove: (id: number) => del(`admin/ai/providers/${id}/`),
    test: (id: number) => post<{ ok: boolean; models?: string[]; latency_ms?: number; error?: string }>(`admin/ai/providers/${id}/test/`),
  },
  aiTasks: {
    list: () => get<AITaskConfig[]>("admin/ai/tasks/"),
    update: (task: AITaskKey, body: Partial<AITaskConfig>) => patch<AITaskConfig>(`admin/ai/tasks/${task}/`, body),
    test: (task: AITaskKey) => post<AITestResult>(`admin/ai/tasks/${task}/test/`),
  },
  usage: {
    list: () => get<AIUsage[]>("admin/ai/usage/"),
    summary: () => get<AIUsageSummary>("admin/ai/usage/summary/"),
  },
  translate: {
    status: () => get<TranslateStatus>("admin/ai/translate/"),
    start: () => post<TranslateStatus>("admin/ai/translate/"),
  },
  synonyms: {
    list: () => get<Synonym[]>("synonyms/"),
    ...resource<Synonym>("synonyms"),
    explain: (q: string) => get<{ terms: string[]; expanded: string[]; matches: Record<string, [string, number][]> }>("search/explain/", { q }),
  },
};
