"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useEffect } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { useModel, useOrgMutation } from "@/hooks/use-org";
import { orgApi } from "@/lib/api/endpoints";
import type { Member, MemberLevel } from "@/lib/api/types";

import { CheckboxField, fromId, FormDialog, NONE, NumberField, Row, SelectField, TextareaField, TextField, toId } from "./form-kit";
import { departmentOptions, memberOptions, teamOptions } from "./options";
import { TeamContacts } from "./team-contacts";

export const LEVELS: MemberLevel[] = ["L1", "L2", "L3", "LEAD", "BIZ", "EXT"];

const schema = z.object({
  name: z.string().trim().min(2).max(80),
  role: z.string().trim().min(2).max(80),
  department: z.string(),
  team: z.string(),
  manager: z.string(),
  member_of: z.string(),
  is_team: z.boolean(),
  phone: z.string().max(40),
  telegram: z.string().max(64),
  email: z.union([z.literal(""), z.email()]),
  location: z.string().max(120),
  trigger: z.string().max(200),
  does: z.string().max(3000),
  excludes: z.string().max(3000),
  level: z.string(),
  duties: z.string().max(8000),
  escalation: z.string().max(3000),
  capacity: z.number().min(0).max(2000),
});
type Values = z.infer<typeof schema>;

/** Xodim: lavozim, bo'lim/jamoa, rahbar, aloqa ma'lumotlari va javobgarlik chegaralari. */
export function MemberDialog({ open, onOpenChange, member, presetDepartment }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  member?: Member;
  presetDepartment?: number | null;
}) {
  const t = useTranslations();
  const model = useModel();
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  const dept = useWatch({ control: form.control, name: "department" });

  useEffect(() => {
    if (!open) return;
    form.reset({
      name: member?.name ?? "", role: member?.role ?? "",
      department: fromId(member ? member.department : presetDepartment), team: fromId(member?.team), manager: fromId(member?.manager),
      member_of: fromId(member?.member_of), is_team: member?.is_team ?? false, phone: member?.phone ?? "", telegram: member?.telegram ?? "", email: member?.email ?? "",
      location: member?.location ?? "", trigger: member?.trigger ?? "", does: member?.does ?? "", excludes: member?.excludes ?? "",
      level: member?.level || NONE, duties: (member?.duties ?? []).join(String.fromCharCode(10)), escalation: member?.escalation ?? "",
      capacity: member?.capacity ?? 40,
    });
  }, [open, member, presetDepartment, form]);

  const save = useOrgMutation(
    (v: Values) => {
      const body = {
        ...v, department: toId(v.department), team: toId(v.team), manager: toId(v.manager),
        member_of: v.is_team ? null : toId(v.member_of),
        level: (v.level === NONE ? "" : v.level) as Member["level"],
        duties: v.duties.split(String.fromCharCode(10)).map((x) => x.trim()).filter(Boolean),
        capacity: Number(v.capacity),
      };
      return member ? orgApi.members.update(member.id, body) : orgApi.members.create(body);
    },
    member ? t("common.saved") : t("forms.member.created"),
  );
  const remove = useOrgMutation(() => orgApi.members.remove(member!.id), t("common.deleted"));
  const managers = memberOptions(model, t("common.none")).filter((o) => o.value !== String(member?.id));
  const isTeam = useWatch({ control: form.control, name: "is_team" });
  const teamsOf = [{ value: NONE, label: t("common.none") },
    ...model.memberOrder.filter((m) => m.is_team && m.id !== member?.id).map((m) => ({ value: String(m.id), label: m.name }))];

  return (
    <FormDialog
      translated
      wide open={open} onOpenChange={onOpenChange}
      title={member ? t("forms.member.edit") : t("forms.member.new")}
      onSubmit={form.handleSubmit(async (v) => { await save.mutateAsync(v); onOpenChange(false); })}
      submitting={save.isPending}
      onDelete={member ? () => remove.mutateAsync(undefined) : undefined}
      deleteConfirm={member ? t("forms.member.deleteConfirm", { count: model.load.get(member.id) ?? 0 }) : undefined}
    >
      <Row>
        <TextField control={form.control} name="name" label={t("forms.member.name")} />
        <TextField control={form.control} name="role" label={t("forms.member.position")} />
      </Row>
      <Row>
        <SelectField control={form.control} name="department" label={t("forms.department")} options={departmentOptions(model, t("forms.noDepartment"))} />
        <SelectField control={form.control} name="team" label={t("forms.teamField")} options={teamOptions(model, dept && dept !== NONE ? Number(dept) : null, t("forms.noTeam"))} />
      </Row>
      <Row>
        <SelectField control={form.control} name="manager" label={t("forms.member.manager")} options={managers} />
        <TextField control={form.control} name="location" label={t("forms.member.location")} />
      </Row>
      <Row>
        <TextField control={form.control} name="phone" label={t("forms.phone")} placeholder="+998 90 123 45 67" />
        <TextField control={form.control} name="telegram" label="Telegram" placeholder="username" />
      </Row>
      <TextField control={form.control} name="email" label="Email" type="email" />
      <CheckboxField control={form.control} name="is_team" label={t("forms.member.isTeam")} />
      {!isTeam && (
        <SelectField control={form.control} name="member_of" label={t("forms.member.memberOf")} options={teamsOf}
          description={t("forms.member.memberOfHint")} />
      )}
      {member?.is_team && <TeamContacts member={model.member.get(member.id) ?? member} />}
      <Row>
        <SelectField
          control={form.control} name="level" label={t("people.level")}
          options={[{ value: NONE, label: "—" }, ...LEVELS.map((l) => ({ value: l, label: t(`people.levels.${l}`) }))]}
        />
        <TextField control={form.control} name="trigger" label={t("forms.member.trigger")} />
      </Row>
      <TextareaField control={form.control} name="does" label={t("forms.member.does")} rows={2} />
      <TextareaField control={form.control} name="duties" label={t("people.duties")} description={t("people.dutiesHint")} rows={5} />
      <TextareaField control={form.control} name="excludes" label={t("forms.member.excludes")} rows={2} />
      <TextareaField control={form.control} name="escalation" label={t("people.escalation")} rows={2} />
      <NumberField control={form.control} name="capacity" label={t("time.capacity")} description={t("time.capacityHint")} step="1" />
    </FormDialog>
  );
}
