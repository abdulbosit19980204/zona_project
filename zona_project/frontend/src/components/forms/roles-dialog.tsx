"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { RoleGlyph } from "@/components/common/role";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { useCan, useModel, useOrgMutation } from "@/hooks/use-org";
import { approvalsApi, orgApi } from "@/lib/api/endpoints";
import type { ProcessRoleKey } from "@/lib/api/types";
import { PROCESS_ROLES } from "@/lib/model";

import { FormDialog } from "./form-kit";

/**
 * Xodimning jarayondagi rollari. Muharrir — darhol saqlaydi; kuzatuvchi — tasdiqlash uchun taklif yuboradi.
 */
export function RolesDialog({ open, onOpenChange, processId, memberId }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  processId: number;
  memberId: number;
}) {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const current = (model.rolesOf.get(processId) ?? []).filter((r) => r.member === memberId);
  const [checked, setChecked] = useState<Set<ProcessRoleKey>>(new Set());
  const [reason, setReason] = useState("");
  // Dialog ochilganda joriy rollar bilan boshlanadi (effektsiz: render paytida holatni moslash).
  const [wasOpen, setWasOpen] = useState(false);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setChecked(new Set(current.map((r) => r.role)));
      setReason("");
    }
  }

  const save = useOrgMutation(async () => {
    for (const role of PROCESS_ROLES) {
      const has = current.find((r) => r.role === role);
      if (checked.has(role) && !has) {
        if (can.edit) await orgApi.roles.create({ process: processId, member: memberId, role });
        else await approvalsApi.create("role_add", { process: processId, member: memberId, role }, reason);
      }
      if (!checked.has(role) && has) {
        if (can.edit) await orgApi.roles.remove(has.id);
        else await approvalsApi.create("role_remove", { role_id: has.id }, reason);
      }
    }
  }, can.edit ? t("forms.roles.saved") : t("forms.roles.proposed"));

  const process = model.process.get(processId);
  const member = model.member.get(memberId);
  const link = model.link(processId, memberId);
  if (!process || !member) return null;

  return (
    <FormDialog
      open={open} onOpenChange={onOpenChange}
      title={`${member.name} · ${process.name}`}
      description={link?.tasks ? t("forms.roles.executes", { count: link.tasks }) : t("forms.roles.noTasks")}
      submitLabel={can.edit ? undefined : t("forms.roles.propose")}
      onSubmit={async () => { await save.mutateAsync(undefined); onOpenChange(false); }}
      submitting={save.isPending}
    >
      {PROCESS_ROLES.map((role) => (
        <Field key={role} orientation="horizontal">
          <Checkbox
            id={`role-${role}`}
            checked={checked.has(role)}
            onCheckedChange={(v) => setChecked((s) => { const n = new Set(s); if (v === true) n.add(role); else n.delete(role); return n; })}
          />
          <RoleGlyph role={role} />
          <div className="grid gap-0.5">
            <FieldLabel htmlFor={`role-${role}`} className="font-normal">{t(`roles.${role}`)}</FieldLabel>
            <FieldDescription>{t(`roles.hint.${role}`)}</FieldDescription>
          </div>
        </Field>
      ))}
      {!can.edit && (
        <Field>
          <FieldLabel htmlFor="reason">{t("approvals.reason")}</FieldLabel>
          <Textarea id="reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          <FieldDescription>{t("forms.roles.approvalHint")}</FieldDescription>
        </Field>
      )}
    </FormDialog>
  );
}
