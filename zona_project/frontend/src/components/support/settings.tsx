"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, History, LogOut, Plus, Save, Send, ShieldCheck, Trash2, Users, Wifi } from "lucide-react";
import { useState } from "react";

import { Page, PageHeader, SectionTitle } from "@/components/common/page";
import { ConfirmDialog, FormRow } from "@/components/qrdrive/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

import { supportApi, type HistoryJob, type Mode, type SupportBot, type SupportGroup, type SupportSettings } from "./api";
import { fmtDate, ModeBadge, useSupportMutation } from "./common";
import { useSt, type ST } from "./i18n";

const MODES: Mode[] = ["collect", "shadow", "live", "off"];

/** Botlar, guruhlar, umumiy sozlamalar va bot taniydigan xodimlar (faqat administrator). */
export function SupportSettingsPage() {
  const t = useSt();
  return (
    <Page>
      <PageHeader title={t("setTitle")} description={t("setDesc")} />
      <div className="grid gap-6">
        <BotsSection t={t} />
        <GroupsSection t={t} />
        <GeneralSection t={t} />
        <HistorySection t={t} />
        <StaffSection t={t} />
      </div>
    </Page>
  );
}

/* ---------------------------------------------------------------- botlar */
function BotsSection({ t }: { t: ST }) {
  const bots = useQuery({ queryKey: ["support", "bots"], queryFn: supportApi.bots });
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("Support bot");
  const [token, setToken] = useState("");
  const create = useSupportMutation(() => supportApi.createBot({ name, token, mode: "shadow", enabled: true }), t("saved"));
  return (
    <section>
      <SectionTitle actions={<Button size="sm" onClick={() => setAdding(!adding)}><Plus className="size-4" />{t("addBot")}</Button>}>
        <span className="inline-flex items-center gap-1.5"><Bot className="size-4" />{t("bots")}</span>
      </SectionTitle>
      <p className="mb-3 text-xs text-muted-foreground">{t("privacyWarn")}</p>
      {adding && (
        <Card className="mb-3 gap-3 p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <FormRow label={t("botName")}><Input value={name} onChange={(e) => setName(e.target.value)} /></FormRow>
            <FormRow label={t("token")} hint={t("tokenHint")}>
              <Input value={token} onChange={(e) => setToken(e.target.value)} type="password" autoComplete="off" placeholder="123456:ABC…" />
            </FormRow>
          </div>
          <Button className="justify-self-start" disabled={!token.includes(":") || create.isPending}
            onClick={() => create.mutate(undefined, { onSuccess: () => { setAdding(false); setToken(""); } })}>
            <Save className="size-4" />{t("save")}
          </Button>
        </Card>
      )}
      {bots.isLoading && <Skeleton className="h-32" />}
      <div className="grid gap-3">{bots.data?.map((b) => <BotCard key={`${b.id}-${b.updated_at}`} b={b} t={t} />)}</div>
    </section>
  );
}

