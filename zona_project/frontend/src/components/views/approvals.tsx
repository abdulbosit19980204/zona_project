"use client";

import { format } from "date-fns";
import { Check, GitPullRequestArrow, Inbox, Undo2, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { DATE_LOCALES } from "@/components/common/activity";
import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { ProposeDialog } from "@/components/forms/propose-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApprovals, useCan, useMe, useOrgMutation } from "@/hooks/use-org";
import { approvalsApi } from "@/lib/api/endpoints";
import type { ChangeRequest, ChangeStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<ChangeStatus, string> = {
  pending: "border-warning/50 text-warning",
  approved: "border-success/50 text-success",
  rejected: "border-destructive/50 text-destructive",
  cancelled: "text-muted-foreground",
};

/** Tasdiqlash oqimi: kuzatuvchi taklif beradi, muharrir/admin tasdiqlaydi yoki rad etadi. */
export function Approvals() {
  const t = useTranslations();
  const can = useCan();
  const [status, setStatus] = useState<ChangeStatus | "all">("pending");
  const [mine, setMine] = useState(!can.edit);
  const [propose, setPropose] = useState(false);
  const { data, isLoading } = useApprovals(status, mine);

  return (
    <Page>
      <PageHeader
        title={t("nav.approvals")}
        description={can.edit ? t("approvals.descriptionEdit") : t("approvals.descriptionView")}
        actions={<Button onClick={() => setPropose(true)}><GitPullRequestArrow className="size-4" />{t("approvals.propose")}</Button>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <Tabs value={status} onValueChange={(v) => setStatus(v as ChangeStatus | "all")}>
          <TabsList>
            {(["pending", "approved", "rejected", "cancelled", "all"] as const).map((s) => (
              <TabsTrigger key={s} value={s}>{t(`approvals.status.${s}`)}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Switch checked={mine} onCheckedChange={setMine} />{t("approvals.mine")}
        </label>
      </div>
      {isLoading && <div className="grid gap-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28 rounded-xl" />)}</div>}
      {data && !data.length && <EmptyState icon={Inbox} title={t("approvals.empty")} hint={t("approvals.emptyHint")} />}
      <div className="grid gap-3">
        {data?.map((r) => <RequestCard key={r.id} request={r} />)}
      </div>
      <ProposeDialog open={propose} onOpenChange={setPropose} />
    </Page>
  );
}

function RequestCard({ request: r }: { request: ChangeRequest }) {
  const t = useTranslations();
  const locale = useLocale() as keyof typeof DATE_LOCALES;
  const can = useCan();
  const me = useMe();
  const [note, setNote] = useState("");
  const approve = useOrgMutation(() => approvalsApi.approve(r.id, note), t("approvals.approved"));
  const reject = useOrgMutation(() => approvalsApi.reject(r.id, note), t("approvals.rejected"));
  const cancel = useOrgMutation(() => approvalsApi.cancel(r.id), t("approvals.cancelled"));
  const busy = approve.isPending || reject.isPending || cancel.isPending;
  const fmt = (d: string) => format(new Date(d), "d MMM yyyy, HH:mm", { locale: DATE_LOCALES[locale] });

  return (
    <Card className={cn("gap-3 p-4", r.status === "pending" && "border-l-2 border-l-warning")}>
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{t(`approvals.kinds.${r.kind}`)}</Badge>
            <Badge variant="outline" className={STATUS_TONE[r.status]}>{t(`approvals.status.${r.status}`)}</Badge>
            <span className="text-xs text-muted-foreground">#{r.id}</span>
          </div>
          <div className="mt-2 font-medium">{r.title}</div>
          {r.reason && <p className="mt-1 text-sm text-muted-foreground">“{r.reason}”</p>}
          <div className="mt-2 text-xs text-muted-foreground">
            {t("approvals.by", { name: r.requested_by_name || "—" })} · {fmt(r.created_at)}
            {r.decided_at && <> · {t("approvals.decidedBy", { name: r.decided_by_name || "—" })} · {fmt(r.decided_at)}</>}
          </div>
          {r.decision_note && <p className="mt-1 text-xs">{t("approvals.note")}: {r.decision_note}</p>}
        </div>
        {r.status === "pending" && me && r.requested_by === me.id && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => cancel.mutate(undefined)}><Undo2 className="size-4" />{t("approvals.cancel")}</Button>
        )}
      </div>
      {r.status === "pending" && can.edit && (
        <div className="flex flex-wrap items-center gap-2 border-t pt-3">
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("approvals.notePlaceholder")} className="h-8 min-w-60 flex-1" />
          <Button size="sm" disabled={busy} onClick={() => approve.mutate(undefined)}><Check className="size-4" />{t("approvals.approve")}</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => reject.mutate(undefined)}><X className="size-4" />{t("approvals.reject")}</Button>
        </div>
      )}
    </Card>
  );
}
