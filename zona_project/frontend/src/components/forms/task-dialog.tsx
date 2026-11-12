"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowDown, ArrowUp, Plus, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect } from "react";
import { Controller, useFieldArray, useForm, type Control } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useModel, useOrgMutation } from "@/hooks/use-org";
import { orgApi } from "@/lib/api/endpoints";
import type { Task } from "@/lib/api/types";

import { fromId, FormDialog, NONE, Row, SelectField, TextareaField, toId, type Option } from "./form-kit";
import { memberOptions, processOptions } from "./options";

const schema = z.object({
  title: z.string().trim().min(3).max(300),
  owner: z.string(),
  process: z.string(),
  note: z.string().max(2000),
  fallbacks: z.array(z.object({ member: z.string(), condition: z.string().max(200) })),
});
type Values = z.infer<typeof schema>;

/** Vazifa (savol turi) yaratish/tahrirlash. preset — yangi vazifa uchun boshlang'ich qiymatlar. */
export function TaskDialog({ open, onOpenChange, task, preset }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  task?: Task;
  preset?: { title?: string; owner?: number | null; process?: number | null };
}) {
  const t = useTranslations();
  const model = useModel();
  const form = useForm<Values>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (open) {
      form.reset({
        title: task?.title ?? preset?.title ?? "",
        owner: fromId(task ? task.owner : preset?.owner),
        process: fromId(task ? task.process : preset?.process),
        note: task?.note ?? "",
        fallbacks: (task?.fallbacks ?? []).map((f) => ({ member: String(f.member), condition: f.condition })),
      });
    }
  }, [open, task, preset, form]);

  const save = useOrgMutation(
    (v: Values) => {
      const owner = toId(v.owner);
      // bo'sh qatorlar, takrorlar va asosiy mas'ulning o'zi navbatga kirmaydi
      const seen = new Set<number>(owner ? [owner] : []);
      const fallbacks = v.fallbacks.flatMap((f) => {
        const member = toId(f.member);
        if (!member || seen.has(member)) return [];
        seen.add(member);
        return [{ member, condition: f.condition.trim() }];
      });
      const body = { title: v.title, owner, process: toId(v.process), note: v.note, fallbacks };
      return task ? orgApi.tasks.update(task.id, body) : orgApi.tasks.create(body);
    },
    task ? t("common.saved") : t("forms.task.created"),
  );
  const remove = useOrgMutation(() => orgApi.tasks.remove(task!.id), t("common.deleted"));

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={task ? t("forms.task.edit") : t("forms.task.new")}
      onSubmit={form.handleSubmit(async (v) => { await save.mutateAsync(v); onOpenChange(false); })}
      submitting={save.isPending}
      onDelete={task ? () => remove.mutateAsync(undefined) : undefined}
      wide
    >
      <TextareaField control={form.control} name="title" label={t("forms.task.title")} rows={2} placeholder={t("forms.task.titleHint")} />
      <Row>
        <SelectField control={form.control} name="owner" label={t("forms.task.ownerFirst")} options={memberOptions(model, t("common.unassigned"))} />
        <SelectField control={form.control} name="process" label={t("forms.task.process")} options={processOptions(model, t("forms.noProcess"))} />
      </Row>
      <FallbackEditor control={form.control} options={memberOptions(model, "—").filter((o) => o.value !== NONE)} />
      <TextareaField control={form.control} name="note" label={t("forms.note")} rows={2} />
    </FormDialog>
  );
}

/** Navbat zanjiri: 1-navbat — asosiy mas'ul; bu yerda 2-, 3-... navbat va qachon ularga o'tishi. */
function FallbackEditor({ control, options }: { control: Control<Values>; options: Option[] }) {
  const t = useTranslations("forms.task");
  const { fields, append, remove, move } = useFieldArray({ control, name: "fallbacks" });
  return (
    <Field>
      <FieldLabel>{t("fallbacks")}</FieldLabel>
      <FieldDescription>{t("fallbacksHint")}</FieldDescription>
      <div className="grid gap-2">
        {fields.map((f, i) => (
          <div key={f.id} className="flex items-center gap-2 rounded-lg border bg-muted/30 p-2">
            <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary/10 font-mono text-xs font-semibold text-primary">
              {i + 2}
            </span>
            <Controller
              control={control}
              name={`fallbacks.${i}.member`}
              render={({ field }) => (
                <Select value={field.value || undefined} onValueChange={field.onChange}>
                  <SelectTrigger className="w-44 shrink-0" aria-label={t("fallbackMember")}>
                    <SelectValue placeholder={t("fallbackMember")} />
                  </SelectTrigger>
                  <SelectContent className="max-h-80">
                    {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            <Controller
              control={control}
              name={`fallbacks.${i}.condition`}
              render={({ field }) => (
                <Input {...field} value={field.value ?? ""} placeholder={t("fallbackCondition")} aria-label={t("fallbackCondition")} className="min-w-0 flex-1" />
              )}
            />
            <div className="flex shrink-0">
              <Button type="button" size="icon" variant="ghost" className="size-7" disabled={i === 0} onClick={() => move(i, i - 1)} aria-label="up">
                <ArrowUp className="size-3.5" />
              </Button>
              <Button type="button" size="icon" variant="ghost" className="size-7" disabled={i === fields.length - 1} onClick={() => move(i, i + 1)} aria-label="down">
                <ArrowDown className="size-3.5" />
              </Button>
              <Button type="button" size="icon" variant="ghost" className="size-7 text-muted-foreground hover:text-destructive" onClick={() => remove(i)} aria-label="remove">
                <X className="size-3.5" />
              </Button>
            </div>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => append({ member: "", condition: "" })}>
          <Plus className="size-3.5" />{t("addFallback")}
        </Button>
      </div>
    </Field>
  );
}
