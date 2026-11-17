"use client";

import { Bell, Bot, CheckCircle2, FolderTree, Image as ImageIcon, Link2, LogOut, QrCode, RotateCcw, Save, Settings2, Trash2, Type, Upload, XCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Page, PageHeader } from "@/components/common/page";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useQr, useQrAction } from "@/hooks/use-qrdrive";
import { qrApi, type QrSettings, type QrStyle } from "@/lib/api/qrdrive";
import { cn } from "@/lib/utils";

import { ConfirmDialog, FormRow, QrGuard } from "./common";
import { useQt, type QKey } from "./i18n";

type Values = Partial<QrSettings> & { bot_token?: string; link_password?: string };

export interface BotCheck { ok: boolean; username?: string; name?: string; photo?: string; title?: string; hint?: string }

export function BotTestResult({ r }: { r: BotCheck | null }) {
  const t = useQt();
  if (!r) return null;
  return r.ok ? (
    <div className="flex items-center gap-3 rounded-lg border border-success/30 bg-success/5 px-3 py-2 text-sm">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {r.photo ? <img src={r.photo} alt="" className="size-9 rounded-full" /> : <Bot className="size-6 text-success" />}
      <span><span className="flex items-center gap-1.5 font-medium text-success"><CheckCircle2 className="size-4" />{t("botConnected", { name: r.username ?? "" })}</span>
        <span className="text-xs text-muted-foreground">{r.name}</span></span>
    </div>
  ) : (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm">
      <div className="flex items-center gap-1.5 font-medium text-destructive"><XCircle className="size-4" />{r.title}</div>
      {r.hint && <div className="text-xs text-muted-foreground">{r.hint}</div>}
    </div>
  );
}

function renderTpl(tpl: string, original = "Ariza.pdf") {
  const now = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  const map: Record<string, string> = {
    xodim: "olimova_d", "boʻlim": "Kadrlar", "bo'lim": "Kadrlar", bolim: "Kadrlar", yyyy: String(now.getFullYear()), mm: p(now.getMonth() + 1),
    dd: p(now.getDate()), sana: `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`,
    vaqt: `${p(now.getHours())}-${p(now.getMinutes())}-${p(now.getSeconds())}`, asl_nom: original,
  };
  return tpl.replace(/\{([^{}]+)\}/g, (m, k: string) => map[k.trim()] ?? m);
}

const NOTIFY_KEYS = ["failed", "storage", "quota", "request", "expiring", "daily"] as const;

