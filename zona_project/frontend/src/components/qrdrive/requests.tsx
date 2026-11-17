"use client";

import { Ban, Check, Link2, RotateCcw, UserPlus, X } from "lucide-react";
import { useState } from "react";

import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useQr, useQrAction } from "@/hooks/use-qrdrive";
import { qrApi, type QrEmployee, type TgAccount } from "@/lib/api/qrdrive";

import { FormRow, QrGuard, fmtDate } from "./common";
import { EmpBadge } from "./employees";
import { useQt } from "./i18n";

export function QrRequests() {
  const t = useQt();
  const [tab, setTab] = useState("pending");
  const q = useQr<TgAccount[]>(["requests", tab], "requests", { status: tab }, { refetchInterval: 20_000 });
  const employees = useQr<QrEmployee[]>(["employees"], "employees");
  const [approve, setApprove] = useState<TgAccount | null>(null);
  const [attach, setAttach] = useState<TgAccount | null>(null);
  const [form, setForm] = useState({ full_name: "", department: "", position: "", phone: "" });
  const [empId, setEmpId] = useState("");
  const [replace, setReplace] = useState(true);
  const doApprove = useQrAction(async () => qrApi.post(`requests/${approve!.id}/approve`, form), t("approved"));
  const doAttach = useQrAction(async () => qrApi.post(`requests/${attach!.id}/attach`, { employee_id: Number(empId), replace }), t("approved"));
  const reject = useQrAction(async (v: { id: number; block: boolean }) => qrApi.post(`requests/${v.id}/reject`, { block: v.block }), t("saved"));
  const reopen = useQrAction(async (id: number) => qrApi.post(`requests/${id}/reopen`), t("saved"));

  return (
    <Page>
      <PageHeader title={t("reqTitle")} description={t("reqDesc")} />
      <Tabs value={tab} onValueChange={setTab} className="mb-4">
        <TabsList>
          <TabsTrigger value="pending">{t("st_pending")}</TabsTrigger>
          <TabsTrigger value="rejected,blocked">{t("showRejected")}</TabsTrigger>
        </TabsList>
      </Tabs>
      <QrGuard query={q}>
        {!q.data?.length ? <EmptyState icon={UserPlus} title={t("reqEmpty")} /> : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {q.data.map((a) => (
              <Card key={a.id} className="gap-3 p-4">
                <div className="flex items-start gap-3">
                  <div className="grid size-10 shrink-0 place-items-center rounded-full bg-primary/10 font-semibold text-primary">
                    {(a.first_name || a.username || "?").slice(0, 1).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{a.display}</div>
                    <div className="text-xs text-muted-foreground">{a.username ? `@${a.username} · ` : ""}{t("tgId")}: {a.telegram_id}</div>
                    <div className="text-xs text-muted-foreground">{t("firstSeen")}: {fmtDate(a.first_seen)}</div>
                  </div>
                  {tab !== "pending" && <EmpBadge status={a.status} />}
                </div>
                {tab === "pending" ? (
                  <div className="flex flex-wrap gap-1.5">
                    <Button size="sm" onClick={() => { setForm({ full_name: `${a.first_name} ${a.last_name}`.trim(), department: "", position: "", phone: "" }); setApprove(a); }}>
                      <Check className="size-4" />{t("approveNew")}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => { setEmpId(""); setAttach(a); }}><Link2 className="size-4" />{t("attachExisting")}</Button>
                    <Button size="sm" variant="ghost" onClick={() => reject.mutate({ id: a.id, block: false })}><X className="size-4" />{t("reject")}</Button>
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => reject.mutate({ id: a.id, block: true })}><Ban className="size-4" />{t("rejectBlock")}</Button>
                  </div>
                ) : (
                  <Button size="sm" variant="outline" className="w-fit" onClick={() => reopen.mutate(a.id)}><RotateCcw className="size-4" />{t("reopen")}</Button>
                )}
              </Card>
            ))}
          </div>
        )}
      </QrGuard>

      <Dialog open={!!approve} onOpenChange={(v) => !v && setApprove(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>{t("approveNew")}</DialogTitle></DialogHeader>
          <div className="grid gap-3">
            <FormRow label={t("fullName")}><Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} autoFocus /></FormRow>
            <FormRow label={t("department")}><Input value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} /></FormRow>
            <FormRow label={t("position")}><Input value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} /></FormRow>
            <FormRow label={t("phone")}><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></FormRow>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApprove(null)}>{t("cancel")}</Button>
            <Button disabled={!form.full_name.trim() || doApprove.isPending} onClick={() => doApprove.mutate(undefined, { onSuccess: () => setApprove(null) })}>{t("confirm")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!attach} onOpenChange={(v) => !v && setAttach(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>{t("attachExisting")}</DialogTitle></DialogHeader>
          <Select value={empId} onValueChange={setEmpId}>
            <SelectTrigger><SelectValue placeholder={t("pickEmployee")} /></SelectTrigger>
            <SelectContent>
              {employees.data?.filter((e) => e.status !== "archived").map((e) => (
                <SelectItem key={e.id} value={String(e.id)}>{e.full_name}{e.department ? ` · ${e.department}` : ""}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Label className="flex items-center gap-2 text-sm"><Checkbox checked={replace} onCheckedChange={(v) => setReplace(!!v)} />{t("replaceOld")}</Label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAttach(null)}>{t("cancel")}</Button>
            <Button disabled={!empId || doAttach.isPending} onClick={() => doAttach.mutate(undefined, { onSuccess: () => setAttach(null) })}>{t("confirm")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Page>
  );
}
