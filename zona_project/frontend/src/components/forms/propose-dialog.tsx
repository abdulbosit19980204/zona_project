"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useEffect } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { useModel, useOrgMutation } from "@/hooks/use-org";
import { approvalsApi } from "@/lib/api/endpoints";
import type { ChangeKind, ProcessRoleKey } from "@/lib/api/types";
import { PROCESS_ROLES } from "@/lib/model";

import { FormDialog, NONE, Row, SelectField, TextareaField, toId } from "./form-kit";
import { memberOptions, processOptions } from "./options";

const schema = z.object({
  kind: z.enum(["task_owner", "role_add", "role_remove"]),
  task: z.string(),
  owner: z.string(),
  process: z.string(),
  member: z.string(),
  role: z.string(),
  roleId: z.string(),
  reason: z.string().max(2000),
}).superRefine((v, ctx) => {
  const need = (field: keyof typeof v) => {
    if (v[field] === NONE || v[field] === "") ctx.addIssue({ code: "custom", path: [field], message: "Tanlang" });
  };
  if (v.kind === "task_owner") need("task");
  if (v.kind === "role_add") { need("process"); need("member"); need("role"); }
  if (v.kind === "role_remove") need("roleId");
});
type Values = z.infer<typeof schema>;

/** Tasdiqlash uchun o'zgarish taklifi: vazifa mas'ulini almashtirish, rol berish yoki olish. */
export function ProposeDialog({ open, onOpenChange, preset }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preset?: Partial<Values>;
}) {
  const t = useTranslations();
  const model = useModel();
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  const kind = useWatch({ control: form.control, name: "kind" }) as ChangeKind | undefined;

  useEffect(() => {
    if (open) {
      form.reset({
        kind: "task_owner", task: NONE, owner: NONE, process: NONE, member: NONE, role: "backup", roleId: NONE, reason: "", ...preset,
      });
    }
  }, [open, preset, form]);

  const submit = useOrgMutation((v: Values) => {
    if (v.kind === "task_owner") return approvalsApi.create("task_owner", { task: Number(v.task), owner: toId(v.owner) }, v.reason);
    if (v.kind === "role_add") {
      return approvalsApi.create("role_add", { process: Number(v.process), member: Number(v.member), role: v.role as ProcessRoleKey }, v.reason);
    }
    return approvalsApi.create("role_remove", { role_id: Number(v.roleId) }, v.reason);
  }, t("approvals.submitted"));

  const taskOptions = model.state.tasks.map((task) => ({
    value: String(task.id),
    label: `${task.title} — ${task.owner ? model.member.get(task.owner)?.name ?? "" : t("common.unassigned")}`,
  }));
  const roleOptions = model.state.roles.map((r) => ({
    value: String(r.id),
    label: `${model.member.get(r.member)?.name ?? "?"}: ${t(`roles.${r.role}`)} — ${model.process.get(r.process)?.name ?? ""}`,
  }));

  return (
    <FormDialog
      wide open={open} onOpenChange={onOpenChange}
      title={t("approvals.propose")} description={t("approvals.proposeHint")} submitLabel={t("approvals.send")}
      onSubmit={form.handleSubmit(async (v) => { await submit.mutateAsync(v); onOpenChange(false); })}
      submitting={submit.isPending}
    >
      <SelectField
        control={form.control} name="kind" label={t("approvals.kind")}
        options={(["task_owner", "role_add", "role_remove"] as const).map((k) => ({ value: k, label: t(`approvals.kinds.${k}`) }))}
      />
      {kind === "task_owner" && (
        <>
          <SelectField control={form.control} name="task" label={t("forms.task.title")} options={taskOptions} />
          <SelectField control={form.control} name="owner" label={t("approvals.newOwner")} options={memberOptions(model, t("common.unassigned"))} />
        </>
      )}
      {kind === "role_add" && (
        <>
          <SelectField control={form.control} name="process" label={t("forms.task.process")} options={processOptions(model)} />
          <Row>
            <SelectField control={form.control} name="member" label={t("nav.employees")} options={memberOptions(model)} />
            <SelectField control={form.control} name="role" label={t("approvals.role")} options={PROCESS_ROLES.map((r) => ({ value: r, label: t(`roles.${r}`) }))} />
          </Row>
        </>
      )}
      {kind === "role_remove" && <SelectField control={form.control} name="roleId" label={t("approvals.role")} options={roleOptions} />}
      <TextareaField control={form.control} name="reason" label={t("approvals.reason")} rows={3} />
    </FormDialog>
  );
}
