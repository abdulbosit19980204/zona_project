"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { Pencil, Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { DATE_LOCALES } from "@/components/common/activity";
import { CheckboxField, FormDialog, fromId, Row, SelectField, TextareaField, TextField, toId } from "@/components/forms/form-kit";
import { memberOptions } from "@/components/forms/options";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useModel, useOrgMutation } from "@/hooks/use-org";
import { adminApi } from "@/lib/api/endpoints";
import type { AdminUserInput, Me } from "@/lib/api/types";

const schema = z.object({
  username: z.string().min(2).max(150).regex(/^[\w.@+-]+$/),
  password: z.string(),
  first_name: z.string().max(150),
  last_name: z.string().max(150),
  email: z.union([z.literal(""), z.email()]),
  role: z.enum(["admin", "editor", "viewer"]),
  member: z.string(),
  position: z.string().max(200),
  phone: z.string().max(50),
  telegram: z.string().max(100),
  address: z.string().max(300),
  note: z.string().max(2000),
  is_active: z.boolean(),
});
type Values = z.infer<typeof schema>;

/** Foydalanuvchilar (faqat admin): rol, xodim bilan bog'lash, aloqa ma'lumotlari. */
export function UsersTab() {
  const t = useTranslations();
  const locale = useLocale() as keyof typeof DATE_LOCALES;
  const model = useModel();
  const users = useQuery({ queryKey: ["admin", "users"], queryFn: adminApi.users.list });
  const [edit, setEdit] = useState<Me | null | undefined>(undefined);

  return (
    <>
      <div className="mb-3 flex items-center">
        <p className="flex-1 text-sm text-muted-foreground">{t("settings.usersHint")}</p>
        <Button onClick={() => setEdit(null)}><Plus className="size-4" />{t("settings.newUser")}</Button>
      </div>
      <Card className="gap-0 overflow-hidden p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("settings.user")}</TableHead>
              <TableHead>{t("settings.role")}</TableHead>
              <TableHead>{t("settings.linkedMember")}</TableHead>
              <TableHead>{t("settings.contacts")}</TableHead>
              <TableHead>{t("settings.lastLogin")}</TableHead>
              <TableHead className="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.data?.map((u) => (
              <TableRow key={u.id} className={u.is_active ? undefined : "opacity-50"}>
                <TableCell><div className="font-medium">{u.full_name || u.username}</div><div className="text-xs text-muted-foreground">@{u.username}{u.position && ` · ${u.position}`}</div></TableCell>
                <TableCell><Badge variant={u.role === "admin" ? "default" : "outline"}>{t(`appRoles.${u.role}`)}</Badge></TableCell>
                <TableCell className="text-muted-foreground">{u.member ? model.member.get(u.member)?.name ?? "—" : "—"}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{[u.email, u.phone, u.telegram].filter(Boolean).join(" · ") || "—"}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {u.last_login ? formatDistanceToNow(new Date(u.last_login), { addSuffix: true, locale: DATE_LOCALES[locale] }) : t("settings.never")}
                </TableCell>
                <TableCell><Button variant="ghost" size="icon" className="size-8" onClick={() => setEdit(u)}><Pencil className="size-4" /></Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <UserDialog open={edit !== undefined} onOpenChange={(o) => !o && setEdit(undefined)} user={edit ?? undefined} />
    </>
  );
}

function UserDialog({ open, onOpenChange, user }: { open: boolean; onOpenChange: (o: boolean) => void; user?: Me }) {
  const t = useTranslations();
  const model = useModel();
  const qc = useQueryClient();
  const form = useForm<Values>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (!open) return;
    form.reset({
      username: user?.username ?? "", password: "", first_name: user?.first_name ?? "", last_name: user?.last_name ?? "",
      email: user?.email ?? "", role: user?.role ?? "viewer", member: fromId(user?.member), position: user?.position ?? "",
      phone: user?.phone ?? "", telegram: user?.telegram ?? "", address: user?.address ?? "", note: user?.note ?? "",
      is_active: user?.is_active ?? true,
    });
  }, [open, user, form]);

  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "users"] });
  const save = useOrgMutation(async (v: Values) => {
    const body: AdminUserInput = { ...v, member: toId(v.member), password: v.password || undefined };
    const r = user ? await adminApi.users.update(user.id, body) : await adminApi.users.create(body);
    await refresh();
    return r;
  }, t("settings.saved"));
  const remove = useOrgMutation(async () => {
    if (user) await adminApi.users.remove(user.id);
    await refresh();
  }, t("settings.deleted"));

  return (
    <FormDialog
      wide open={open} onOpenChange={onOpenChange}
      title={user ? user.username : t("settings.newUser")}
      onSubmit={form.handleSubmit(async (v) => {
        if (!user && v.password.length < 8) { form.setError("password", { message: t("settings.passwordRule") }); return; }
        await save.mutateAsync(v);
        onOpenChange(false);
      })}
      submitting={save.isPending}
      onDelete={user ? () => remove.mutateAsync(undefined) : undefined}
    >
      <Row>
        <TextField control={form.control} name="username" label={t("login.username")} />
        <TextField control={form.control} name="password" label={user ? t("settings.newPasswordOptional") : t("login.password")} type="password" />
      </Row>
      <Row>
        <TextField control={form.control} name="first_name" label={t("settings.firstName")} />
        <TextField control={form.control} name="last_name" label={t("settings.lastName")} />
      </Row>
      <Row>
        <SelectField
          control={form.control} name="role" label={t("settings.role")}
          options={(["admin", "editor", "viewer"] as const).map((r) => ({ value: r, label: t(`appRoles.${r}`) }))}
          description={t("settings.roleHint")}
        />
        <SelectField control={form.control} name="member" label={t("settings.linkedMember")} options={memberOptions(model, "—")} />
      </Row>
      <Row>
        <TextField control={form.control} name="position" label={t("settings.position")} />
        <TextField control={form.control} name="email" label={t("forms.member.email")} type="email" />
      </Row>
      <Row>
        <TextField control={form.control} name="phone" label={t("forms.member.phone")} />
        <TextField control={form.control} name="telegram" label={t("forms.member.telegram")} />
      </Row>
      <TextField control={form.control} name="address" label={t("settings.address")} />
      <TextareaField control={form.control} name="note" label={t("settings.note")} rows={2} />
      <CheckboxField control={form.control} name="is_active" label={t("settings.active")} />
    </FormDialog>
  );
}
