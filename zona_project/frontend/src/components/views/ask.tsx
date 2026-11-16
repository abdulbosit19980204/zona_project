"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, Loader2, Mail, MessageCircleQuestion, Search, Sparkles, UserRound, UsersRound } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Highlight } from "@/components/common/highlight";
import { MemberAvatar } from "@/components/common/member-avatar";
import { EmptyState, Page, PageHeader, SectionTitle } from "@/components/common/page";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { errorMessage } from "@/lib/api/client";
import { aiApi, orgApi } from "@/lib/api/endpoints";
import { askerKey } from "@/components/forms/askers";
import { StaffContacts } from "@/components/views/staff-shared";
import { useCan, useModel } from "@/hooks/use-org";
import type { AICandidate, Member, SearchResult } from "@/lib/api/types";

const EXAMPLES = {
  uz: ["Mijoz to'lovi tushmadi", "VPN ishlamayapti", "1C da hisobot chiqmayapti", "yangi xodimga kirish huquqi"],
  ru: ["Не прошла оплата клиента", "Не работает VPN", "Отчёт в 1С не формируется", "доступ для нового сотрудника"],
  en: ["Client payment did not arrive", "VPN is down", "1C report fails", "access for a new employee"],
} as const;

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

/** "Savol kimga?" — erkin matndan mas'ulni topish: avval ko'p tilli qidiruv, kerak bo'lsa AI tahlili. */
export function Ask() {
  const t = useTranslations();
  const locale = useLocale() as keyof typeof EXAMPLES;
  const model = useModel();
  const router = useRouter();
  const params = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const query = useDebounced(q.trim(), 250);
  const search = useQuery({ queryKey: ["search", query], queryFn: () => orgApi.search(query, 12), enabled: query.length > 1 });
  const ai = useMutation({ mutationFn: (question: string) => aiApi.route(question) });
  const aiEnabled = model.state.meta.ai.route;

  const run = (text: string) => {
    setQ(text);
    ai.reset();
    router.replace(`/ask?q=${encodeURIComponent(text)}`, { scroll: false });
  };

  return (
    <Page>
      <PageHeader title={t("nav.ask")} description={t("ask.description")} />
      <Card className="gap-3 p-4">
        <form
          className="flex gap-2"
          onSubmit={(e) => { e.preventDefault(); if (aiEnabled && q.trim()) ai.mutate(q.trim()); }}
        >
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input autoFocus value={q} onChange={(e) => { setQ(e.target.value); ai.reset(); }} placeholder={t("ask.placeholder")} className="h-11 pl-9 text-base" />
          </div>
          <Button type="submit" size="lg" className="h-11" disabled={!aiEnabled || !q.trim() || ai.isPending} title={aiEnabled ? undefined : t("ask.aiOff")}>
            {ai.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}{t("ask.askAi")}
          </Button>
        </form>
        <div className="flex flex-wrap gap-1.5">
          {(EXAMPLES[locale] ?? EXAMPLES.uz).map((ex) => (
            <button key={ex} type="button" onClick={() => run(ex)} className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground hover:border-primary/40 hover:text-foreground">{ex}</button>
          ))}
        </div>
        {!aiEnabled && <p className="text-xs text-muted-foreground">{t("ask.aiOff")}</p>}
      </Card>

      {ai.isError && <Alert variant="destructive" className="mt-4"><AlertDescription>{errorMessage(ai.error)}</AlertDescription></Alert>}
      {ai.data && <AiAnswer result={ai.data} />}

      {query.length > 1 && search.data && <LocalResults result={search.data} />}
      {query.length <= 1 && !ai.data && (
        <div className="mt-6"><EmptyState icon={MessageCircleQuestion} title={t("ask.emptyTitle")} hint={t("ask.emptyHint")} /></div>
      )}
    </Page>
  );
}

