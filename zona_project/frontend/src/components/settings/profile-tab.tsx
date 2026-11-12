"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Row, TextareaField, TextField } from "@/components/forms/form-kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FieldGroup } from "@/components/ui/field";
import { queryKeys, useMe } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/client";
import { authApi } from "@/lib/api/endpoints";
import { useAuth } from "@/stores/auth";

const profileSchema = z.object({
  first_name: z.string().max(150),
  last_name: z.string().max(150),
  email: z.union([z.literal(""), z.email()]),
  position: z.string().max(200),
  phone: z.string().max(50),
  telegram: z.string().max(100),
  address: z.string().max(300),
  note: z.string().max(2000),
});
type Profile = z.infer<typeof profileSchema>;

const passwordSchema = z.object({
  old: z.string().min(1),
  next: z.string().min(8),
  confirm: z.string(),
}).refine((v) => v.next === v.confirm, { path: ["confirm"], message: "≠" });
type Password = z.infer<typeof passwordSchema>;

/** Profil: aloqa ma'lumotlari va parol. Parol almashsa, boshqa qurilmalardagi seanslar yopiladi. */
export function ProfileTab() {
  const t = useTranslations();
  const me = useMe();
  const qc = useQueryClient();
  const setUser = useAuth((s) => s.setUser);
  const setTokens = useAuth((s) => s.setTokens);
  const form = useForm<Profile>({ resolver: zodResolver(profileSchema) });
  const pw = useForm<Password>({ resolver: zodResolver(passwordSchema), defaultValues: { old: "", next: "", confirm: "" } });

  useEffect(() => {
    if (me) {
      form.reset({
        first_name: me.first_name, last_name: me.last_name, email: me.email, position: me.position,
        phone: me.phone, telegram: me.telegram, address: me.address, note: me.note,
      });
    }
  }, [me, form]);

  const save = useMutation({
    mutationFn: (v: Profile) => authApi.updateMe(v),
    onSuccess: async (user) => {
      setUser(user);
      await qc.invalidateQueries({ queryKey: queryKeys.state });
      toast.success(t("settings.saved"));
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const change = useMutation({
    mutationFn: (v: Password) => authApi.changePassword(v.old, v.next),
    onSuccess: (r) => {
      setTokens({ access: r.access, refresh: r.refresh });
      pw.reset({ old: "", next: "", confirm: "" });
      toast.success(t("settings.passwordChanged"));
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (!me) return <p className="text-sm text-muted-foreground">{t("settings.anonymous")}</p>;

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
      <Card className="gap-4 p-5">
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="font-semibold">{me.full_name || me.username}</div>
            <div className="text-xs text-muted-foreground">@{me.username}</div>
          </div>
          <Badge variant="outline">{t(`appRoles.${me.role}`)}</Badge>
        </div>
        <form noValidate onSubmit={form.handleSubmit((v) => save.mutate(v))}>
          <FieldGroup>
            <Row>
              <TextField control={form.control} name="first_name" label={t("settings.firstName")} />
              <TextField control={form.control} name="last_name" label={t("settings.lastName")} />
            </Row>
            <Row>
              <TextField control={form.control} name="position" label={t("settings.position")} />
              <TextField control={form.control} name="email" label={t("forms.member.email")} type="email" />
            </Row>
            <Row>
              <TextField control={form.control} name="phone" label={t("forms.member.phone")} placeholder="+998 90 123 45 67" />
              <TextField control={form.control} name="telegram" label={t("forms.member.telegram")} placeholder="@username" />
            </Row>
            <TextField control={form.control} name="address" label={t("settings.address")} />
            <TextareaField control={form.control} name="note" label={t("settings.note")} rows={2} />
          </FieldGroup>
          <Button type="submit" className="mt-5" disabled={save.isPending}>{save.isPending ? t("common.saving") : t("common.save")}</Button>
        </form>
      </Card>
      <Card className="gap-4 p-5">
        <div>
          <div className="font-semibold">{t("settings.password")}</div>
          <p className="text-xs text-muted-foreground">{t("settings.passwordHint")}</p>
        </div>
        <form noValidate onSubmit={pw.handleSubmit((v) => change.mutate(v))}>
          <FieldGroup>
            <TextField control={pw.control} name="old" label={t("settings.oldPassword")} type="password" />
            <TextField control={pw.control} name="next" label={t("settings.newPassword")} type="password" description={t("settings.passwordRule")} />
            <TextField control={pw.control} name="confirm" label={t("settings.confirmPassword")} type="password" />
          </FieldGroup>
          <Button type="submit" variant="outline" className="mt-5" disabled={change.isPending}>{t("settings.changePassword")}</Button>
        </form>
      </Card>
    </div>
  );
}
