"use client";

import { Archive, Database, Download, HardDrive, ListOrdered, Send, Server, Upload } from "lucide-react";
import { useRef } from "react";

import { Page, PageHeader, SectionTitle, StatCard } from "@/components/common/page";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useQr, useQrAction } from "@/hooks/use-qrdrive";
import { download, formatBytes, qrApi, type SystemStatus } from "@/lib/api/qrdrive";

import { Dot, QrGuard, fmtDate } from "./common";
import { errorText, useQt } from "./i18n";

/** Tizim holati: har bir servis (api, worker, bot) alohida, navbat, baza, disk, saqlash joylari, zaxira. */
export function QrSystem() {
  const t = useQt();
  const q = useQr<SystemStatus>(["system"], "system", undefined, { refetchInterval: 15_000 });
  const backup = useQrAction(async () => (await qrApi.post<{ name: string }>("system/backup")).data, t("backupMade"));
  const envInput = useRef<HTMLInputElement>(null);
  const legacy = useQrAction(async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return (await qrApi.post<{ employees: number }>("system/legacy-import", fd)).data;
  }, (r) => t("legacyDone", { n: r.employees }));
  const s = q.data;
  const queue = s ? Object.values(s.queue).reduce((a, b) => a + b, 0) : 0;
  return (
    <Page>
      <PageHeader title={t("sysTitle")} description={t("sysDesc")} />
      <QrGuard query={q}>
        {s && (
          <>
            <div className="grid gap-3 md:grid-cols-3">
              {s.services.map((svc) => (
                <Card key={svc.name} className="gap-1 px-5 py-4">
                  <div className="flex items-center gap-2 font-medium"><Dot ok={svc.ok} /><Server className="size-4 text-muted-foreground" />{svc.label}</div>
                  <div className={svc.ok ? "text-sm text-success" : "text-sm text-destructive"}>{svc.ok ? t("svcOk") : t("svcDown")}</div>
                  <div className="text-xs text-muted-foreground">{t("lastSeen")}: {fmtDate(svc.last_seen)}</div>
                  {svc.started_at && <div className="text-xs text-muted-foreground">{t("startedAt")}: {fmtDate(svc.started_at)}</div>}
                  {typeof svc.info.status === "string" && <div className="text-xs text-muted-foreground">{String(svc.info.status)}{svc.info.username ? ` · @${String(svc.info.username)}` : ""}</div>}
                </Card>
              ))}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard label={t("queue")} value={queue} icon={ListOrdered} tone={queue > 20 ? "warning" : "default"} />
              <StatCard label={t("database")} value={formatBytes(s.database.size)} icon={Database} />
              <StatCard label={t("disk")} value={formatBytes(s.disk.free)} icon={HardDrive} hint={t("diskFree", { free: formatBytes(s.disk.free), total: formatBytes(s.disk.total) })}
                progress={s.disk.total ? 1 - s.disk.free / s.disk.total : undefined} tone={s.disk.total && s.disk.free / s.disk.total < 0.1 ? "danger" : "default"} />
              <StatCard label={t("tgApi")} value={s.telegram_api.bot ? `@${s.telegram_api.bot}` : "—"} icon={Send} hint={s.telegram_api.mode} />
            </div>

            <SectionTitle>{t("stoTitle")}</SectionTitle>
            <Card className="gap-0 divide-y p-0">
              {s.storages.map((st) => (
                <div key={st.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                  <Dot ok={st.status === "ok"} unknown={st.status === "unknown"} />
                  <span className="font-medium">{st.name}</span>
                  <span className="text-muted-foreground">{st.latency_ms !== null ? `${st.latency_ms} ms` : ""}</span>
                  {st.error && <span className="text-destructive">{errorText(t, { kind: st.error_kind, title: st.error, hint: "" })?.title}</span>}
                  <span className="ml-auto text-xs text-muted-foreground">{t("lastCheck")}: {fmtDate(st.last_check_at)}</span>
                </div>
              ))}
              {!s.storages.length && <div className="px-5 py-3 text-sm text-muted-foreground">{t("stoEmpty")}</div>}
            </Card>

            <SectionTitle actions={<Button size="sm" onClick={() => backup.mutate()} disabled={backup.isPending}><Archive className="size-4" />{t("makeBackup")}</Button>}>
              {t("backups")}
            </SectionTitle>
            <Card className="gap-0 divide-y p-0">
              {s.backups.map((b) => (
                <div key={b.name} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                  <Archive className="size-4 text-muted-foreground" />
                  <span className="flex-1 font-mono text-xs">{b.name}</span>
                  <span className="text-xs text-muted-foreground">{formatBytes(b.size)} · {fmtDate(b.created_at)}</span>
                  <Button size="icon" variant="ghost" onClick={() => download(`system/backups/${b.name}`, b.name)} aria-label={t("download")}><Download className="size-4" /></Button>
                </div>
              ))}
              {!s.backups.length && <div className="px-5 py-3 text-sm text-muted-foreground">{t("noBackups")}</div>}
            </Card>
            <SectionTitle>{t("runtime")}</SectionTitle>
            <Card className="grid gap-1 p-5 text-sm">
              <p className="mb-2 text-xs text-muted-foreground">{t("runtimeHint")}</p>
              <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                <span className="text-muted-foreground">{t("publicBaseUrl")}</span><code className="break-all">{s.runtime.public_base_url}</code>
                <span className="text-muted-foreground">API</span><code>{s.runtime.host}:{s.runtime.port}</code>
                <span className="text-muted-foreground">{t("database")}</span><code className="break-all">{s.runtime.data_dir}</code>
                <span className="text-muted-foreground">{t("timezone")}</span><code>{s.runtime.timezone}</code>
              </div>
              <div className={s.runtime.master_key_set && s.runtime.sso_set ? "mt-2 text-success" : "mt-2 text-warning"}>
                {s.runtime.master_key_set && s.runtime.sso_set ? t("keysOk") : t("keysDev")}
              </div>
            </Card>

            <SectionTitle>{t("legacyImport")}</SectionTitle>
            <Card className="flex flex-row flex-wrap items-center gap-3 p-5 text-sm">
              <p className="min-w-0 flex-1 text-muted-foreground">{t("legacyImportHint")}</p>
              <input ref={envInput} type="file" accept=".env,.txt,text/plain" hidden
                onChange={(e) => { const f = e.target.files?.[0]; if (f) legacy.mutate(f); e.target.value = ""; }} />
              <Button variant="outline" onClick={() => envInput.current?.click()} disabled={legacy.isPending}><Upload className="size-4" />{t("import")}</Button>
            </Card>
            <p className="mt-4 text-xs text-muted-foreground">{t("version")}: {s.version}</p>
          </>
        )}
      </QrGuard>
    </Page>
  );
}