function AiAnswer({ result }: { result: Awaited<ReturnType<typeof aiApi.route>> }) {
  const t = useTranslations();
  const model = useModel();
  if (result.source !== "ai") {
    return <Alert className="mt-4"><AlertDescription>{result.ai_error || t("ask.aiFallback")}</AlertDescription></Alert>;
  }
  return (
    <Card className="mt-4 gap-3 border-primary/40 p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="size-4 text-primary" />{t("ask.aiAnswer")}
        {result.meta && <span className="ml-auto text-xs font-normal text-muted-foreground">{result.meta.model} · {result.meta.latency_ms} ms</span>}
      </div>
      {result.summary && <p className="text-sm text-muted-foreground">{result.summary}</p>}
      {result.answer && <p className="text-sm">{result.answer}</p>}
      {result.needs_clarification && result.clarifying_question && (
        <Alert><AlertDescription>{t("ask.clarify")}: {result.clarifying_question}</AlertDescription></Alert>
      )}
      <div className="grid gap-2 md:grid-cols-2">
        {(result.candidates ?? []).map((c) => <Candidate key={c.member} c={c} />)}
      </div>
      {!!result.process_ids?.length && (
        <div className="flex flex-wrap gap-1.5">
          {result.process_ids.map((pid) => model.process.get(pid)).filter((p) => p !== undefined).map((p) => (
            <Link key={p.id} href={`/organization?focus=process:${p.id}`}><Badge variant="outline" className="hover:border-primary/50">{p.name}</Badge></Link>
          ))}
        </div>
      )}
    </Card>
  );
}

function Candidate({ c }: { c: AICandidate }) {
  const model = useModel();
  const m = model.member.get(c.member);
  if (!m) return null;
  return (
    <div className="rounded-xl border bg-muted/20 p-3">
      <div className="flex items-center gap-3">
        <MemberAvatar member={m} size={36} />
        <div className="min-w-0 flex-1">
          <Link href={`/employees/${m.id}`} className="font-medium hover:text-primary">{m.name}</Link>
          <div className="truncate text-xs text-muted-foreground">{c.role || m.role}</div>
        </div>
        <span className="font-mono text-sm font-semibold">{Math.round(c.confidence)}%</span>
      </div>
      {c.reason && <p className="mt-2 text-xs text-muted-foreground">{c.reason}</p>}
      <div className="mt-2"><Reach m={m} /></div>
    </div>
  );
}

function LocalResults({ result }: { result: SearchResult }) {
  const t = useTranslations();
  const model = useModel();
  if (!result.people.length && !result.tasks.length) {
    return <div className="mt-6"><EmptyState icon={Search} title={t("common.nothingFound")} hint={t("ask.tryAi")} /></div>;
  }
  const top = result.tasks.map((h) => model.task.get(h.id)).find((x) => x && (x.rule || x.fallbacks.length));
  return (
    <>
      {top && <RuleCard taskId={top.id} />}
      <SectionTitle>{t("ask.whoAnswers")}</SectionTitle>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {result.people.slice(0, 6).map((p, i) => {
          const m = model.member.get(p.member);
          if (!m) return null;
          return (
            <Card key={p.member} className={i === 0 ? "gap-3 border-primary/50 p-4" : "gap-3 p-4"}>
              <div className="flex items-center gap-3">
                <MemberAvatar member={m} size={40} />
                <div className="min-w-0 flex-1">
                  <Link href={`/employees/${m.id}`} className="font-semibold hover:text-primary">{m.name}</Link>
                  <div className="truncate text-xs text-muted-foreground">{m.role}</div>
                </div>
                {i === 0 && <Badge>{t("ask.best")}</Badge>}
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Progress value={p.confidence} className="h-1.5" /><span className="w-10 text-right font-mono">{Math.round(p.confidence)}%</span>
              </div>
              {!!p.via.length && <p className="line-clamp-2 text-xs text-muted-foreground">{t("ask.via")}: {p.via.slice(0, 4).map((v) => (t.has(`ask.viaKind.${v}`) ? t(`ask.viaKind.${v}`) : v)).join(" · ")}</p>}
              <Reach m={m} />
            </Card>
          );
        })}
      </div>
      {!!result.edge_cases.length && (
        <>
          <SectionTitle>{t("ask.edgeCases")}</SectionTitle>
          <Card className="gap-0 p-2">
            {result.edge_cases.map((h) => {
              const e = model.state.edge_cases.find((x) => x.id === h.id);
              if (!e) return null;
              const first = e.first_owner ? model.member.get(e.first_owner) : undefined;
              return (
                <div key={e.id} className="flex items-start gap-3 rounded-lg px-3 py-2.5 text-sm">
                  <ArrowRight className="mt-0.5 size-4 text-primary" />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium"><Highlight text={e.situation} spans={h.hl} /></div>
                    <div className="text-xs text-muted-foreground">{first && <b className="text-foreground">{first.name}</b>} {e.then_text}</div>
                  </div>
                </div>
              );
            })}
          </Card>
        </>
      )}
      {!!result.tasks.length && (
        <>
          <SectionTitle>{t("ask.matchingTasks")}</SectionTitle>
          <Card className="gap-0 p-2">
            {result.tasks.map((h) => {
              const task = model.task.get(h.id);
              if (!task) return null;
              const m = task.owner ? model.member.get(task.owner) : undefined;
              return (
                <div key={h.id} className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-muted/50">
                  <span className="min-w-0 flex-1"><Highlight text={task.title} spans={h.hl} />
                    <span className="ml-2 text-xs text-muted-foreground">{task.process ? model.process.get(task.process)?.name : ""}</span></span>
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><MemberAvatar member={m} size={20} />{m?.name ?? t("common.unassigned")}</span>
                </div>
              );
            })}
          </Card>
        </>
      )}
      {!!result.expanded.length && <p className="mt-4 text-xs text-muted-foreground">{t("ask.expanded")}: {result.expanded.slice(0, 16).join(", ")}</p>}
    </>
  );
}

