"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, History, Images, Link2, ListTodo, LogOut, MessageSquareText, Plus, Save, Search, Send, Settings2, ShieldCheck, Trash2, Users, Wifi, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog, FormRow } from "@/components/qrdrive/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { supportApi, type HistoryJob, type Mode, type SupportBot, type SupportGroup, type StaffRow, type SupportSettings, type TgUserInfo } from "./api";
import { DataTable, type Column } from "./data-table";
import { fmtDate, ModeBadge, SearchPicker, Segmented, useSupportMutation } from "./common";
import { useSt, type SKey, type ST } from "./i18n";
import { SettingRow, SupportShell } from "./shell";
import { TasksPanel } from "./tasks-panel";

const MODES: Mode[] = ["collect", "shadow", "live", "off"];

/** Botlar, guruhlar, umumiy sozlamalar va bot taniydigan xodimlar (faqat administrator). */
const SETTING_TABS: { key: string; label: SKey; hint: SKey; icon: LucideIcon }[] = [
  { key: "bots", label: "stBots", hint: "stBotsHint", icon: Bot },
  { key: "groups", label: "stGroups", hint: "stGroupsHint", icon: Users },
  { key: "answering", label: "stAnswering", hint: "stAnsweringHint", icon: MessageSquareText },
  { key: "images", label: "stImages", hint: "stImagesHint", icon: Images },
  { key: "history", label: "stHistory", hint: "stHistoryHint", icon: History },
  { key: "tasks", label: "stTasks", hint: "stTasksHint", icon: ListTodo },
  { key: "people", label: "stPeople", hint: "stPeopleHint", icon: Link2 },
  { key: "general", label: "stGeneral", hint: "stGeneralHint", icon: Settings2 },
];

