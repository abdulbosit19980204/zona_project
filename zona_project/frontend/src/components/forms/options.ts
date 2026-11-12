import type { Model } from "@/lib/model";

import { NONE, type Option } from "./form-kit";

export const memberOptions = (model: Model, none?: string): Option[] => [
  ...(none ? [{ value: NONE, label: none }] : []),
  ...model.memberOrder.map((m) => ({ value: String(m.id), label: `${m.name} — ${m.role}` })),
];

export const processOptions = (model: Model, none?: string): Option[] => [
  ...(none ? [{ value: NONE, label: none }] : []),
  ...model.state.processes.map((p) => ({
    value: String(p.id),
    label: (model.systemName(p) ? `${model.systemName(p)} · ` : "") + p.name,
  })),
];

export const departmentOptions = (model: Model, none?: string): Option[] => [
  ...(none ? [{ value: NONE, label: none }] : []),
  ...model.state.departments.map((d) => ({ value: String(d.id), label: d.name })),
];

export const teamOptions = (model: Model, deptId: number | null, none?: string): Option[] => [
  ...(none ? [{ value: NONE, label: none }] : []),
  ...model.state.teams.filter((t) => deptId === null || t.department === deptId)
    .map((t) => ({ value: String(t.id), label: `${model.dept.get(t.department)?.name ?? ""} / ${t.name}` })),
];

export const systemOptions = (model: Model, none?: string): Option[] => [
  ...(none ? [{ value: NONE, label: none }] : []),
  ...model.state.systems.map((s) => ({ value: String(s.id), label: s.name })),
];
