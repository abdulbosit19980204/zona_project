/** IT inventarizatsiya API (/api/inventory/...). */
import { api } from "@/lib/api/client";

export type Level = "manager" | "director" | "collector";
export type Condition = "ok" | "repair" | "broken" | "spare" | "missing";
export type BranchStatus = "planned" | "active" | "done";
export type Flag = "done" | "active" | "slowing" | "slow" | "idle";

export interface InvMe {
  id: number; username: string; name: string; level: Level; branches: number[] | null; restricted: boolean;
  can: { write: boolean; manage: boolean; analytics: boolean };
}
export interface Org { id: number; name: string; code: string }
export interface Branch {
  id: number; code: string; name: string; region: string; note: string; status: BranchStatus; status_label: string;
  conductor: string; started_at: string | null; finished_at: string | null; order: number;
}
export interface DeviceType {
  id: number; name: string; group: string; description: string; serial_hint: string; extra_hint: string;
  brands: string[]; is_active: boolean; order: number;
  name_ru: string; description_ru: string; serial_hint_ru: string; extra_hint_ru: string;
}
export interface Boot {
  me: InvMe; orgs: Org[]; branches: Branch[]; locations: { id: number; name: string; name_ru: string }[]; device_types: DeviceType[];
  conditions: { value: Condition; label: string }[]; branch_statuses: { value: BranchStatus; label: string }[];
  levels: { value: Level; label: string }[];
}
export interface PhotoRef { id: number; url: string; thumb: string; width: number; height: number }
export interface LogRow {
  id: number; at: string; user: string; user_id: number | null; branch: string; branch_id: number | null;
  item: number | null; entity: string; action: string; action_label: string; summary: string;
  changes: Record<string, [unknown, unknown]>;
}
export interface Item {
  id: number; inv_number: string; org: number | null; org_name: string; branch: number; branch_name: string;
  location: string; device_type: number; device_type_name: string; group: string; brand: string; model: string;
  serial: string; quantity: number; condition: Condition; condition_label: string; employee: number | null;
  employee_name: string; employee_position: string; employee_phone: string; note: string; is_deleted: boolean;
  created_by: string; updated_by: string; created_at: string; updated_at: string; photos: PhotoRef[];
  history?: LogRow[]; duplicate?: { id: number; inv_number: string; branch: string } | null;
}
export interface ItemInput {
  org: number | null; branch: number | null; location: string; device_type: number | null; brand: string;
  model: string; serial: string; quantity: number; condition: Condition; employee: number | null; note: string;
  photos: number[];
}
export interface Page<T> { count: number; page: number; page_size: number; results: T[]; quantity?: number }
export type AckStatus = "pending" | "signed" | "revoked";
export interface AckBrief { id: number; status: AckStatus; created_at: string; opened_at: string | null; signed_at: string | null; issues: number }
export interface Employee {
  id: number; full_name: string; position: string; phone: string; telegram: string; ack: AckBrief | null;
  org: number | null; org_name: string;
  branch: number | null; branch_name: string; project: string; department: string; note: string;
  is_active: boolean; source: string; devices: number;
}
export interface EmployeeList { count: number; results: Employee[]; projects: string[]; departments: string[] }
export interface AccessRow {
  id: number; user_id: number; username: string; name: string; first_name: string; last_name: string; level: Level;
  level_label: string; is_active: boolean; branches: number[]; branch_names: string[]; note: string;
  has_password: boolean; last_login: string | null; created_at: string; items: number; password?: string;
}
export interface BranchStat extends Branch {
  rows: number; qty: number; broken: number; missing: number; no_serial: number; no_employee: number;
  with_photo: number; today: number; week: number; last_at: string | null; employees: number;
  employees_with_devices: number; coverage: number | null; photo_pct: number | null; collectors: number; flag: Flag;
  acks_signed: number; acks_pending: number;
}
export interface Stats {
  generated_at: string; days: number;
  totals: {
    rows: number; qty: number; branches: number; done: number; active: number; planned: number; slow: number;
    employees: number; employees_total: number; employees_with_devices: number; today: number; week: number;
    no_serial: number; no_employee: number; with_photo: number; broken: number; missing: number; deleted: number;
    collectors: number; collectors_logged_in: number; acks_signed: number; acks_pending: number;
  };
  branches: BranchStat[];
  daily: { date: string; create: number; update: number; delete: number }[];
  by_condition: { value: Condition; label: string; qty: number }[];
  by_type: { name: string; group: string; rows: number; qty: number }[];
  by_group: { name: string; qty: number }[];
  by_org: { name: string; qty: number; rows: number }[];
  by_location: { name: string; qty: number }[];
  leaderboard: { user_id: number; name: string; username: string; create: number; update: number; delete: number;
    week: number; last_at: string | null; branches: string[] }[];
}
export interface ImportResult {
  created?: number; updated?: number; unchanged?: number; employees_created: number; employees_updated: number;
  errors: { sheet?: string; row: number; message: string }[]; warnings: { sheet?: string; row: number; message: string }[];
  dry_run: boolean;
}

export interface AckItem {
  id: number; inv_number: string; type: string; type_ru: string; group: string; brand: string; model: string; serial: string;
  quantity: number; condition: Condition; condition_label: string; location: string; branch: string;
  photos: { thumb: string; url: string }[]; result?: { id: number; ok: boolean; comment: string } | null;
}
export interface Ack {
  id: number; token?: string; path: string; status: AckStatus; employee: number; employee_name: string; position: string;
  phone: string; telegram: string; branch: string; branch_id: number | null; items_count: number; issues: number;
  created_at: string; created_by?: string; opened_at: string | null; signed_at: string | null; signer_name: string;
  outdated: boolean; items?: AckItem[]; comment?: string; signature_url?: string; ip?: string; user_agent?: string;
  lang?: string; company?: string;
}