export function SupportSettingsPage() {
  const t = useSt();
  const [tab, setTab] = useState("bots");
  const cur = SETTING_TABS.find((x) => x.key === tab)!;
  return (
    <SupportShell title={t("setTitle")} description={t("setDesc")}>
      <div className="grid gap-5 lg:grid-cols-[230px_1fr]">
        <nav className="-mx-1 flex gap-1 overflow-x-auto px-1 lg:sticky lg:top-0 lg:mx-0 lg:flex-col lg:self-start lg:overflow-visible lg:px-0">
          {SETTING_TABS.map((x) => {
            const on = x.key === tab;
            return (
              <button key={x.key} type="button" onClick={() => setTab(x.key)}
                className={cn("flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                  on ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
                <x.icon className="size-4 shrink-0" />{t(x.label)}
              </button>
            );
          })}
        </nav>
        <div className="min-w-0">
          <div className="mb-4 flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-lg bg-primary/10 text-primary"><cur.icon className="size-4" /></span>
            <div className="min-w-0">
              <h2 className="font-semibold leading-tight">{t(cur.label)}</h2>
              <p className="text-xs text-muted-foreground">{t(cur.hint)}</p>
            </div>
          </div>
          {tab === "bots" && <BotsSection t={t} />}
          {tab === "groups" && <GroupsSection t={t} />}
          {tab === "answering" && <SettingsForm t={t} part="answering" />}
          {tab === "images" && <SettingsForm t={t} part="images" />}
          {tab === "history" && <HistorySection t={t} />}
          {tab === "tasks" && <TasksPanel t={t} />}
          {tab === "people" && <div className="grid gap-6"><TgUsersSection t={t} /><StaffSection t={t} /></div>}
          {tab === "general" && <SettingsForm t={t} part="general" />}
        </div>
      </div>
    </SupportShell>
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
      <div className="mb-3 flex items-start gap-3">
        <p className="flex-1 text-xs text-muted-foreground">{t("privacyWarn")}</p>
        <Button size="sm" onClick={() => setAdding(!adding)}><Plus className="size-4" />{t("addBot")}</Button>
      </div>
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
          <Segmented size="sm" value={f.mode} onChange={(v) => setF({ ...f, mode: v as Mode })} className="w-full"
            options={MODES.map((m) => ({ value: m, label: t(`mode_${m}`) }))} />
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
    <section className="grid gap-3">
      <p className="text-xs text-muted-foreground">{t("groupsHint")}</p>
      {groups.isLoading && <Skeleton className="h-32" />}
      {groups.data && groups.data.length === 0 && <p className="text-sm text-muted-foreground">{t("empty")}</p>}
      {groups.data?.map((g) => (
        <Card key={g.id} className={cn("gap-3 p-4", !g.is_active && "opacity-60")}>
          <div className="flex flex-wrap items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-muted"><Users className="size-4 text-muted-foreground" /></span>
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium">{g.title || g.chat_id}</div>
              <div className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                {g.is_admin ? <span className="inline-flex items-center gap-0.5 text-success"><ShieldCheck className="size-3" />{t("botAdmin")}</span>
                  : <span className="text-warning">{t("notAdmin")}</span>}
                <span>· {g.bot_name}</span>
                <span>· {t("q7")}: <b className="text-foreground">{g.questions_7d}</b></span>
                {g.last_message_at && <span>· {fmtDate(g.last_message_at)}</span>}
              </div>
            </div>
            {g.mode === "inherit" && <div className="flex items-center gap-1.5 text-xs text-muted-foreground">{t("nowActs")}: <ModeBadge mode={g.effective_mode} t={t} /></div>}
          </div>
          <Segmented size="sm" value={g.mode} className="w-full sm:w-auto"
            onChange={(v) => upd.mutate({ id: g.id, mode: v as SupportGroup["mode"] })}
            options={(["inherit", ...MODES] as const).map((m) => ({ value: m, label: t(`mode_${m}`) }))} />
        </Card>
      ))}
    </section>
  );
}

/* ---------------------------------------------------------------- sozlamalar (javob berish, rasmlar, umumiy) */
type Form = Omit<SupportSettings, "ocr_available" | "ocr_languages" | "ai_ready" | "ai_quota_left" | "has_api_hash">;
type Part = "answering" | "images" | "general";

function SettingsForm({ t, part }: { t: ST; part: Part }) {
  const q = useQuery({ queryKey: ["support", "settings"], queryFn: supportApi.settings });
  if (!q.data) return <Skeleton className="h-64" />;
  return <SettingsFields key={q.dataUpdatedAt} s={q.data} t={t} part={part} />;
}

function SettingsFields({ s, t, part }: { s: SupportSettings; t: ST; part: Part }) {
  const [f, setF] = useState<Form>({ ...s });
  const [hash, setHash] = useState("");
  // kalitlar bosilishi bilan saqlanadi; raqam va matn maydonlari — «Saqlash» tugmasi bilan
  const toggle = useSupportMutation((body: Partial<Form>) => supportApi.saveSettings(body), t("saved"));
  const save = useSupportMutation(() => {
    const body: Record<string, unknown> = { ...f };
    delete body.api_hash;
    if (hash) body.api_hash = hash;
    return supportApi.saveSettings(body);
  }, t("saved"));
  const num = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: Number(e.target.value) || 0 });
  const sw = (k: keyof Form, label: string, hint?: React.ReactNode) => (
    <SettingRow label={label} hint={hint}>
      <Switch checked={Boolean(f[k])} disabled={toggle.isPending}
        onCheckedChange={(v) => { setF({ ...f, [k]: v }); toggle.mutate({ [k]: v } as Partial<Form>); }} />
    </SettingRow>
  );
  const field = (label: string, hint: string | undefined, input: React.ReactNode) => (
    <SettingRow label={label} hint={hint}><div className="w-36 sm:w-44">{input}</div></SettingRow>
  );
  const saveBtn = (
    <Button className="mt-3" disabled={save.isPending} onClick={() => save.mutate(undefined, { onSuccess: () => setHash("") })}>
      <Save className="size-4" />{t("save")}
    </Button>
  );

  if (part === "answering") {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="gap-3 p-4 lg:col-span-2">
          <div>
            <div className="text-sm font-semibold">{t("polTitle")}</div>
            <p className="mt-0.5 text-xs text-muted-foreground">{t("polHint")}</p>
          </div>
          <Segmented value={f.answer_policy ?? "all"} className="w-full sm:w-auto"
            onChange={(v) => { setF({ ...f, answer_policy: v }); toggle.mutate({ answer_policy: v }); }}
            options={(["standard", "kb", "all"] as const).map((v) => ({ value: v, label: t(`pol_${v}` as SKey) }))} />
          <p className="rounded-lg bg-muted/50 p-2.5 text-xs leading-relaxed">{t(`pol_${f.answer_policy ?? "all"}_h` as SKey)}</p>
        </Card>
        <Card className="gap-0 p-4">
          <div className="mb-1 text-sm font-semibold">{t("grpReply")}</div>
          <p className="mb-2 text-xs text-muted-foreground">{t("behaviorHint")}</p>
          {sw("mention_asker", t("t_mentionAsker"), t("t_mentionAskerHint"))}
          {sw("mention_supervisor", t("t_mentionSv"), t("t_mentionSvHint"))}
          {sw("mention_responsible", t("t_mention"))}
          {sw("escalation_ack", t("t_escalation"))}
          {sw("feedback_buttons", t("t_feedback"))}
          {sw("thanks_reaction", t("t_thanks"), t("t_thanksHint"))}
          {sw("confirm_resolution", t("t_confirm"), t("t_confirmHint"))}
          {f.confirm_resolution && field(t("t_confirmAfter"), undefined,
            <Input type="number" min={0} value={f.confirm_after} onChange={num("confirm_after")}
              onBlur={() => toggle.mutate({ confirm_after: f.confirm_after })} />)}
          {sw("ask_first_prompt", t("t_askFirst"))}
          {sw("contact_lookup", t("t_contacts"), t("t_contactsHint"))}
        </Card>
        <Card className="gap-0 p-4">
          <div className="mb-1 text-sm font-semibold">{t("grpLearn")}</div>
          <p className="mb-2 text-xs text-muted-foreground">{t("grpLearnHint")}</p>
          {sw("self_learning", t("t_selfLearn"), t("t_selfLearnHint"))}
          {sw("answer_variety", t("t_variety"), t("t_varietyHint"))}
          {sw("progress_messages", t("t_progress"), t("t_progressHint"))}
          <SettingRow label={t("t_autoLevel")} hint={t("t_autoLevelHint")}>
            <Segmented size="sm" value={f.auto_approve_level}
              onChange={(v) => { setF({ ...f, auto_approve_level: v }); toggle.mutate({ auto_approve_level: v }); }}
              options={(["off", "lead", "l2", "all"] as const).map((v) => ({ value: v, label: t(`lvl_${v}` as SKey) }))} />
          </SettingRow>
          {sw("learn_from_staff", t("learn"), t("learnHint"))}
          {sw("learn_clarifications", t("t_clarify"), t("t_clarifyHint"))}
          {sw("notify_candidates", t("t_candidates"))}
          {sw("drafts_to_admin", t("t_drafts"))}
        </Card>
        <Card className="gap-0 p-4 lg:col-span-2">
          <div className="mb-1 text-sm font-semibold">{t("grpPrecision")}</div>
          {sw("ai_primary", t("t_aiPrimary"), t("t_aiPrimaryHint"))}
          {field(t("aiPrimaryBelow"), t("aiPrimaryBelowHint"), <Input type="number" value={f.ai_primary_below} onChange={num("ai_primary_below")} />)}
          {field(t("faqTh"), t("faqThHint"), <Input type="number" value={f.faq_threshold} onChange={num("faq_threshold")} />)}
          {field(t("albumWindow"), t("albumWindowHint"), <Input type="number" value={f.album_window} onChange={num("album_window")} />)}
          {field(t("mergeWindow"), t("mergeWindowHint"), <Input type="number" min={0} max={60} value={f.merge_window} onChange={num("merge_window")} />)}
          {field(t("ruleTh"), undefined, <Input type="number" value={f.route_threshold} onChange={num("route_threshold")} />)}
          {field(t("workers"), t("workersHint"), <Input type="number" min={1} max={24} value={f.workers} onChange={num("workers")} />)}
          {field(t("signature"), undefined, <Input value={f.signature} onChange={(e) => setF({ ...f, signature: e.target.value })} />)}
          <div>{saveBtn}</div>
        </Card>
      </div>
    );
  }
  if (part === "images") {
    return (
      <Card className="gap-0 p-4">
        {sw("image_match", t("imgMatch"), t("imgMatchHint"))}
        {sw("image_autolabel", t("imgAuto"), t("imgAutoHint"))}
        {sw("ocr_enabled", t("ocrOn"), s.ocr_available ? t("ocrLangs", { l: s.ocr_languages }) : <span className="text-warning">{t("ocrMissing")}</span>)}
        {field(t("imgThreshold"), t("imgThresholdHint"), <Input type="number" min={2} max={20} value={f.image_threshold} onChange={num("image_threshold")} />)}
        {field(t("mediaDays"), t("mediaDaysHint"), <Input type="number" value={f.media_days} onChange={num("media_days")} />)}
        <div>{saveBtn}</div>
      </Card>
    );
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="gap-0 p-4">
        <div className="mb-1 text-sm font-semibold">{t("ai")}</div>
        <p className="mb-2 text-xs text-muted-foreground">{t("aiHint")}</p>
        {sw("ai_enabled", t("ai"), !s.ai_ready ? <span className="text-warning">{t("aiNotReady")}</span> : undefined)}
        {field(t("aiLimit"), t("aiLeft", { n: s.ai_quota_left }), <Input type="number" value={f.ai_daily_limit} onChange={num("ai_daily_limit")} />)}
        {field(t("aiMin"), undefined, <Input type="number" value={f.ai_min_confidence} onChange={num("ai_min_confidence")} />)}
        <div>{saveBtn}</div>
      </Card>
      <Card className="gap-0 p-4">
        <div className="mb-1 text-sm font-semibold">Telegram API</div>
        <p className="mb-2 text-xs text-muted-foreground">{t("apiHint")}</p>
        <FormRow label={t("apiId")}><Input value={f.api_id} onChange={(e) => setF({ ...f, api_id: e.target.value })} /></FormRow>
        <FormRow label={t("apiHash")} hint={s.has_api_hash ? s.api_hash : undefined} className="mt-3">
          <Input value={hash} onChange={(e) => setHash(e.target.value)} type="password" autoComplete="off" placeholder={s.api_hash || ""} />
        </FormRow>
        <div>{saveBtn}</div>
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------- Telegram foydalanuvchilar <-> kontaktlar */
function TgUsersSection({ t }: { t: ST }) {
  const users = useQuery({ queryKey: ["support", "tg-users"], queryFn: () => supportApi.tgUsers() });
  const columns: Column<TgUserInfo>[] = [
    {
      key: "name", header: "Telegram", sort: (u) => (u.name || u.username || "").toLowerCase(),
      cell: (u) => (
        <div className="min-w-44">
          <div className="font-medium">{u.name || "—"}</div>
          <div className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
            {u.username && <span>@{u.username}</span>}
            {u.is_staff && <Badge variant="outline" className="font-normal">{t("staffBadge")}: {u.staff_name}</Badge>}
          </div>
        </div>
      ),
    },
    { key: "person", header: t("tgStaff"), sort: (u) => u.staff_person_name || null, className: "min-w-64", cell: (u) => <TgLinkCell u={u} t={t} /> },
    { key: "sv", header: t("tgSupervisor"), sort: (u) => u.supervisor || null, cell: (u) => <span className="text-sm">{u.supervisor || "—"}</span> },
    { key: "msgs", header: t("anMessages"), align: "right", sort: (u) => u.msg_count ?? 0, cell: (u) => <span className="font-mono text-xs">{u.msg_count ?? 0}</span> },
    { key: "q", header: t("anQuestions"), align: "right", sort: (u) => u.questions, cell: (u) => <span className="font-mono text-xs">{u.questions}</span> },
    { key: "seen", header: t("lastSeen"), align: "right", sort: (u) => u.last_seen, cell: (u) => <span className="whitespace-nowrap text-xs text-muted-foreground">{fmtDate(u.last_seen)}</span> },
  ];
  return (
    <section>
      <h3 className="mb-1 inline-flex items-center gap-1.5 text-sm font-semibold"><Link2 className="size-4" />{t("tgUsers")}</h3>
      <p className="mb-3 text-xs text-muted-foreground">{t("tgUsersHint")}</p>
      <DataTable rows={users.data} loading={users.isLoading} columns={columns} rowKey={(u) => u.id} t={t}
        initialSort={{ key: "seen", dir: "desc" }}
        search={(u) => [u.name, u.username, u.staff_name, u.staff_person_name, u.project, u.supervisor].join(" ")}
        filters={[
          { value: "all", label: t("dtAll"), test: () => true },
          { value: "staff", label: t("dtStaff"), test: (u) => u.is_staff },
          { value: "linked", label: t("dtAgents"), test: (u) => !!u.staff_person },
          { value: "none", label: t("dtUnlinked"), test: (u) => !u.is_staff && !u.staff_person },
        ]} />
    </section>
  );
}

function TgLinkCell({ u, t }: { u: TgUserInfo; t: ST }) {
  const [editing, setEditing] = useState(false);
  const [q, setQ] = useState("");
  const found = useQuery({ queryKey: ["support", "staff-people", q], queryFn: () => supportApi.staffPeople(q), enabled: editing && q.length >= 2 });
  const link = useSupportMutation((id: number | null) => supportApi.linkTgUser(u.id, id), t("saved"));
  if (!editing) {
    return (
      <div className="flex items-center justify-between gap-2">
        {u.staff_person ? (
          <span className="min-w-0 text-sm">{u.staff_person_name}
            <span className="block truncate text-xs text-muted-foreground">{u.staff_person_role} · {u.project}{u.link === "auto" ? ` · ${t("tgAuto")}` : ""}</span>
          </span>
        ) : <span className="text-xs text-muted-foreground">{u.link === "none" ? t("tgNone") : "—"}</span>}
        <Button size="sm" variant="ghost" className="shrink-0" onClick={() => setEditing(true)}>{t("edit")}</Button>
      </div>
    );
  }
  return (
    <div className="grid gap-1.5">
      <div className="relative"><Search className="absolute left-2 top-2 size-4 text-muted-foreground" />
        <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("tgSearch")} className="h-8 pl-7" /></div>
      <div className="grid max-h-56 gap-0.5 overflow-auto">
        {(found.data ?? []).map((p) => (
          <button key={p.id} type="button" className="rounded-md px-2 py-1 text-left text-xs hover:bg-muted"
            onClick={() => link.mutate(p.id, { onSuccess: () => setEditing(false) })}>
            <span className="font-medium">{p.name}</span> · {p.role} · {p.project}{p.manager ? ` · ${t("tgSupervisor")}: ${p.manager}` : ""}
          </button>
        ))}
      </div>
      <div className="flex gap-1">
        <Button size="sm" variant="ghost" onClick={() => link.mutate(null, { onSuccess: () => setEditing(false) })}>{t("tgUnlink")}</Button>
        <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>{t("cancel")}</Button>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- xodimlar */
function StaffSection({ t }: { t: ST }) {
  const q = useQuery({ queryKey: ["support", "staff"], queryFn: supportApi.staff });
  const teams = Array.from(new Set((q.data ?? []).map((s) => s.team).filter(Boolean)));
  const columns: Column<StaffRow>[] = [
    { key: "name", header: t("staff"), sort: (s) => s.name.toLowerCase(),
      cell: (s) => <div className="min-w-40 font-medium">{s.name}<div className="text-xs font-normal text-muted-foreground">{s.role}</div></div> },
    { key: "team", header: t("team"), sort: (s) => s.team || null,
      cell: (s) => (s.team ? <Badge variant="outline" className="font-normal">{s.team}</Badge> : <span className="text-xs text-muted-foreground">—</span>) },
    { key: "level", header: "L", sort: (s) => s.level || null, cell: (s) => <span className="text-xs">{s.level}</span> },
    { key: "tg", header: "Telegram", sort: (s) => s.telegram || null,
      cell: (s) => (
        <span className="whitespace-nowrap text-xs">{s.telegram ? `@${s.telegram.replace(/^@/, "")}` : "ID"}
          {s.linked && <span className="ml-1 text-success">· {t("linked")}</span>}</span>
      ) },
    { key: "phone", header: "☎", cell: (s) => <span className="whitespace-nowrap text-xs text-muted-foreground">{s.phone}</span> },
  ];
  return (
    <section>
      <h3 className="mb-1 text-sm font-semibold">{t("staff")}</h3>
      <p className="mb-3 text-xs text-muted-foreground">{t("staffHint")}</p>
      <DataTable rows={q.data} loading={q.isLoading} columns={columns} rowKey={(s) => `${s.type}-${s.id}`} t={t}
        initialSort={{ key: "name", dir: "asc" }} maxHeight="60vh"
        search={(s) => [s.name, s.role, s.team, s.telegram, s.phone].join(" ")}
        filters={[{ value: "all", label: t("dtAll"), test: () => true },
          ...teams.map((tm) => ({ value: `team:${tm}`, label: tm, test: (s: StaffRow) => s.team === tm }))]} />
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
  const [agree, setAgree] = useState(false);
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
            <div className="rounded-lg border border-warning/50 bg-warning/5 p-3 text-xs leading-relaxed">
              <b>{t("mtSafetyTitle")}</b>
              <ul className="mt-1 list-disc pl-4">
                <li>{t("mtSafe1")}</li><li>{t("mtSafe2")}</li><li>{t("mtSafe3")}</li><li>{t("mtSafe4")}</li>
              </ul>
              <label className="mt-2 flex items-center gap-2 text-sm"><Switch checked={agree} onCheckedChange={setAgree} />{t("mtAgree")}</label>
            </div>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
              <FormRow label={t("mtPhone")}><Input value={phone} onChange={(e) => setPhone(e.target.value)} /></FormRow>
              <Button variant="outline" className="self-end" disabled={!agree || phone.length < 10 || send.isPending} onClick={() => send.mutate(undefined)}>
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
              <SearchPicker value={group} onChange={setGroup} className="w-full"
                options={(groups.data ?? []).map((g) => ({ id: g.id, title: g.title || String(g.chat_id), sub: t("q7") + ": " + g.questions_7d }))}
                placeholder={t("histGroup")} searchPlaceholder={t("search")} emptyText={t("pickNone")} />
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
