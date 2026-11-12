"use client";

import { ArrowRight, Ban, Download, GitBranch, MessageSquareText, Phone, Send, Signpost, Split } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { toast } from "sonner";

import { MemberAvatar } from "@/components/common/member-avatar";
import { Page, PageHeader } from "@/components/common/page";
import { Button } from "@/components/ui/button";
import { useModel } from "@/hooks/use-org";
import type { Member, Task } from "@/lib/api/types";

const ACCENTS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];
const tint = (c: string, pct: number) => `color-mix(in oklab, ${c} ${pct}%, transparent)`;

interface Person {
  member: Member;
  accent: string;
  total: number;
  groups: { name: string; count: number }[];
  backupCount: number;
}

interface Chain {
  key: string;
  owner: number | null;
  steps: { member: number; condition: string }[];
  tasks: Task[];
}

/**
 * "Kimga murojaat" — bitta rasmda butun tashkilot: qaysi savol bilan kimga yozish,
 * u qila olmasa kimga o'tadi va chegaradagi holatlar. PNG qilib agentlarga yuborish uchun.
 */
export function Cheatsheet() {
  const t = useTranslations("cheatsheet");
  const model = useModel();
  const poster = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);

  const { people, accentOf, chains } = useMemo(() => {
    const ownTasks = new Map<number, Task[]>();
    for (const task of model.state.tasks) {
      if (!task.owner) continue;
      const list = ownTasks.get(task.owner) ?? [];
      list.push(task);
      ownTasks.set(task.owner, list);
    }
    const edgeOwners = new Set(model.state.edge_cases.map((e) => e.first_owner));
    const accentOf = new Map<number, string>();
    const people: Person[] = [];
    for (const m of model.memberOrder) {
      const own = ownTasks.get(m.id) ?? [];
      const backupCount = model.fallbackTasksOf.get(m.id)?.length ?? 0;
      if (!own.length && !backupCount && !m.trigger && !edgeOwners.has(m.id)) continue;
      const accent = ACCENTS[people.length % ACCENTS.length];
      accentOf.set(m.id, accent);
      const byProcess = new Map<string, number>();
      for (const task of own) {
        const name = (task.process && model.process.get(task.process)?.name) || "—";
        byProcess.set(name, (byProcess.get(name) ?? 0) + 1);
      }
      const groups = [...byProcess.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
      people.push({ member: m, accent, total: own.length, groups, backupCount });
    }

    // bir xil zanjirli vazifalar bitta qatorga yig'iladi
    const byKey = new Map<string, Chain>();
    for (const task of model.state.tasks) {
      if (!task.fallbacks?.length) continue;
      const steps = task.fallbacks.map((f) => ({ member: f.member, condition: f.condition }));
      const key = `${task.owner ?? 0}|${steps.map((s) => `${s.member}:${s.condition}`).join("|")}`;
      const c = byKey.get(key) ?? { key, owner: task.owner, steps, tasks: [] };
      c.tasks.push(task);
      byKey.set(key, c);
    }
    const chains = [...byKey.values()].sort((a, b) => b.tasks.length - a.tasks.length);
    return { people, accentOf, chains };
  }, [model]);

  const accent = (id: number | null) => (id != null && accentOf.get(id)) || "var(--muted-foreground)";
  // uz lokali brauzerlarda "2026 M11 12" bo'lib chiqadi: raqamli format hamma tilda bir xil o'qiladi
  const now = new Date();
  const today = `${String(now.getDate()).padStart(2, "0")}.${String(now.getMonth() + 1).padStart(2, "0")}.${now.getFullYear()}`;
  const company = model.state.meta.company;

  const download = async () => {
    if (!poster.current) return;
    setBusy(true);
    try {
      const { toPng } = await import("html-to-image");
      const bg = getComputedStyle(document.body).backgroundColor;
      const url = await toPng(poster.current, { pixelRatio: 2, backgroundColor: bg, cacheBust: true });
      const a = document.createElement("a");
      a.href = url;
      a.download = `kimga-murojaat-${new Date().toISOString().slice(0, 10)}.png`;
      a.click();
    } catch {
      toast.error(t("downloadError"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page>
      <PageHeader
        title={t("pageTitle")}
        description={t("description")}
        actions={<Button onClick={download} disabled={busy}><Download className="size-4" />{busy ? t("downloading") : t("download")}</Button>}
      />

      <div ref={poster} className="mx-auto max-w-[1500px] rounded-2xl border bg-background p-6 sm:p-8">
        {/* sarlavha */}
        <header className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b pb-6">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-primary">
              <Signpost className="size-4" />{company}
            </div>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">{t("title")}</h2>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{t("subtitle")}</p>
          </div>
          <div className="text-right text-xs text-muted-foreground">{t("updated", { date: today })}</div>
        </header>

        {/* 1. kimga */}
        <SectionHead n={1} icon={MessageSquareText} title={t("people")} />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {people.map((p) => <PersonCard key={p.member.id} person={p} />)}
        </div>

        {/* 2. navbat */}
        <SectionHead n={2} icon={GitBranch} title={t("chains")} hint={t("chainsHint")} />
        {chains.length ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {chains.map((c) => (
              <div key={c.key} className="rounded-xl border bg-card p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Step n={1} member={c.owner ? model.member.get(c.owner) : undefined} accent={accent(c.owner)} />
                  {c.steps.map((s, i) => (
                    <div key={s.member} className="flex items-center gap-2">
                      <div className="flex flex-col items-center px-1">
                        <ArrowRight className="size-4 text-muted-foreground" />
                        <span className="max-w-36 text-center text-[10px] leading-tight text-muted-foreground">{s.condition || t("ifCannot")}</span>
                      </div>
                      <Step n={i + 2} member={model.member.get(s.member)} accent={accent(s.member)} />
                    </div>
                  ))}
                </div>
                <ul className="mt-3 grid gap-1 border-t pt-3 text-sm">
                  {c.tasks.map((task) => (
                    <li key={task.id} className="flex gap-2"><span className="text-muted-foreground">•</span>{task.title}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        ) : (
          <p className="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">{t("chainsEmpty")}</p>
        )}

        {/* 3. chegaradagi holatlar */}
        {model.state.edge_cases.length > 0 && (
          <>
            <SectionHead n={3} icon={Split} title={t("edges")} hint={t("edgesHint")} />
            <div className="overflow-hidden rounded-xl border">
              {model.state.edge_cases.map((e, i) => {
                const m = e.first_owner ? model.member.get(e.first_owner) : undefined;
                return (
                  <div key={e.id} className={`grid items-center gap-3 px-4 py-3 text-sm md:grid-cols-[1fr_15rem_1.4fr] ${i % 2 ? "bg-muted/30" : "bg-card"}`}>
                    <div className="font-medium">{e.situation}</div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">{t("first")}</span>
                      <Pill member={m} accent={accent(e.first_owner)} />
                    </div>
                    <div className="text-muted-foreground"><span className="mr-1 text-xs font-semibold uppercase text-foreground/70">{t("then")}:</span>{e.then_text || "—"}</div>
                  </div>
                );
              })}
            </div>
          </>
        )}

        <footer className="mt-8 flex flex-wrap items-center justify-between gap-2 border-t pt-4 text-xs text-muted-foreground">
          <span>{t("footer")}</span>
          <span>{company} · {today}</span>
        </footer>
      </div>
    </Page>
  );
}

function SectionHead({ n, icon: Icon, title, hint }: { n: number; icon: typeof Split; title: string; hint?: string }) {
  return (
    <div className="mb-4 mt-10 flex items-start gap-3 first-of-type:mt-0">
      <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-primary text-sm font-bold text-primary-foreground">{n}</span>
      <div>
        <h3 className="flex items-center gap-2 text-lg font-semibold"><Icon className="size-4 text-primary" />{title}</h3>
        {hint && <p className="text-sm text-muted-foreground">{hint}</p>}
      </div>
    </div>
  );
}

function PersonCard({ person: p }: { person: Person }) {
  const t = useTranslations("cheatsheet");
  const m = p.member;
  const tg = m.telegram.replace(/^@/, "");
  const shown = p.groups.slice(0, 8);
  const style = { borderTopColor: p.accent } as CSSProperties;
  return (
    <article className="flex flex-col rounded-xl border border-t-4 bg-card p-4" style={style}>
      <div className="flex items-center gap-3">
        <MemberAvatar member={m} size={44} className="text-base" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-lg font-semibold leading-tight">{m.name}</div>
          <div className="truncate text-xs text-muted-foreground">{m.role}</div>
        </div>
        {p.total > 0 && (
          <span className="rounded-full px-2.5 py-1 font-mono text-xs font-semibold" style={{ background: tint(p.accent, 16), color: p.accent }}>
            {t("tasksN", { count: p.total })}
          </span>
        )}
      </div>

      {(m.phone || tg) && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {m.phone && <span className="inline-flex items-center gap-1.5"><Phone className="size-3 text-muted-foreground" />{m.phone}</span>}
          {tg && <span className="inline-flex items-center gap-1.5"><Send className="size-3 text-muted-foreground" />@{tg}</span>}
        </div>
      )}

      {m.trigger && (
        <div className="mt-3 rounded-lg px-3 py-2.5" style={{ background: tint(p.accent, 10) }}>
          <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: p.accent }}>{t("whenToWrite")}</div>
          <div className="mt-0.5 text-[15px] font-medium leading-snug">«{m.trigger}»</div>
        </div>
      )}

      {shown.length > 0 && (
        <Block label={t("questionTypes")}>
          <div className="flex flex-wrap gap-1.5">
            {shown.map((g) => (
              <span key={g.name} className="inline-flex items-center gap-1.5 rounded-md border bg-muted/40 px-2 py-0.5 text-xs">
                {g.name}<span className="font-mono text-[10px] text-muted-foreground">{g.count}</span>
              </span>
            ))}
            {p.groups.length > shown.length && <span className="px-1 text-xs text-muted-foreground">{t("more", { count: p.groups.length - shown.length })}</span>}
          </div>
        </Block>
      )}

      {p.backupCount > 0 && (
        <Block label={t("backupFor")}>
          <span className="text-sm">{t("backupCount", { count: p.backupCount })}</span>
        </Block>
      )}

      {m.excludes && (
        <div className="mt-auto pt-3">
          <div className="flex gap-2 rounded-lg border border-dashed px-3 py-2 text-xs text-muted-foreground">
            <Ban className="mt-0.5 size-3.5 shrink-0 text-destructive/70" />
            <span><b className="text-foreground/80">{t("notThis")}:</b> {m.excludes}</span>
          </div>
        </div>
      )}
    </article>
  );
}

function Block({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mt-3">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
      {children}
    </div>
  );
}

function Step({ n, member, accent }: { n: number; member?: Member; accent: string }) {
  return (
    <div className="flex items-center gap-2 rounded-xl border px-2.5 py-1.5" style={{ borderColor: tint(accent, 45), background: tint(accent, 8) }}>
      <span className="grid size-5 place-items-center rounded-full font-mono text-[11px] font-bold text-white" style={{ background: accent }}>{n}</span>
      <MemberAvatar member={member} size={24} />
      <span className="text-sm font-medium">{member?.name ?? "—"}</span>
    </div>
  );
}

function Pill({ member, accent }: { member?: Member; accent: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border py-0.5 pl-0.5 pr-2.5 text-sm font-medium" style={{ borderColor: tint(accent, 45), background: tint(accent, 8) }}>
      <MemberAvatar member={member} size={22} />{member?.name ?? "—"}
    </span>
  );
}
