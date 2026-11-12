"use client";

import { Mail, Phone, Plus, Search, Send, Users } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { MemberAvatar } from "@/components/common/member-avatar";
import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { RoleGlyph } from "@/components/common/role";
import { MemberDialog } from "@/components/forms/member-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCan, useModel, useScope } from "@/hooks/use-org";
import type { RoleKey } from "@/lib/api/types";
import { ROLE_ORDER } from "@/lib/model";

const norm = (s: string) => s.toLowerCase().replace(/[ʻʼ’‘`´]/g, "'");

/** Xodimlar katalogi: har bir kartada rollar soni, yuklama, aloqa. Bosilsa — Xodim 360°. */
export function Employees() {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const { inScope } = useScope();
  const [query, setQuery] = useState("");
  const [create, setCreate] = useState(false);
  const q = norm(query.trim());
  const list = model.memberOrder.filter(inScope).filter((m) => !q || norm(`${m.name} ${m.role} ${m.trigger} ${m.does}`).includes(q));

  return (
    <Page>
      <PageHeader
        title={t("nav.employees")}
        description={t("employees.description")}
        actions={<>
          <div className="relative w-72"><Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("employees.search")} className="pl-8" /></div>
          {can.edit && <Button onClick={() => setCreate(true)}><Plus className="size-4" />{t("forms.member.new")}</Button>}
        </>}
      />
      <div className="mb-4 flex flex-wrap gap-4 text-xs text-muted-foreground">
        {ROLE_ORDER.map((r) => <span key={r} className="flex items-center gap-1.5"><RoleGlyph role={r} />{t(`roles.${r}`)}</span>)}
      </div>
      {!list.length && <EmptyState icon={Users} title={t("common.nothingFound")} />}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {list.map((m) => {
          const counts = new Map<RoleKey, number>();
          for (const l of model.linksOfMember.get(m.id) ?? []) for (const r of l.roles) counts.set(r, (counts.get(r) ?? 0) + 1);
          const dept = m.department ? model.dept.get(m.department) : undefined;
          const team = m.team ? model.team.get(m.team) : undefined;
          const w = model.workload.find((x) => x.member.id === m.id);
          return (
            <Link key={m.id} href={`/employees/${m.id}`}>
              <Card className="h-full gap-3 p-4 transition-all hover:-translate-y-0.5 hover:border-primary/40">
                <div className="flex items-center gap-3">
                  <MemberAvatar member={m} size={44} />
                  <div className="min-w-0">
                    <div className="truncate font-semibold">{m.name}</div>
                    <div className="truncate text-xs text-muted-foreground">{m.role}</div>
                    <div className="truncate text-xs text-muted-foreground">{[dept?.name, team?.name].filter(Boolean).join(" / ")}</div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1">
                  {ROLE_ORDER.filter((r) => counts.has(r)).map((r) => <RoleGlyph key={r} role={r} count={counts.get(r)} />)}
                  {!counts.size && <span className="text-xs text-muted-foreground">{t("employees.noRoles")}</span>}
                </div>
                <div className="mt-auto flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{t("employees.load", { tasks: w?.tasks ?? 0, authority: (model.authorities.get(m.id) ?? []).length })}</span>
                  {w?.excessive && <span className="rounded-md bg-warning/15 px-1.5 text-warning">{t("workload.excessive")}</span>}
                  <span className="ml-auto flex gap-1.5">
                    {m.phone && <Phone className="size-3.5" />}{m.telegram && <Send className="size-3.5" />}{m.email && <Mail className="size-3.5" />}
                  </span>
                </div>
              </Card>
            </Link>
          );
        })}
      </div>
      <MemberDialog open={create} onOpenChange={setCreate} />
    </Page>
  );
}