function BotCard({ b, t }: { b: SupportBot; t: ST }) {
  const [f, setF] = useState({ name: b.name, mode: b.mode, enabled: b.enabled, admin_chat_id: b.admin_chat_id ? String(b.admin_chat_id) : "", welcome: b.welcome, token: "" });
  const [confirm, setConfirm] = useState(false);
  const save = useSupportMutation(() => supportApi.updateBot(b.id, {
    name: f.name, mode: f.mode, enabled: f.enabled, welcome: f.welcome,
    admin_chat_id: f.admin_chat_id.trim() ? Number(f.admin_chat_id) : null, ...(f.token ? { token: f.token } : {}),
  }), t("saved"));
  const check = useSupportMutation(() => supportApi.checkBot(b.id), (r) => (r.ok ? t("checkOk", { u: r.username ?? "" }) : r.error ?? ""));
  const remove = useSupportMutation(() => supportApi.deleteBot(b.id));

  return (
    <Card className="gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`size-2.5 rounded-full ${b.enabled && !b.last_error ? "bg-success" : "bg-warning"}`} />
        <span className="font-semibold">{b.name}</span>
        {b.username && <a className="text-sm text-primary hover:underline" href={`https://t.me/${b.username}`} target="_blank" rel="noreferrer">@{b.username}</a>}
        <ModeBadge mode={b.mode} t={t} />
        <span className="font-mono text-xs text-muted-foreground">{b.token_masked}</span>
        <span className="text-xs text-muted-foreground">· {t("groups")}: {b.groups_count}</span>
        {b.last_ok_at && <span className="text-xs text-muted-foreground">· {t("lastOk")}: {fmtDate(b.last_ok_at)}</span>}
      </div>
      {b.last_error && <p className="rounded-md bg-warning/10 p-2 text-xs text-warning">{b.last_error}</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        <FormRow label={t("botName")}><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></FormRow>
        <FormRow label={t("mode")} hint={`${t("modeHint2")} ${t("modeHint")}`}>
          <Select value={f.mode} onValueChange={(v) => setF({ ...f, mode: v as Mode })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{MODES.map((m) => <SelectItem key={m} value={m}>{t(`mode_${m}`)}</SelectItem>)}</SelectContent>
          </Select>
        </FormRow>
        <FormRow label={t("adminChat")} hint={t("adminChatHint")}>
          <Input value={f.admin_chat_id} onChange={(e) => setF({ ...f, admin_chat_id: e.target.value.replace(/[^\d-]/g, "") })} />
        </FormRow>
        <FormRow label={t("newToken")} hint={t("tokenHint")}>
          <Input value={f.token} onChange={(e) => setF({ ...f, token: e.target.value })} type="password" autoComplete="off" />
        </FormRow>
      </div>
      <FormRow label={t("welcome")}><Textarea rows={2} value={f.welcome} onChange={(e) => setF({ ...f, welcome: e.target.value })} /></FormRow>
      <label className="flex items-center gap-2 text-sm"><Switch checked={f.enabled} onCheckedChange={(v) => setF({ ...f, enabled: v })} />{t("enabled")}</label>
      <div className="flex flex-wrap gap-2">
        <Button disabled={save.isPending} onClick={() => save.mutate(undefined)}><Save className="size-4" />{t("save")}</Button>
        <Button variant="outline" disabled={check.isPending} onClick={() => check.mutate(undefined)}><Wifi className="size-4" />{t("check")}</Button>
        <Button variant="ghost" className="text-destructive" onClick={() => setConfirm(true)}><Trash2 className="size-4" />{t("delete")}</Button>
      </div>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title={t("areYouSure")} description={t("deleteBotConfirm")}
        confirmLabel={t("delete")} destructive pending={remove.isPending}
        onConfirm={() => remove.mutate(undefined, { onSuccess: () => setConfirm(false) })} />
    </Card>
  );
}

/* ---------------------------------------------------------------- guruhlar */
function GroupsSection({ t }: { t: ST }) {
  const groups = useQuery({ queryKey: ["support", "groups"], queryFn: supportApi.groups, refetchInterval: 30_000 });
  const upd = useSupportMutation(({ id, mode }: { id: number; mode: SupportGroup["mode"] }) => supportApi.updateGroup(id, { mode }), t("saved"));
  return (
    <section>
      <SectionTitle><span className="inline-flex items-center gap-1.5"><Users className="size-4" />{t("groups")}</span></SectionTitle>
      <p className="mb-3 text-xs text-muted-foreground">{t("groupsHint")}</p>
      {groups.data && groups.data.length === 0 && <p className="text-sm text-muted-foreground">{t("empty")}</p>}
      {groups.data && groups.data.length > 0 && (
        <Card className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("groups")}</TableHead><TableHead>{t("bots")}</TableHead><TableHead>{t("mode")}</TableHead>
                <TableHead className="text-right">{t("q7")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {groups.data.map((g) => (
                <TableRow key={g.id} className={g.is_active ? "" : "opacity-50"}>
                  <TableCell>
                    <div className="font-medium">{g.title || g.chat_id}</div>
                    <div className="text-xs text-muted-foreground">
                      {g.is_admin ? <span className="text-success"><ShieldCheck className="mr-0.5 inline size-3" />{t("botAdmin")}</span> : t("notAdmin")}
                      {g.last_message_at && ` · ${fmtDate(g.last_message_at)}`}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs">{g.bot_name}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Select value={g.mode} onValueChange={(v) => upd.mutate({ id: g.id, mode: v as SupportGroup["mode"] })}>
                        <SelectTrigger className="h-8 w-40"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {(["inherit", ...MODES] as const).map((m) => <SelectItem key={m} value={m}>{t(`mode_${m}`)}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      {g.mode === "inherit" && <ModeBadge mode={g.effective_mode} t={t} />}
                    </div>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">{g.questions_7d}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </section>
  );
}

/* ---------------------------------------------------------------- umumiy sozlamalar */
type Form = Omit<SupportSettings, "ocr_available" | "ocr_languages" | "ai_ready" | "ai_quota_left" | "has_api_hash">;

function GeneralSection({ t }: { t: ST }) {
  const q = useQuery({ queryKey: ["support", "settings"], queryFn: supportApi.settings });
  if (!q.data) return <Skeleton className="h-64" />;
  return <GeneralForm key={q.dataUpdatedAt} s={q.data} t={t} />;
}

function GeneralForm({ s, t }: { s: SupportSettings; t: ST }) {
  const [f, setF] = useState<Form>({ ...s });
  const [hash, setHash] = useState("");
  const save = useSupportMutation(() => {
    const body: Record<string, unknown> = { ...f };
    delete body.api_hash;
    if (hash) body.api_hash = hash;
    return supportApi.saveSettings(body);
  }, t("saved"));
  const num = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: Number(e.target.value) || 0 });
  const sw = (k: keyof Form, label: string, hint?: string, extra?: React.ReactNode) => (
    <label className="flex items-start gap-2 text-sm">
      <Switch className="mt-0.5" checked={Boolean(f[k])} onCheckedChange={(v) => setF({ ...f, [k]: v })} />
      <span>{label}{hint && <span className="block text-xs text-muted-foreground">{hint}</span>}{extra}</span>
    </label>
  );

  return (
    <section>
      <SectionTitle>{t("general")}</SectionTitle>
      <Card className="gap-4 p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <FormRow label={t("apiId")} hint={t("apiHint")}><Input value={f.api_id} onChange={(e) => setF({ ...f, api_id: e.target.value })} /></FormRow>
          <FormRow label={t("apiHash")} hint={s.has_api_hash ? s.api_hash : t("apiHint")}>
            <Input value={hash} onChange={(e) => setHash(e.target.value)} type="password" autoComplete="off" placeholder={s.api_hash || ""} />
          </FormRow>
        </div>
        {sw("ai_enabled", t("ai"), t("aiHint"), !s.ai_ready && <span className="block text-xs text-warning">{t("aiNotReady")}</span>)}
        <div className="grid gap-3 sm:grid-cols-3">
          <FormRow label={t("aiLimit")} hint={t("aiLeft", { n: s.ai_quota_left })}><Input type="number" value={f.ai_daily_limit} onChange={num("ai_daily_limit")} /></FormRow>
          <FormRow label={t("aiMin")}><Input type="number" value={f.ai_min_confidence} onChange={num("ai_min_confidence")} /></FormRow>
          <FormRow label={t("faqTh")}><Input type="number" value={f.faq_threshold} onChange={num("faq_threshold")} /></FormRow>
          <FormRow label={t("ruleTh")}><Input type="number" value={f.route_threshold} onChange={num("route_threshold")} /></FormRow>
          <FormRow label={t("mediaDays")}><Input type="number" value={f.media_days} onChange={num("media_days")} /></FormRow>
          <FormRow label={t("signature")}><Input value={f.signature} onChange={(e) => setF({ ...f, signature: e.target.value })} /></FormRow>
        </div>
        {sw("learn_from_staff", t("learn"), t("learnHint"))}
        <div className="grid gap-3 rounded-lg border p-3">
          <div className="text-sm font-medium">{t("behavior")}</div>
          <p className="text-xs text-muted-foreground">{t("behaviorHint")}</p>
          {sw("drafts_to_admin", t("t_drafts"))}
          {sw("escalation_ack", t("t_escalation"))}
          {sw("mention_responsible", t("t_mention"))}
          {sw("feedback_buttons", t("t_feedback"))}
          {sw("notify_candidates", t("t_candidates"))}
          {sw("learn_clarifications", t("t_clarify"), t("t_clarifyHint"))}
          {sw("ask_first_prompt", t("t_askFirst"))}
        </div>
        {sw("ocr_enabled", t("ocrOn"), s.ocr_available ? t("ocrLangs", { l: s.ocr_languages }) : undefined,
          !s.ocr_available && <span className="block text-xs text-warning">{t("ocrMissing")}</span>)}
        <Button className="justify-self-start" disabled={save.isPending}
          onClick={() => save.mutate(undefined, { onSuccess: () => setHash("") })}>
          <Save className="size-4" />{t("save")}
        </Button>
      </Card>
    </section>
  );
}

/* ---------------------------------------------------------------- xodimlar */
function StaffSection({ t }: { t: ST }) {
  const q = useQuery({ queryKey: ["support", "staff"], queryFn: supportApi.staff });
  return (
    <section>
      <SectionTitle>{t("staff")}</SectionTitle>
      <p className="mb-3 text-xs text-muted-foreground">{t("staffHint")}</p>
      <Card className="p-0">
        <Table>
          <TableBody>
            {q.data?.map((s) => (
              <TableRow key={`${s.type}-${s.id}`}>
                <TableCell className="font-medium">{s.name}<div className="text-xs font-normal text-muted-foreground">{s.role}</div></TableCell>
                <TableCell className="text-xs">{s.team ? <Badge variant="outline" className="font-normal">{t("team")}: {s.team}</Badge> : null}</TableCell>
                <TableCell className="text-xs">{s.level}</TableCell>
                <TableCell className="text-xs">@{s.telegram.replace(/^@/, "")}{s.linked && <span className="ml-1 text-success">· {t("linked")}</span>}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{s.phone}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </section>
  );
}

/* ---------------------------------------------------------------- guruh tarixi (MTProto, faqat o'qish) */
function HistorySection({ t }: { t: ST }) {
  const st = useQuery({ queryKey: ["support", "settings"], queryFn: supportApi.settings });
  const groups = useQuery({ queryKey: ["support", "groups"], queryFn: supportApi.groups });
  const jobs = useQuery({
    queryKey: ["support", "history"], queryFn: supportApi.historyJobs,
    refetchInterval: (q) => ((q.state.data ?? []).some((j: HistoryJob) => j.status === "queued" || j.status === "running") ? 4000 : 30_000),
  });
  const s = st.data;
  const [phone, setPhone] = useState("+998");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [group, setGroup] = useState("");
  const [days, setDays] = useState<number | null>(null);
  const [photos, setPhotos] = useState<boolean | null>(null);
  const send = useSupportMutation(() => supportApi.mtSendCode(phone), (r) => (r.need_password ? t("mtNeedPassword") : t("mtCodeSent", { p: r.mtproto_phone })));
  const sign = useSupportMutation(() => supportApi.mtSignIn(code, password),
    (r) => (r.need_password ? t("mtNeedPassword") : t("mtConnected", { u: r.mtproto_user })));
  const out = useSupportMutation(() => supportApi.mtLogout(), t("saved"));
  const start = useSupportMutation(() => supportApi.startHistory(Number(group), days ?? s?.history_days ?? 30, photos ?? s?.history_photos ?? true), t("saved"));
  if (!s) return <Skeleton className="h-40" />;
  const ready = !!s.api_id && s.has_api_hash;

  return (
    <section>
      <SectionTitle><span className="inline-flex items-center gap-1.5"><History className="size-4" />{t("history")}</span></SectionTitle>
      <p className="mb-3 text-xs text-muted-foreground">{t("historyHint")}</p>
      <Card className="gap-4 p-4">
        {!s.mtproto_available && <p className="text-sm text-warning">{t("mtNotInstalled")}</p>}
        {!ready && <p className="text-sm text-warning">{t("mtNeedApi")}</p>}
        {s.mtproto_connected ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="size-2 rounded-full bg-success" />{t("mtConnected", { u: s.mtproto_user })}
            <Button size="sm" variant="ghost" className="text-destructive" disabled={out.isPending} onClick={() => out.mutate(undefined)}>
              <LogOut className="size-4" />{t("mtLogout")}
            </Button>
          </div>
        ) : ready && s.mtproto_available && (
          <div className="grid gap-3">
            <p className="text-sm text-muted-foreground">{t("mtNotConnected")}</p>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
              <FormRow label={t("mtPhone")}><Input value={phone} onChange={(e) => setPhone(e.target.value)} /></FormRow>
              <Button variant="outline" className="self-end" disabled={phone.length < 10 || send.isPending} onClick={() => send.mutate(undefined)}>
                <Send className="size-4" />{t("mtSendCode")}
              </Button>
            </div>
            {s.mtproto_pending && (
              <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
                <FormRow label={t("mtCode")} hint={t("mtCodeSent", { p: s.mtproto_phone })}>
                  <Input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" />
                </FormRow>
                <FormRow label={t("mtPassword")} hint={s.mtproto_need_password ? t("mtNeedPassword") : undefined}>
                  <Input value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="off" />
                </FormRow>
                <Button className="self-end" disabled={(!code && !password) || sign.isPending} onClick={() => sign.mutate(undefined)}>{t("mtSignIn")}</Button>
              </div>
            )}
          </div>
        )}

        {s.mtproto_connected && (
          <div className="grid gap-3 sm:grid-cols-[2fr_1fr_auto_auto]">
            <FormRow label={t("histGroup")}>
              <Select value={group} onValueChange={setGroup}>
                <SelectTrigger><SelectValue placeholder={t("histGroup")} /></SelectTrigger>
                <SelectContent>{(groups.data ?? []).map((g) => <SelectItem key={g.id} value={String(g.id)}>{g.title || g.chat_id}</SelectItem>)}</SelectContent>
              </Select>
            </FormRow>
            <FormRow label={t("histDays")}>
              <Input type="number" min={1} max={365} value={days ?? s.history_days} onChange={(e) => setDays(Number(e.target.value) || 1)} />
            </FormRow>
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
              <Switch checked={photos ?? s.history_photos} onCheckedChange={setPhotos} />{t("histPhotos")}
            </label>
            <Button className="self-end" disabled={!group || start.isPending} onClick={() => start.mutate(undefined)}>
              <History className="size-4" />{t("histStart")}
            </Button>
          </div>
        )}

        {(jobs.data ?? []).length > 0 && (
          <div className="grid gap-2">
            <div className="text-sm font-medium">{t("histJobs")}</div>
            {jobs.data!.map((j) => (
              <div key={j.id} className="grid gap-1 rounded-lg border p-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className={j.status === "done" ? "border-success/50 text-success" : j.status === "failed" ? "border-destructive/50 text-destructive" : "border-warning/50 text-warning"}>
                    {t(`j_${j.status}` as never)}
                  </Badge>
                  <span className="font-medium">{j.group_title}</span>
                  <span className="text-muted-foreground">· {j.days} kun · {fmtDate(j.created_at)} · {j.created_by}</span>
                </div>
                <div className="text-muted-foreground">
                  {[["messages", "jMsgs"], ["photos", "jPhotos"], ["questions", "jQuestions"], ["staff_answers", "jAnswers"],
                    ["clarifications", "jClar"], ["candidates", "jCand"]]
                    .filter(([k]) => j.progress[k as keyof HistoryJob["progress"]] != null)
                    .map(([k, l]) => `${j.progress[k as keyof HistoryJob["progress"]]} ${t(l as never)}`).join(" · ")}
                  {!!j.progress.flood_wait && ` · ${t("jWait", { n: j.progress.flood_wait })}`}
                </div>
                {j.error && <div className="text-destructive">{j.error}</div>}
              </div>
            ))}
          </div>
        )}
      </Card>
    </section>
  );
}
