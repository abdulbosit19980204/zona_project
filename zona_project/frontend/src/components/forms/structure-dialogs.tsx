"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useModel, useOrgMutation } from "@/hooks/use-org";
import { orgApi } from "@/lib/api/endpoints";
import type { Authority, Department, Process, Team } from "@/lib/api/types";

import { fromId, FormDialog, NONE, Row, SelectField, TextareaField, TextField, toId } from "./form-kit";
import { departmentOptions, memberOptions, systemOptions } from "./options";

type Open = { open: boolean; onOpenChange: (open: boolean) => void };

/* ------------------------------------------------------------------ bo'lim */
const deptSchema = z.object({ name: z.string().trim().min(2).max(80), description: z.string().max(200) });

export function DepartmentDialog({ open, onOpenChange, department }: Open & { department?: Department }) {
  const t = useTranslations();
  const form = useForm<z.infer<typeof deptSchema>>({ resolver: zodResolver(deptSchema) });
  useEffect(() => {
    if (open) form.reset({ name: department?.name ?? "", description: department?.description ?? "" });
  }, [open, department, form]);
  const save = useOrgMutation(
    (v: z.infer<typeof deptSchema>) => (department ? orgApi.departments.update(department.id, v) : orgApi.departments.create(v)),
    t("common.saved"),
  );
  const remove = useOrgMutation(() => orgApi.departments.remove(department!.id), t("common.deleted"));
  return (
    <FormDialog
      open={open} onOpenChange={onOpenChange} title={department ? t("forms.dept.edit") : t("forms.dept.new")}
      onSubmit={form.handleSubmit(async (v) => { await save.mutateAsync(v); onOpenChange(false); })}
      submitting={save.isPending} onDelete={department ? () => remove.mutateAsync(undefined) : undefined}
      deleteConfirm={t("forms.dept.deleteConfirm")}
    >
      <TextField control={form.control} name="name" label={t("forms.name")} />
      <TextField control={form.control} name="description" label={t("forms.description")} />
    </FormDialog>
  );
}

/* ------------------------------------------------------------------ jamoa */
const teamSchema = z.object({
  name: z.string().trim().min(2).max(80),
  description: z.string().max(200),
  department: z.string().refine((v) => v !== NONE),
  lead: z.string(),
});

export function TeamDialog({ open, onOpenChange, team, presetDepartment }: Open & { team?: Team; presetDepartment?: number }) {
  const t = useTranslations();
  const model = useModel();
  const form = useForm<z.infer<typeof teamSchema>>({ resolver: zodResolver(teamSchema) });
  useEffect(() => {
    if (open) {
      form.reset({
        name: team?.name ?? "", description: team?.description ?? "",
        department: fromId(team?.department ?? presetDepartment), lead: fromId(team?.lead),
      });
    }
  }, [open, team, presetDepartment, form]);
  const save = useOrgMutation((v: z.infer<typeof teamSchema>) => {
    const body = { name: v.name, description: v.description, department: Number(v.department), lead: toId(v.lead) };
    return team ? orgApi.teams.update(team.id, body) : orgApi.teams.create(body);
  }, t("common.saved"));
  const remove = useOrgMutation(() => orgApi.teams.remove(team!.id), t("common.deleted"));
  return (
    <FormDialog
      open={open} onOpenChange={onOpenChange} title={team ? t("forms.team.edit") : t("forms.team.new")}
      onSubmit={form.handleSubmit(async (v) => { await save.mutateAsync(v); onOpenChange(false); })}
      submitting={save.isPending} onDelete={team ? () => remove.mutateAsync(undefined) : undefined}
    >
      <TextField control={form.control} name="name" label={t("forms.name")} />
      <TextField control={form.control} name="description" label={t("forms.description")} />
      <Row>
        <SelectField control={form.control} name="department" label={t("forms.department")} options={departmentOptions(model)} />
        <SelectField control={form.control} name="lead" label={t("forms.team.lead")} options={memberOptions(model, t("common.none"))} />
      </Row>
    </FormDialog>
  );
}

