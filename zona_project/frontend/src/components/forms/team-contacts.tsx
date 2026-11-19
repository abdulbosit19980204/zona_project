"use client";

import { Plus, Trash2, UsersRound } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ContactLinks } from "@/components/common/contacts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCan, useOrgMutation } from "@/hooks/use-org";
import { orgApi } from "@/lib/api/endpoints";
import type { Member, TeamContact } from "@/lib/api/types";

const EMPTY = { name: "", role: "", telegram: "", phone: "" };

/**
 * Jamoa a'zolari (kontaktlar). Jamoaga biriktirilgan ishlar jamoaning o'zida qoladi — a'zolar alohida xodim
 * emas, hisobot va yuklamada bo'linmaydi; ular vaziyatga qarab ishni o'zaro bo'lishadi. Support bot ularni
 * Telegram orqali taniydi. O'zgarish darhol saqlanadi.
 */
export function TeamContacts({ member }: { member: Member }) {
  const t = useTranslations("teamContacts");
  const can = useCan();
  const [draft, setDraft] = useState(EMPTY);
  const contacts: TeamContact[] = member.contacts ?? [];

  const add = useOrgMutation(
    () => orgApi.teamContacts.create({ ...draft, member: member.id }),
    t("added"),
  );
  const remove = useOrgMutation((id: number) => orgApi.teamContacts.remove(id), t("removed"));

  return (
    <div className="grid gap-2 rounded-xl border p-3">
      <div className="flex items-center gap-2 text-sm font-medium"><UsersRound className="size-4" />{t("title")}</div>
      <p className="text-xs text-muted-foreground">{t("hint")}</p>
      {contacts.length === 0 && <p className="text-xs text-muted-foreground">{t("empty")}</p>}
      {contacts.map((c) => (
        <div key={c.id} className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 px-2.5 py-1.5">
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{c.name}{c.role && <span className="ml-1.5 font-normal text-muted-foreground">· {c.role}</span>}</div>
            <ContactLinks contact={{ phone: c.phone, telegram: c.telegram, email: "" }} />
          </div>
          {c.telegram_id && <span className="text-[11px] text-success">{t("linked")}</span>}
          {can.edit && (
            <Button type="button" size="icon" variant="ghost" aria-label={t("remove")} disabled={remove.isPending}
              onClick={() => remove.mutate(c.id)}>
              <Trash2 className="size-4 text-destructive" />
            </Button>
          )}
        </div>
      ))}
      {can.edit && (
        <div className="grid gap-2 sm:grid-cols-[1.2fr_1fr_1fr_1fr_auto]">
          <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder={t("name")} />
          <Input value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value })} placeholder={t("role")} />
          <Input value={draft.telegram} onChange={(e) => setDraft({ ...draft, telegram: e.target.value })} placeholder="@username" />
          <Input value={draft.phone} onChange={(e) => setDraft({ ...draft, phone: e.target.value })} placeholder="+998…" />
          <Button type="button" variant="outline" disabled={draft.name.trim().length < 2 || add.isPending}
            onClick={() => add.mutate(undefined, { onSuccess: () => setDraft(EMPTY) })}>
            <Plus className="size-4" />{t("add")}
          </Button>
        </div>
      )}
    </div>
  );
}
