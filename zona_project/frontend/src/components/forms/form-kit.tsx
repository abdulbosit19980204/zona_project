"use client";

import { Languages, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { Controller, type Control, type FieldPath, type FieldValues } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useOrg } from "@/hooks/use-org";
import { cn } from "@/lib/utils";

/** Radix Select bo'sh qiymatni qabul qilmaydi: "tanlanmagan" shu belgi bilan ifodalanadi. */
export const NONE = "__none__";
export const toId = (v: string): number | null => (v === NONE || v === "" ? null : Number(v));
export const fromId = (v: number | null | undefined): string => (v == null ? NONE : String(v));

export interface Option {
  value: string;
  label: string;
}

export function FormDialog({
  open, onOpenChange, title, description, children, onSubmit, submitting, submitLabel, onDelete, deleteConfirm, wide, translated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  onSubmit: () => void;
  submitting?: boolean;
  submitLabel?: string;
  onDelete?: () => Promise<unknown> | void;
  deleteConfirm?: string;
  wide?: boolean;
  /** Matnlar AI orqali boshqa tillarga tarjima qilinadi: foydalanuvchiga eslatma ko'rsatiladi. */
  translated?: boolean;
}) {
  const t = useTranslations("common");
  const [confirming, setConfirming] = useState(false);
  return (
    <Dialog open={open} onOpenChange={(o) => { setConfirming(false); onOpenChange(o); }}>
      <DialogContent className={cn("max-h-[90vh] overflow-y-auto", wide ? "sm:max-w-2xl" : "sm:max-w-lg")}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
          {translated && <TranslateNote />}
        </DialogHeader>
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit();
          }}
        >
          <FieldGroup>{children}</FieldGroup>
          <DialogFooter className="mt-6 items-center gap-2 sm:justify-between">
            {onDelete ? (
              confirming ? (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-destructive">{deleteConfirm ?? t("confirmDelete")}</span>
                  <Button type="button" size="sm" variant="destructive" onClick={async () => { await onDelete(); onOpenChange(false); }}>{t("yes")}</Button>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setConfirming(false)}>{t("no")}</Button>
                </div>
              ) : (
                <Button type="button" variant="ghost" className="text-destructive" onClick={() => setConfirming(true)}>
                  <Trash2 className="size-4" />{t("delete")}
                </Button>
              )
            ) : <span />}
            <div className="flex gap-2">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>{t("cancel")}</Button>
              <Button type="submit" disabled={submitting}>{submitting ? t("saving") : submitLabel ?? t("save")}</Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

interface BaseProps<T extends FieldValues> {
  control: Control<T>;
  name: FieldPath<T>;
  label: string;
  description?: string;
  className?: string;
}

export function TextField<T extends FieldValues>({ control, name, label, description, className, type = "text", placeholder }: BaseProps<T> & { type?: string; placeholder?: string }) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid} className={className}>
          <FieldLabel htmlFor={name}>{label}</FieldLabel>
          <Input id={name} type={type} placeholder={placeholder} {...field} value={field.value ?? ""} aria-invalid={fieldState.invalid} />
          {description && <FieldDescription>{description}</FieldDescription>}
          {fieldState.error && <FieldError errors={[fieldState.error]} />}
        </Field>
      )}
    />
  );
}

export function NumberField<T extends FieldValues>({ control, name, label, description, className, step }: BaseProps<T> & { step?: string }) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid} className={className}>
          <FieldLabel htmlFor={name}>{label}</FieldLabel>
          <Input
            id={name} type="number" step={step} value={field.value ?? ""}
            onChange={(e) => field.onChange(e.target.value === "" ? null : Number(e.target.value))}
            onBlur={field.onBlur}
          />
          {description && <FieldDescription>{description}</FieldDescription>}
          {fieldState.error && <FieldError errors={[fieldState.error]} />}
        </Field>
      )}
    />
  );
}

export function TextareaField<T extends FieldValues>({ control, name, label, description, className, rows = 3, placeholder }: BaseProps<T> & { rows?: number; placeholder?: string }) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid} className={className}>
          <FieldLabel htmlFor={name}>{label}</FieldLabel>
          <Textarea id={name} rows={rows} placeholder={placeholder} {...field} value={field.value ?? ""} />
          {description && <FieldDescription>{description}</FieldDescription>}
          {fieldState.error && <FieldError errors={[fieldState.error]} />}
        </Field>
      )}
    />
  );
}

export function SelectField<T extends FieldValues>({ control, name, label, description, className, options, placeholder }: BaseProps<T> & { options: Option[]; placeholder?: string }) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid} className={className}>
          <FieldLabel htmlFor={name}>{label}</FieldLabel>
          <Select value={field.value ?? NONE} onValueChange={field.onChange}>
            <SelectTrigger id={name} className="w-full"><SelectValue placeholder={placeholder} /></SelectTrigger>
            <SelectContent className="max-h-80">
              {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
          {description && <FieldDescription>{description}</FieldDescription>}
          {fieldState.error && <FieldError errors={[fieldState.error]} />}
        </Field>
      )}
    />
  );
}

export function CheckboxField<T extends FieldValues>({ control, name, label, description }: BaseProps<T>) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <Field orientation="horizontal">
          <Checkbox id={name} checked={!!field.value} onCheckedChange={(v) => field.onChange(v === true)} />
          <div className="grid gap-0.5">
            <FieldLabel htmlFor={name} className="font-normal">{label}</FieldLabel>
            {description && <FieldDescription>{description}</FieldDescription>}
          </div>
        </Field>
      )}
    />
  );
}

export function Row({ children }: { children: ReactNode }) {
  return <div className="grid gap-4 sm:grid-cols-2">{children}</div>;
}

/** "Istalgan tilda yozing" eslatmasi — faqat AI tarjima yoqilgan bo'lsa. */
function TranslateNote() {
  const t = useTranslations("forms");
  const { data } = useOrg();
  if (!data?.meta.ai.translate) return null;
  return (
    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <Languages className="size-3.5 shrink-0 text-primary" />{t("anyLanguage")}
    </p>
  );
}