/* ------------------------------------------------------------------ jarayon */
const processSchema = z.object({
  name: z.string().trim().min(2).max(120),
  system: z.string(),
  newSystem: z.string().max(60),
  description: z.string().max(2000),
  owner: z.string(),
});

export function ProcessDialog({ open, onOpenChange, process }: Open & { process?: Process }) {
  const t = useTranslations();
  const model = useModel();
  const form = useForm<z.infer<typeof processSchema>>({ resolver: zodResolver(processSchema) });
  useEffect(() => {
    if (open) {
      form.reset({ name: process?.name ?? "", system: fromId(process?.system), newSystem: "", description: process?.description ?? "", owner: NONE });
    }
  }, [open, process, form]);
  const save = useOrgMutation(async (v: z.infer<typeof processSchema>) => {
    let system = toId(v.system);
    if (v.newSystem.trim()) system = (await orgApi.systems.create({ name: v.newSystem.trim() })).id;
    const body = { name: v.name, description: v.description, system };
    const saved = process ? await orgApi.processes.update(process.id, body) : await orgApi.processes.create(body);
    const owner = toId(v.owner);
    if (!process && owner) await orgApi.roles.create({ process: saved.id, member: owner, role: "owner" });
    return saved;
  }, t("common.saved"));
  const remove = useOrgMutation(() => orgApi.processes.remove(process!.id), t("common.deleted"));
  return (
    <FormDialog
      open={open} onOpenChange={onOpenChange} title={process ? t("forms.process.edit") : t("forms.process.new")}
      onSubmit={form.handleSubmit(async (v) => { await save.mutateAsync(v); onOpenChange(false); })}
      submitting={save.isPending} onDelete={process ? () => remove.mutateAsync(undefined) : undefined}
      deleteConfirm={t("forms.process.deleteConfirm")}
    >
      <TextField control={form.control} name="name" label={t("forms.name")} />
      <Row>
        <SelectField control={form.control} name="system" label={t("forms.process.system")} options={systemOptions(model, t("forms.process.noSystem"))} />
        <TextField control={form.control} name="newSystem" label={t("forms.process.newSystem")} />
      </Row>
      <TextareaField control={form.control} name="description" label={t("forms.description")} rows={2} />
      {!process && <SelectField control={form.control} name="owner" label={t("roles.owner")} options={memberOptions(model, t("common.none"))} />}
    </FormDialog>
  );
}

/* ------------------------------------------------------------------ vakolat */
const authSchema = z.object({ title: z.string().trim().min(3).max(200), scope: z.string().max(200) });

export function AuthorityDialog({ open, onOpenChange, authority, memberId }: Open & { authority?: Authority; memberId: number }) {
  const t = useTranslations();
  const form = useForm<z.infer<typeof authSchema>>({ resolver: zodResolver(authSchema) });
  useEffect(() => {
    if (open) form.reset({ title: authority?.title ?? "", scope: authority?.scope ?? "" });
  }, [open, authority, form]);
  const save = useOrgMutation(
    (v: z.infer<typeof authSchema>) =>
      authority ? orgApi.authorities.update(authority.id, v) : orgApi.authorities.create({ ...v, member: memberId }),
    t("common.saved"),
  );
  const remove = useOrgMutation(() => orgApi.authorities.remove(authority!.id), t("common.deleted"));
  return (
    <FormDialog
      open={open} onOpenChange={onOpenChange} title={authority ? t("forms.authority.edit") : t("forms.authority.new")}
      description={t("forms.authority.hint")}
      onSubmit={form.handleSubmit(async (v) => { await save.mutateAsync(v); onOpenChange(false); })}
      submitting={save.isPending} onDelete={authority ? () => remove.mutateAsync(undefined) : undefined}
    >
      <TextField control={form.control} name="title" label={t("forms.authority.title")} placeholder={t("forms.authority.titleHint")} />
      <TextField control={form.control} name="scope" label={t("forms.authority.scope")} />
    </FormDialog>
  );
}