const B = "inventory/";
const get = async <T>(url: string, params?: object) => (await api.get<T>(B + url, { params })).data;
const post = async <T>(url: string, body?: unknown) => (await api.post<T>(B + url, body)).data;
const patch = async <T>(url: string, body?: unknown) => (await api.patch<T>(B + url, body)).data;
const del = async <T>(url: string) => (await api.delete<T>(B + url)).data;

export type Params = Record<string, string | number | boolean | undefined | null>;

function clean(params: Params) {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "" && v !== false));
}

async function upload<T>(url: string, file: File, extra: Record<string, string> = {}) {
  const form = new FormData();
  form.append("file", file);
  Object.entries(extra).forEach(([k, v]) => form.append(k, v));
  return (await api.post<T>(B + url, form, { headers: { "Content-Type": "multipart/form-data" } })).data;
}

/** Faylni (token bilan) yuklab olib, brauzerda saqlash. */
export async function download(url: string, params: Params = {}, fallbackName = "fayl.xlsx") {
  const r = await api.get<Blob>(B + url, { params: clean(params), responseType: "blob" });
  const cd = String(r.headers["content-disposition"] ?? "");
  const name = /filename="?([^";]+)"?/.exec(cd)?.[1] ?? fallbackName;
  const href = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 4000);
}

export const inv = {
  bootstrap: () => get<Boot>("bootstrap/"),
  items: (params: Params) => get<Page<Item>>("items/", clean(params)),
  item: (id: number) => get<Item>(`items/${id}/`),
  createItem: (body: ItemInput) => post<Item>("items/", body),
  updateItem: (id: number, body: Partial<ItemInput>) => patch<Item>(`items/${id}/`, body),
  deleteItem: (id: number) => del<null>(`items/${id}/`),
  restoreItem: (id: number) => post<Item>(`items/${id}/restore/`),
  checkSerial: (serial: string, exclude?: number) =>
    get<{ duplicate: Item["duplicate"] }>("items/check-serial/", clean({ serial, exclude })),
  uploadPhotos: async (files: File[], onProgress?: (pct: number) => void) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name));
    return (await api.post<PhotoRef[]>(B + "photos/", form, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (e) => onProgress?.(e.total ? Math.round((100 * e.loaded) / e.total) : 0),
    })).data;
  },
  deletePhoto: (id: number) => del<null>(`photos/${id}/`),
  importItems: (file: File, dryRun: boolean, branch?: number | null) =>
    upload<ImportResult>("items/import/", file, { dry_run: dryRun ? "1" : "", ...(branch ? { branch: String(branch) } : {}) }),

  employees: (params: Params) => get<EmployeeList>("employees/", clean(params)),
  createEmployee: (body: Partial<Employee>) => post<Employee>("employees/", body),
  updateEmployee: (id: number, body: Partial<Employee>) => patch<Employee>(`employees/${id}/`, body),
  deleteEmployee: (id: number) => del<{ deactivated?: boolean; devices?: number } | null>(`employees/${id}/`),
  importEmployees: (file: File, dryRun: boolean) => upload<ImportResult>("employees/import/", file, { dry_run: dryRun ? "1" : "" }),
  employeesFromStaff: (dryRun: boolean) =>
    post<{ created: number; updated: number; unmapped: number; dry_run: boolean }>("employees/from-staff/", { dry_run: dryRun }),

  branches: () => get<Branch[]>("branches/"),
  createBranch: (body: Partial<Branch>) => post<Branch>("branches/", body),
  updateBranch: (id: number, body: Partial<Branch>) => patch<Branch>(`branches/${id}/`, body),
  deleteBranch: (id: number) => del<null>(`branches/${id}/`),
  saveCatalog: (body: Record<string, unknown>) => post<unknown>("catalog/", body),

  users: () => get<AccessRow[]>("users/"),
  createUser: (body: Record<string, unknown>) => post<AccessRow>("users/", body),
  updateUser: (id: number, body: Record<string, unknown>) => patch<AccessRow>(`users/${id}/`, body),
  deleteUser: (id: number) => del<null>(`users/${id}/`),
  resetPassword: (id: number) => post<{ password: string; username: string }>(`users/${id}/reset-password/`, {}),
  generateUsers: () => post<{ created: { username: string; password: string; branch: string }[] }>("users/generate/", {}),

  createAck: (employeeId: number) => post<Ack>(`employees/${employeeId}/ack/`),
  acks: (params: Params) => get<{ count: number; results: Ack[] }>("acks/", clean(params)),
  ack: (id: number) => get<Ack>(`acks/${id}/`),
  revokeAck: (id: number) => post<Ack>(`acks/${id}/revoke/`),
  acksBulk: (branch?: number | null) => post<{ created: number; skipped: number }>("acks/bulk/", { branch: branch ?? undefined }),
  publicAck: (token: string) => get<Ack>(`public/ack/${token}/`),
  publicSign: (token: string, body: { name: string; signature: string; items: { id: number; ok: boolean; comment: string }[]; comment: string; lang: string }) =>
    post<Ack>(`public/ack/${token}/sign/`, body),

  logs: (params: Params) => get<Page<LogRow> & { users: { id: number; name: string }[] }>("logs/", clean(params)),
  stats: (params: Params = {}) => get<Stats>("stats/", clean(params)),
};