/** Mas'ul bilan bog'lanish: qo'ng'iroq, Telegram, WhatsApp; jamoa bo'lsa — Kontaktlar sahifasidagi odamlari. */
function Reach({ m }: { m: Member }) {
  const t = useTranslations();
  const can = useCan();
  const has = !!(m.phone || m.telegram);
  // "Supervayzerlar" -> "supervayzer": Kontaktlar sahifasida shu rol bo'yicha qidiruv
  const stem = m.name.toLowerCase().replace(/(lari|lar)\b/g, "").split(/\s+/)[0];
  return (
    <div className="space-y-2">
      {has ? <StaffContacts person={{ phone: m.phone, telegram: m.telegram }} />
        : <p className="text-xs text-muted-foreground">{t("ask.noContacts")}</p>}
      <div className="flex flex-wrap gap-1.5">
        {m.email && (
          <Button asChild size="sm" variant="ghost" className="h-7 px-2 text-xs"><a href={`mailto:${m.email}`}><Mail className="size-3.5" />{m.email}</a></Button>
        )}
        <Button asChild size="sm" variant="ghost" className="h-7 px-2 text-xs">
          <Link href={`/employees/${m.id}`}><UserRound className="size-3.5" />{!has && can.edit ? t("ask.addContacts") : t("ask.profile")}</Link>
        </Button>
        {m.is_team && (
          <Button asChild size="sm" variant="outline" className="h-7 px-2 text-xs">
            <Link href={`/staff?q=${encodeURIComponent(stem)}`}><UsersRound className="size-3.5" />{t("ask.teamContacts")}</Link>
          </Button>
        )}
      </div>
    </div>
  );
}

/** Eng mos savol uchun tayyor javob: qoida va kim → kim zanjiri (bot ham shuni yuboradi). */
function RuleCard({ taskId }: { taskId: number }) {
  const t = useTranslations();
  const model = useModel();
  const task = model.task.get(taskId);
  if (!task) return null;
  const process = task.process ? model.process.get(task.process) : undefined;
  const zone = model.zoneOf(process);
  const owner = task.owner ? model.member.get(task.owner) : undefined;
  return (
    <Card className="mt-6 gap-3 border-primary/40 p-5">
      <div className="text-xs text-muted-foreground">{[zone?.name, process?.name].filter(Boolean).join(" → ")}</div>
      <div className="text-base font-semibold">{task.title}</div>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {task.asker && <span className="rounded-full bg-muted px-2 py-0.5 text-muted-foreground">{t(`knowledge.askers.${askerKey(task.asker)}`)}</span>}
        {task.asker && <ArrowRight className="size-3 text-muted-foreground" />}
        <span className="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 font-medium text-primary">{owner?.name ?? t("common.unassigned")}</span>
        {task.fallbacks.map((f, i) => (
          <span key={i} className="flex items-center gap-1.5" title={f.condition}>
            <ArrowRight className="size-3 text-muted-foreground" />
            <span className="rounded-full border px-2 py-0.5 text-muted-foreground">{model.member.get(f.member)?.name}</span>
          </span>
        ))}
      </div>
      {task.rule && (
        <div className="rounded-lg border-l-[3px] border-primary bg-muted/30 px-3 py-2">
          <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-primary">{t("knowledge.rule")}</div>
          <p className="whitespace-pre-line text-[13px] leading-relaxed">{task.rule}</p>
        </div>
      )}
      {task.fallbacks.some((f) => f.condition) && (
        <ol className="space-y-1 text-[12.5px]">
          {task.fallbacks.map((f, i) => f.condition && (
            <li key={i}><b className="font-medium">{i + 2}. {model.member.get(f.member)?.name}</b> — <span className="text-muted-foreground">{f.condition}</span></li>
          ))}
        </ol>
      )}
      {owner && <Reach m={owner} />}
    </Card>
  );
}
