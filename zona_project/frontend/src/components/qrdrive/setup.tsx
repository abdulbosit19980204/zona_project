"use client";

import { Bot, Check, HardDrive, PartyPopper, Send, ShieldCheck, UserPlus, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Page, PageHeader } from "@/components/common/page";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useQr, useQrAction } from "@/hooks/use-qrdrive";
import { qrApi, type QrSettings, type QrStorage, type SetupStatus } from "@/lib/api/qrdrive";
import { cn } from "@/lib/utils";

import { FormRow, QrGuard } from "./common";
import { useQt, type QKey } from "./i18n";
import { BotTestResult, type BotCheck } from "./settings";
import { StorageDialog, type Draft } from "./storages";

const STEPS = [
  { key: "admin", icon: ShieldCheck, title: "s1", desc: "s1d" },
  { key: "bot", icon: Bot, title: "s2", desc: "s2d" },
  { key: "storage", icon: HardDrive, title: "s3", desc: "s3d" },
  { key: "employees", icon: Users, title: "s4", desc: "s4d" },
  { key: "test", icon: Send, title: "s5", desc: "s5d" },
] as const;

/** Sozlash ustasi: texnik bo'lmagan admin 5 qadamda tizimni ishga tushiradi. */
export function QrSetup() {
  const t = useQt();
  const q = useQr<SetupStatus>(["setup"], "setup", undefined, { refetchInterval: 10_000 });
  const [step, setStep] = useState(1);
  const [token, setToken] = useState("");
  const [check, setCheck] = useState<BotCheck | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [emp, setEmp] = useState({ full_name: "", department: "" });
  const [chat, setChat] = useState("");
  const test = useQrAction(async () => (await qrApi.post<BotCheck>("settings/bot/test", { token })).data);
  const saveToken = useQrAction(async () => (await qrApi.patch<QrSettings>("settings", { bot_token: token })).data, t("saved"));
  const addEmp = useQrAction(async () => qrApi.post("employees", emp), t("saved"));
  const sendTest = useQrAction(async () => qrApi.post("settings/test-send", { chat_id: Number(chat) }), t("testOk"));
  const finish = useQrAction(async () => qrApi.post("setup/complete"), t("finished"));
  const storages = useQr<QrStorage[]>(["storages"], "storages");
  const s = q.data;

  return (
    <Page>
      <PageHeader title={t("setupTitle")} description={t("setupDesc")} />
      <QrGuard query={q}>
        {s && (
          <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
            <ol className="grid content-start gap-1">
              {STEPS.map((st, i) => {
                const done = s.steps[st.key];
                return (
                  <li key={st.key}>
                    <button onClick={() => setStep(i + 1)}
                      className={cn("flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm hover:bg-muted", step === i + 1 && "bg-muted font-medium")}>
                      <span className={cn("grid size-7 shrink-0 place-items-center rounded-full border text-xs",
                        done ? "border-success bg-success/15 text-success" : step === i + 1 ? "border-primary text-primary" : "text-muted-foreground")}>
                        {done ? <Check className="size-4" /> : i + 1}
                      </span>
                      {t(st.title as QKey)}
                    </button>
                  </li>
                );
              })}
            </ol>

            <Card className="gap-4 p-6">
              {(() => {
                const st = STEPS[step - 1];
                const Icon = st.icon;
                return (
                  <div className="flex items-start gap-3">
                    <span className="grid size-10 place-items-center rounded-xl bg-primary/10 text-primary"><Icon className="size-5" /></span>
                    <div>
                      <div className="text-lg font-semibold">{step}. {t(st.title as QKey)}
                        {s.steps[st.key] && <span className="ml-2 text-sm font-normal text-success">✓ {t("stepDone")}</span>}</div>
                      <p className="text-sm text-muted-foreground">{t(st.desc as QKey)}</p>
                    </div>
                  </div>
                );
              })()}

              {step === 2 && (
                <div className="grid max-w-xl gap-3">
                  <FormRow label={t("botToken")} help={t("botTokenHint")} hint={s.bot_username ? t("botConnected", { name: s.bot_username }) : undefined}>
                    <div className="flex gap-2">
                      <Input type="password" autoComplete="new-password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="123456789:AA…" />
                      <Button variant="outline" disabled={!token || test.isPending} onClick={() => test.mutate(undefined, { onSuccess: setCheck })}>{t("botTest")}</Button>
                    </div>
                  </FormRow>
                  <BotTestResult r={check} />
                  <Button className="w-fit" disabled={!check?.ok || saveToken.isPending}
                    onClick={() => saveToken.mutate(undefined, { onSuccess: () => { setToken(""); setStep(3); } })}>{t("save")}</Button>
                </div>
              )}

              {step === 3 && !!storages.data?.length && (
                <div className="grid gap-2">
                  {storages.data.some((x) => x.last_error === "not_configured") && <p className="text-sm text-primary">{t("defaultStorage")}</p>}
                  {storages.data.map((x) => (
                    <div key={x.id} className="flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2 text-sm">
                      <span className="font-medium">{x.name}</span>
                      <span className="text-xs text-muted-foreground">{x.kind_label}</span>
                      <span className={x.status === "ok" ? "text-success" : "text-warning"}>{t(`status_${x.status}` as QKey)}</span>
                      <Button size="sm" variant={x.status === "ok" ? "outline" : "default"} className="ml-auto"
                        onClick={() => setDraft({ id: x.id, name: x.name, kind: x.kind, base_folder: x.base_folder, link_mode: x.link_mode,
                          is_fallback: x.is_fallback, enabled: x.enabled, is_primary: x.is_primary, config: { ...x.config } })}>
                        {x.status === "ok" ? t("edit") : t("enterCredentials")}
                      </Button>
                    </div>
                  ))}
                </div>
              )}

              {step === 3 && (
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => setDraft({ name: "", kind: "synology", base_folder: "/Kadrlar", link_mode: "provider", is_fallback: false, enabled: true, is_primary: true, config: {} })}>
                    <HardDrive className="size-4" />{t("addStorage")}
                  </Button>
                  <Button variant="outline" asChild><Link href="/qr/storages">{t("stoTitle")}</Link></Button>
                </div>
              )}

              {step === 4 && (
                <div className="grid max-w-xl gap-3">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <FormRow label={t("fullName")}><Input value={emp.full_name} onChange={(e) => setEmp({ ...emp, full_name: e.target.value })} /></FormRow>
                    <FormRow label={t("department")}><Input value={emp.department} onChange={(e) => setEmp({ ...emp, department: e.target.value })} /></FormRow>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button disabled={!emp.full_name.trim() || addEmp.isPending} onClick={() => addEmp.mutate(undefined, { onSuccess: () => setEmp({ full_name: "", department: "" }) })}>
                      <UserPlus className="size-4" />{t("addFirstEmployee")}
                    </Button>
                    <Button variant="outline" asChild><Link href="/qr/employees">{t("goEmployees")}</Link></Button>
                  </div>
                </div>
              )}

              {step === 5 && (
                <div className="grid max-w-xl gap-3">
                  {s.bot_username && <a className="text-sm text-primary hover:underline" href={`https://t.me/${s.bot_username}`} target="_blank" rel="noreferrer">t.me/{s.bot_username}</a>}
                  <FormRow label={t("chatId")}>
                    <div className="flex gap-2">
                      <Input value={chat} onChange={(e) => setChat(e.target.value.replace(/[^\d-]/g, ""))} placeholder="123456789" />
                      <Button disabled={!chat || sendTest.isPending} onClick={() => sendTest.mutate()}><Send className="size-4" />{t("sendTest")}</Button>
                    </div>
                  </FormRow>
                </div>
              )}

              <div className="mt-2 flex flex-wrap gap-2 border-t pt-4">
                {step > 1 && <Button variant="outline" onClick={() => setStep(step - 1)}>{t("back")}</Button>}
                {step < 5 ? <Button variant="outline" onClick={() => setStep(step + 1)}>{t("next")}</Button> : (
                  <Button disabled={finish.isPending || s.done} onClick={() => finish.mutate()}><PartyPopper className="size-4" />{s.done ? t("finished") : t("finish")}</Button>
                )}
              </div>
            </Card>
          </div>
        )}
      </QrGuard>
      <StorageDialog draft={draft} setDraft={setDraft} onSaved={() => setStep(4)} />
    </Page>
  );
}