export function QrSettingsPage() {
  const t = useQt();
  const q = useQr<QrSettings>(["settings"], "settings");
  const [v, setV] = useState<Values>({});
  const [token, setToken] = useState("");
  const [linkPass, setLinkPass] = useState("");
  const [botCheck, setBotCheck] = useState<BotCheck | null>(null);
  const [textLang, setTextLang] = useState("uz");
  const [logoutOpen, setLogoutOpen] = useState(false);
  const logoInput = useRef<HTMLInputElement>(null);
  const s = q.data;
  const cur = useMemo(() => ({ ...s, ...v }) as QrSettings, [s, v]);
  const dirty = Object.keys(v).length > 0 || token !== "" || linkPass !== "";
  const set = <K extends keyof QrSettings>(k: K, value: QrSettings[K]) => setV((old) => ({ ...old, [k]: value }));
  const setStyle = (patch: Partial<QrStyle>) => set("qr_style", { ...cur.qr_style, ...patch });

  const save = useQrAction(async () => {
    const body: Record<string, unknown> = { ...v };
    if (token) body.bot_token = token;
    if (linkPass) body.link_password = linkPass === "-" ? "" : linkPass;
    return (await qrApi.patch<QrSettings>("settings", body)).data;
  }, t("saved"));
  const test = useQrAction(async () => (await qrApi.post<BotCheck>("settings/bot/test", { token, api_url: cur.bot_api_url })).data);
  const logout = useQrAction(async () => qrApi.post("settings/bot/logout"), t("done"));
  const logo = useQrAction(async (file: File | null) => {
    if (!file) return qrApi.delete("settings/logo");
    const fd = new FormData();
    fd.append("file", file);
    return qrApi.post("settings/logo", fd);
  }, t("saved"));

  // QR jonli ko'rinishi
  const [preview, setPreview] = useState<string | null>(null);
  const styleKey = JSON.stringify(cur.qr_style ?? {}) + (cur.company_name ?? "") + String(s?.logo);
  useEffect(() => {
    if (!s) return;
    const timer = setTimeout(async () => {
      try {
        const { data } = await qrApi.post<Blob>("settings/qr/preview", { style: cur.qr_style, company: cur.company_name }, { responseType: "blob" });
        setPreview((old) => { if (old) URL.revokeObjectURL(old); return URL.createObjectURL(data); });
      } catch { /* servis ishlamasa — ko'rinish yangilanmaydi */ }
    }, 350);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [styleKey]);

  const doSave = () => save.mutate(undefined, { onSuccess: () => { setV({}); setToken(""); setLinkPass(""); } });
  const texts = cur.bot_texts?.[textLang] ?? {};
  const defaults = s?.default_texts?.[textLang] ?? {};

  return (
    <Page>
      <PageHeader title={t("setTitle")} description={t("setDesc")} actions={
        <>
          {dirty && <span className="text-sm text-warning">{t("unsaved")}</span>}
          <Button disabled={!dirty || save.isPending} onClick={doSave}><Save className="size-4" />{t("save")}</Button>
        </>
      } />
      <QrGuard query={q}>
        {s && (
          <Tabs defaultValue="bot">
            <TabsList className="mb-4 flex-wrap">
              <TabsTrigger value="bot"><Bot className="size-4" />{t("secBot")}</TabsTrigger>
              <TabsTrigger value="files"><FolderTree className="size-4" />{t("secFiles")}</TabsTrigger>
              <TabsTrigger value="links"><Link2 className="size-4" />{t("secLinks")}</TabsTrigger>
              <TabsTrigger value="qr"><QrCode className="size-4" />{t("secQr")}</TabsTrigger>
              <TabsTrigger value="texts"><Type className="size-4" />{t("secTexts")}</TabsTrigger>
              <TabsTrigger value="notify"><Bell className="size-4" />{t("secNotify")}</TabsTrigger>
              <TabsTrigger value="general"><Settings2 className="size-4" />{t("secGeneral")}</TabsTrigger>
            </TabsList>

            <TabsContent value="bot">
              <Card className="grid max-w-2xl gap-4 p-5">
                <FormRow label={t("botToken")} help={t("botTokenHint")}
                  hint={s.bot_token_set ? `${t("set")}${s.bot_username ? ` · @${s.bot_username}` : ""} — ${t("secretKeep")}` : t("notSet")}>
                  <div className="flex gap-2">
                    <Input type="password" autoComplete="new-password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="123456789:AA…" />
                    <Button variant="outline" onClick={() => test.mutate(undefined, { onSuccess: setBotCheck })} disabled={test.isPending}>{t("botTest")}</Button>
                  </div>
                </FormRow>
                <BotTestResult r={botCheck} />
                <FormRow label={t("apiUrl")} hint={t("apiUrlHint")}>
                  <Input value={cur.bot_api_url ?? ""} onChange={(e) => set("bot_api_url", e.target.value)} placeholder="http://127.0.0.1:8081" />
                </FormRow>
                <label className="flex items-center justify-between gap-3 text-sm">
                  <span>{t("regRequired")}<span className="block text-xs text-muted-foreground">{t("regRequiredHint")}</span></span>
                  <Switch checked={cur.registration_required ?? true} onCheckedChange={(x) => set("registration_required", x)} />
                </label>
                <label className="flex items-center justify-between gap-3 text-sm">{t("apiLocal")}
                  <Switch checked={!!cur.bot_api_local} onCheckedChange={(x) => set("bot_api_local", x)} /></label>
                <div className="flex items-center gap-3 border-t pt-3">
                  <Button variant="outline" size="sm" disabled={!s.bot_token_set} onClick={() => setLogoutOpen(true)}><LogOut className="size-4" />{t("logout")}</Button>
                  <span className="text-xs text-muted-foreground">{t("logoutHint")}</span>
                </div>
                <FormRow label={t("defaultLang")}>
                  <Select value={cur.default_lang} onValueChange={(x) => set("default_lang", x)}>
                    <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="uz">O‘zbekcha</SelectItem><SelectItem value="ru">Русский</SelectItem></SelectContent>
                  </Select>
                </FormRow>
              </Card>
            </TabsContent>

            <TabsContent value="files">
              <Card className="grid max-w-2xl gap-4 p-5">
                <FormRow label={t("maxMb")} hint={!cur.bot_api_url && cur.max_file_mb > 20 ? t("apiUrlHint") : undefined}>
                  <Input type="number" min={1} max={2000} className="w-40" value={cur.max_file_mb} onChange={(e) => set("max_file_mb", Number(e.target.value))} />
                </FormRow>
                <FormRow label={t("allowedTypes")} hint={t("allowedTypesHint")}>
                  <Input value={cur.allowed_types} onChange={(e) => set("allowed_types", e.target.value)} placeholder="pdf, docx, xlsx, jpg, png" />
                </FormRow>
                <FormRow label={t("folderTpl")} help={t("tplHint")} hint={t("tplExample", { path: `/Kadrlar/${renderTpl(cur.folder_template)}` })}>
                  <Input value={cur.folder_template} onChange={(e) => set("folder_template", e.target.value)} />
                </FormRow>
                <FormRow label={t("fileTpl")} help={t("tplHint")} hint={`${t("tplExample", { path: renderTpl(cur.filename_template, "Ariza") + ".pdf" })} ${t("extAuto")}`}>
                  <Input value={cur.filename_template} onChange={(e) => set("filename_template", e.target.value)} />
                </FormRow>
                <p className="-mt-2 font-mono text-xs text-muted-foreground">{t("tplHint")}</p>
                <FormRow label={t("replaceMode")} hint={t("replaceHint")}>
                  <Select value={cur.replace_mode ?? "ask"} onValueChange={(x) => set("replace_mode", x as QrSettings["replace_mode"])}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ask">{t("replaceAsk")}</SelectItem>
                      <SelectItem value="replace">{t("replaceReplace")}</SelectItem>
                      <SelectItem value="new">{t("replaceNew")}</SelectItem>
                    </SelectContent>
                  </Select>
                </FormRow>
                <FormRow label={t("multiMode")}>
                  <Select value={cur.multi_mode ?? "ask"} onValueChange={(x) => set("multi_mode", x as QrSettings["multi_mode"])}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ask">{t("multiAsk")}</SelectItem>
                      <SelectItem value="folder">{t("multiFolder")}</SelectItem>
                      <SelectItem value="separate">{t("multiSeparate")}</SelectItem>
                    </SelectContent>
                  </Select>
                </FormRow>
                <FormRow label={t("archiveMode")}>
                  <Select value={cur.archive_mode ?? "ask"} onValueChange={(x) => set("archive_mode", x as QrSettings["archive_mode"])}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ask">{t("archiveAsk")}</SelectItem>
                      <SelectItem value="archive">{t("archiveArchive")}</SelectItem>
                      <SelectItem value="folder">{t("archiveFolder")}</SelectItem>
                    </SelectContent>
                  </Select>
                </FormRow>
                <div className="grid gap-4 sm:grid-cols-2">
                  <FormRow label={t("archiveMaxFiles")}><Input type="number" min={1} value={cur.archive_max_files ?? 1000} onChange={(e) => set("archive_max_files", Number(e.target.value))} /></FormRow>
                  <FormRow label={t("archiveMaxMb")}><Input type="number" min={1} value={cur.archive_max_mb ?? 2048} onChange={(e) => set("archive_max_mb", Number(e.target.value))} /></FormRow>
                </div>
                <FormRow label={t("dupPolicy")}>
                  <Select value={cur.duplicate_policy} onValueChange={(x) => set("duplicate_policy", x as QrSettings["duplicate_policy"])}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="reuse">{t("dupReuse")}</SelectItem><SelectItem value="upload">{t("dupUpload")}</SelectItem></SelectContent>
                  </Select>
                </FormRow>
                <label className="flex items-center justify-between gap-3 text-sm">{t("autoFallback")}
                  <Switch checked={cur.auto_fallback} onCheckedChange={(x) => set("auto_fallback", x)} /></label>
              </Card>
            </TabsContent>

            <TabsContent value="links">
              <Card className="grid max-w-2xl gap-4 p-5">
                <FormRow label={t("visMode")} hint={t("visHint")}>
                  <Select value={cur.visibility_mode ?? "ask"} onValueChange={(x) => set("visibility_mode", x as QrSettings["visibility_mode"])}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ask">{t("visModeAsk")}</SelectItem>
                      <SelectItem value="public">{t("visModePublic")}</SelectItem>
                      <SelectItem value="private">{t("visModePrivate")}</SelectItem>
                    </SelectContent>
                  </Select>
                </FormRow>
                <div className="grid gap-4 sm:grid-cols-2">
                  <FormRow label={t("defaultVisibility")}>
                    <Select value={cur.default_visibility ?? "public"} onValueChange={(x) => set("default_visibility", x as QrSettings["default_visibility"])}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="public">{t("visPublic")}</SelectItem>
                        <SelectItem value="private">{t("visPrivate")}</SelectItem>
                      </SelectContent>
                    </Select>
                  </FormRow>
                  <FormRow label={t("visTimeout")}>
                    <Input type="number" min={1} max={1440} value={cur.visibility_timeout_min ?? 10} onChange={(e) => set("visibility_timeout_min", Number(e.target.value))} />
                  </FormRow>
                </div>
                <FormRow label={t("linkDays")}>
                  <Input type="number" min={0} className="w-40" value={cur.link_expire_days} onChange={(e) => set("link_expire_days", Number(e.target.value))} />
                </FormRow>
                <FormRow label={t("linkPassword")} hint={linkPass === "-" ? t("notSet") : s.link_password_set ? `${t("set")} — ${t("secretKeep")}` : t("notSet")}>
                  <div className="flex gap-2">
                    <Input type="password" autoComplete="new-password" value={linkPass === "-" ? "" : linkPass} onChange={(e) => setLinkPass(e.target.value)} />
                    {s.link_password_set && <Button variant="outline" onClick={() => setLinkPass("-")}><Trash2 className="size-4" />{t("delete")}</Button>}
                  </div>
                </FormRow>
              </Card>
            </TabsContent>

            <TabsContent value="qr">
              <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
                <Card className="grid gap-4 p-5">
                  <div className="grid gap-4 sm:grid-cols-3">
                    <FormRow label={t("qrSize")}><Input type="number" min={200} max={2000} step={50} value={cur.qr_style.size} onChange={(e) => setStyle({ size: Number(e.target.value) })} /></FormRow>
                    <FormRow label={t("qrFg")}><Input type="color" className="h-9 p-1" value={cur.qr_style.fg} onChange={(e) => setStyle({ fg: e.target.value })} /></FormRow>
                    <FormRow label={t("qrBg")}><Input type="color" className="h-9 p-1" value={cur.qr_style.bg} onChange={(e) => setStyle({ bg: e.target.value })} /></FormRow>
                  </div>
                  <FormRow label={t("qrCaption")}>
                    <Select value={cur.qr_style.caption} onValueChange={(x) => setStyle({ caption: x as QrStyle["caption"] })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>{(["filename", "company", "custom", "none"] as const).map((c) => <SelectItem key={c} value={c}>{t(`cap_${c}` as QKey)}</SelectItem>)}</SelectContent>
                    </Select>
                  </FormRow>
                  {cur.qr_style.caption === "custom" && <FormRow label={t("captionText")}><Input value={cur.qr_style.caption_text} onChange={(e) => setStyle({ caption_text: e.target.value })} /></FormRow>}
                  {cur.qr_style.caption === "company" && <FormRow label={t("companyName")}><Input value={cur.company_name} onChange={(e) => set("company_name", e.target.value)} /></FormRow>}
                  <label className="flex items-center justify-between gap-3 text-sm">{t("qrLogo")}
                    <Switch checked={cur.qr_style.logo} disabled={!s.logo} onCheckedChange={(x) => setStyle({ logo: x })} /></label>
                  <div className="flex gap-2">
                    <input ref={logoInput} type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) logo.mutate(f, { onSuccess: () => setStyle({ logo: true }) }); e.target.value = ""; }} />
                    <Button variant="outline" size="sm" onClick={() => logoInput.current?.click()}><Upload className="size-4" />{t("uploadLogo")}</Button>
                    {s.logo && <Button variant="ghost" size="sm" onClick={() => logo.mutate(null, { onSuccess: () => setStyle({ logo: false }) })}><Trash2 className="size-4" />{t("removeLogo")}</Button>}
                  </div>
                </Card>
                <Card className="grid place-items-center gap-2 p-5">
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("livePreview")}</div>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {preview ? <img src={preview} alt="QR" className="w-64 rounded-lg border" /> : <ImageIcon className="size-16 text-muted-foreground" />}
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="texts">
              <Card className="grid gap-3 p-5">
                <div className="flex items-center gap-3">
                  <span className="text-sm">{t("textsLang")}:</span>
                  <Select value={textLang} onValueChange={setTextLang}>
                    <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="uz">O‘zbekcha</SelectItem><SelectItem value="ru">Русский</SelectItem></SelectContent>
                  </Select>
                </div>
                <div className="grid gap-3 lg:grid-cols-2">
                  {Object.keys(defaults).map((key) => {
                    const value = texts[key] ?? defaults[key];
                    const changed = value !== defaults[key];
                    return (
                      <div key={key} className="grid gap-1">
                        <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">{key}
                          {changed && <button className="ml-auto flex items-center gap-1 hover:text-foreground" onClick={() =>
                            set("bot_texts", { ...cur.bot_texts, [textLang]: { ...texts, [key]: defaults[key] } })}><RotateCcw className="size-3" />{t("resetText")}</button>}
                        </div>
                        <Textarea rows={key === "start" || key === "help" ? 4 : 2} className={cn(changed && "border-primary/50")} value={value}
                          onChange={(e) => set("bot_texts", { ...cur.bot_texts, [textLang]: { ...texts, [key]: e.target.value } })} />
                      </div>
                    );
                  })}
                </div>
              </Card>
            </TabsContent>

            <TabsContent value="notify">
              <Card className="grid max-w-2xl gap-4 p-5">
                <FormRow label={t("notifyChats")} hint={t("notifyChatsHint")}>
                  <Input value={cur.notify_chat_ids} onChange={(e) => set("notify_chat_ids", e.target.value)} placeholder="123456789, 987654321" />
                </FormRow>
                {NOTIFY_KEYS.map((k) => (
                  <label key={k} className="flex items-center justify-between gap-3 text-sm">{t(`n_${k}` as QKey)}
                    <Switch checked={!!cur.notify?.[k]} onCheckedChange={(x) => set("notify", { ...cur.notify, [k]: x })} /></label>
                ))}
                {cur.notify?.daily && <FormRow label={t("dailyTime")}><Input type="time" className="w-36" value={cur.daily_report_time} onChange={(e) => set("daily_report_time", e.target.value)} /></FormRow>}
              </Card>
            </TabsContent>

            <TabsContent value="general">
              <Card className="grid max-w-2xl gap-4 p-5 sm:grid-cols-2">
                <FormRow label={t("publicBaseUrl")} hint={t("publicBaseUrlHint")} className="sm:col-span-2">
                  <Input value={cur.public_base_url ?? ""} onChange={(e) => set("public_base_url", e.target.value)} placeholder="https://zona.stargroup.uz" />
                </FormRow>
                <FormRow label={t("companyName")}><Input value={cur.company_name} onChange={(e) => set("company_name", e.target.value)} /></FormRow>
                <FormRow label={t("timezone")}><Input value={cur.timezone} onChange={(e) => set("timezone", e.target.value)} /></FormRow>
                <FormRow label={t("savedMinutes")}><Input type="number" min={0} value={cur.saved_minutes_per_file} onChange={(e) => set("saved_minutes_per_file", Number(e.target.value))} /></FormRow>
                <FormRow label={t("retention")}><Input type="number" min={30} value={cur.retention_days} onChange={(e) => set("retention_days", Number(e.target.value))} /></FormRow>
                <FormRow label={t("trashDays")}><Input type="number" min={1} value={cur.trash_days} onChange={(e) => set("trash_days", Number(e.target.value))} /></FormRow>
                <FormRow label={t("backupDays")}><Input type="number" min={1} value={cur.backup_keep_days} onChange={(e) => set("backup_keep_days", Number(e.target.value))} /></FormRow>
              </Card>
            </TabsContent>
          </Tabs>
        )}
      </QrGuard>
      <ConfirmDialog open={logoutOpen} onOpenChange={setLogoutOpen} title={t("logout")} description={t("logoutHint")}
        onConfirm={() => logout.mutate(undefined, { onSuccess: () => setLogoutOpen(false) })} />
    </Page>
  );
}
