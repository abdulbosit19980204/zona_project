"use client";

import { Background, BackgroundVariant, Controls, ReactFlow, ReactFlowProvider, useReactFlow } from "@xyflow/react";
import { ArrowLeft, ChevronLeft, ChevronRight, Pencil, Plus, ShieldAlert, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { ContactLinks } from "@/components/common/contacts";
import { Markdown } from "@/components/common/markdown";
import { MemberAvatar } from "@/components/common/member-avatar";
import { RoleLine } from "@/components/common/role";
import { MemberDialog } from "@/components/forms/member-dialog";
import { AuthorityDialog } from "@/components/forms/structure-dialogs";
import { layoutRadial, radialEdgeTypes, radialNodeTypes } from "@/components/graph/radial";
import { PanelSection } from "@/components/panels/info-panels";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useCan, useModel } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/client";
import { aiApi } from "@/lib/api/endpoints";
import type { Authority } from "@/lib/api/types";
import { ROLE_ORDER } from "@/lib/model";

function Canvas({ memberId }: { memberId: number }) {
  const t = useTranslations();
  const model = useModel();
  const router = useRouter();
  const flow = useReactFlow();
  const [hover, setHover] = useState<string | null>(null);
  const graph = useMemo(() => layoutRadial(model, memberId, (r) => t(`roles.${r}`)), [model, memberId, t]);

  useEffect(() => {
    const id = setTimeout(() => void flow.fitView({ padding: 0.12, duration: 400 }), 60);
    return () => clearTimeout(id);
  }, [memberId, flow]);

  const related = useMemo(() => {
    if (!hover) return null;
    const ids = new Set(graph.edges.filter((e) => e.source === hover || e.target === hover).map((e) => e.id));
    const nodes = new Set([hover, ...graph.edges.filter((e) => ids.has(e.id)).flatMap((e) => [e.source, e.target])]);
    return { ids, nodes };
  }, [hover, graph.edges]);
  const nodes = graph.nodes.map((n) => ({ ...n, data: { ...n.data, dim: !!related && !related.nodes.has(n.id) } }));
  const edges = graph.edges.map((e) => ({ ...e, data: e.data ? { ...e.data, highlight: !!related?.ids.has(e.id), dim: !!related && !related.ids.has(e.id) } : e.data }));

  return (
    <ReactFlow
      nodes={nodes} edges={edges} nodeTypes={radialNodeTypes} edgeTypes={radialEdgeTypes}
      onNodeMouseEnter={(_, n) => setHover(n.id)} onNodeMouseLeave={() => setHover(null)}
      onNodeClick={(_, n) => {
        if (n.data.kind === "person") router.push(`/employees/${n.data.id}`);
        if (n.data.kind === "proc") router.push(`/organization?focus=process:${n.data.id}`);
      }}
      fitView minZoom={0.2} maxZoom={1.6} nodesConnectable={false} proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="var(--grid-dot)" />
      <Controls position="bottom-left" showInteractive={false} />
    </ReactFlow>
  );
}

export function Employee360({ memberId }: { memberId: number }) {
  const t = useTranslations();
  const locale = useLocale();
  const model = useModel();
  const can = useCan();
  const router = useRouter();
  const [edit, setEdit] = useState(false);
  const [authority, setAuthority] = useState<Authority | null | undefined>(undefined);
  const analysis = useMutation({ mutationFn: () => aiApi.person(memberId, locale) });
  const m = model.member.get(memberId);
  const order = model.memberOrder;
  const idx = order.findIndex((x) => x.id === memberId);

  if (!m) {
    return <div className="grid h-full place-items-center text-muted-foreground">{t("employees.notFound")} <Link href="/employees" className="underline">{t("nav.employees")}</Link></div>;
  }
  const links = model.linksOfMember.get(m.id) ?? [];
  const noBackup = links.filter((l) => l.roles.has("owner") && !model.hasRole(l.processId, "backup"));
  const authorities = model.authorities.get(m.id) ?? [];
  const workload = model.workload.find((w) => w.member.id === m.id);

  return (
    <div className="flex h-full">
      <div className="canvas-grid relative min-w-0 flex-1">
        <ReactFlowProvider><Canvas memberId={m.id} /></ReactFlowProvider>
        <div className="pointer-events-none absolute inset-x-5 top-4 z-10 flex flex-wrap items-center gap-2">
          <Button asChild variant="outline" size="icon" className="pointer-events-auto"><Link href="/employees" aria-label={t("nav.employees")}><ArrowLeft className="size-4" /></Link></Button>
          <div className="pointer-events-auto flex items-center gap-3">
            <MemberAvatar member={m} size={40} />
            <div><h1 className="text-lg font-semibold leading-tight">{m.name}</h1><p className="text-xs text-muted-foreground">{m.role} · {t("employees.view360")}</p></div>
          </div>
          <div className="flex-1" />
          <Button variant="outline" size="icon" className="pointer-events-auto" disabled={idx <= 0} onClick={() => router.push(`/employees/${order[idx - 1].id}`)}><ChevronLeft className="size-4" /></Button>
          <Select value={String(m.id)} onValueChange={(v) => router.push(`/employees/${v}`)}>
            <SelectTrigger className="pointer-events-auto w-64 bg-card"><SelectValue /></SelectTrigger>
            <SelectContent>{order.map((x) => <SelectItem key={x.id} value={String(x.id)}>{x.name} — {x.role}</SelectItem>)}</SelectContent>
          </Select>
          <Button variant="outline" size="icon" className="pointer-events-auto" disabled={idx >= order.length - 1} onClick={() => router.push(`/employees/${order[idx + 1].id}`)}><ChevronRight className="size-4" /></Button>
          {can.edit && <Button variant="outline" className="pointer-events-auto" onClick={() => setEdit(true)}><Pencil className="size-4" />{t("common.edit")}</Button>}
        </div>
        <div className="glass absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-3 rounded-2xl border px-4 py-2 text-xs text-muted-foreground shadow-lg">
          <span>{t("employees.legend")}</span>
          {ROLE_ORDER.slice(0, 4).map((r) => <span key={r} className="flex items-center gap-1.5"><RoleLine role={r} />{t(`roles.${r}`)}</span>)}
        </div>
      </div>

      <aside className="w-96 shrink-0 overflow-y-auto border-l bg-card/60 backdrop-blur">
        <div className="flex items-start gap-3 border-b px-5 py-5">
          <MemberAvatar member={m} size={48} />
          <div className="min-w-0"><h2 className="font-semibold">{m.name}</h2><p className="text-[13px] text-muted-foreground">{m.role}</p></div>
        </div>
        <PanelSection title={t("panel.contacts")}>
          <ContactLinks contact={m} empty={t("panel.noContacts")} />
        </PanelSection>
        <PanelSection title={t("panel.workload")}>
          <div className="grid grid-cols-3 gap-2 text-center">
            {([[t("panel.tasks"), workload?.tasks ?? 0], [t("panel.owned"), workload?.owned ?? 0], [t("panel.otherRoles"), (workload?.approvals ?? 0) + (workload?.other ?? 0)]] as const).map(([l, v]) => (
              <div key={l} className="rounded-lg border bg-muted/40 py-2"><div className="font-mono text-lg font-semibold">{v}</div><div className="text-[11px] text-muted-foreground">{l}</div></div>
            ))}
          </div>
          {workload?.excessive && <p className="mt-2 text-xs text-warning">{t("workload.excessiveHint")}</p>}
        </PanelSection>
        <PanelSection title={t("panel.authorities")} count={authorities.length}>
          {authorities.map((a) => (
            <button key={a.id} disabled={!can.edit} onClick={() => setAuthority(a)} className="mb-1.5 block w-full rounded-lg border border-dashed border-violet/50 px-3 py-2 text-left text-[13px] enabled:hover:bg-violet/10">
              <div className="font-medium">{a.title}</div>{a.scope && <div className="text-xs text-muted-foreground">{a.scope}</div>}
            </button>
          ))}
          {!authorities.length && <p className="text-sm text-muted-foreground">{t("panel.none")}</p>}
          {can.edit && <Button size="sm" variant="outline" className="mt-1" onClick={() => setAuthority(null)}><Plus className="size-4" />{t("forms.authority.new")}</Button>}
        </PanelSection>
        <PanelSection title={t("panel.boundaries")}>
          {m.trigger && <p className="text-[13px]"><b>{t("panel.receives")}:</b> {m.trigger}</p>}
          {m.does && <p className="mt-1.5 text-[13px]"><b>{t("panel.does")}:</b> {m.does}</p>}
          {m.excludes && <p className="mt-1.5 text-[13px] text-muted-foreground"><b className="text-foreground">{t("panel.notResponsible")}:</b> {m.excludes}</p>}
          {!m.trigger && !m.does && !m.excludes && <p className="text-sm text-muted-foreground">{t("panel.none")}</p>}
        </PanelSection>
        {noBackup.length > 0 && (
          <PanelSection title={t("panel.risks")} count={noBackup.length}>
            <p className="mb-2 text-xs text-muted-foreground">{t("panel.noBackupHint")}</p>
            {noBackup.slice(0, 8).map((l) => (
              <Link key={l.processId} href={`/organization?focus=process:${l.processId}`} className="-mx-2 flex items-center gap-2 rounded-lg px-2 py-1.5 text-[13px] hover:bg-muted">
                <ShieldAlert className="size-3.5 text-warning" /><span className="truncate">{model.process.get(l.processId)?.name}</span>
              </Link>
            ))}
          </PanelSection>
        )}
        <PanelSection title={t("panel.aiAnalysis")} className="border-b-0">
          {!model.state.meta.ai.person && <p className="text-sm text-muted-foreground">{t("ai.disabled")}</p>}
          {analysis.isPending && <p className="text-sm text-muted-foreground">{t("ai.thinking")}</p>}
          {analysis.isError && <p className="text-sm text-destructive">{errorMessage(analysis.error)}</p>}
          {analysis.data && (
            <>
              <Markdown text={analysis.data.text} />
              <p className="mt-2 text-[11px] text-muted-foreground">{analysis.data.meta.model} · {analysis.data.meta.input_tokens + analysis.data.meta.output_tokens} token · {(analysis.data.meta.latency_ms / 1000).toFixed(1)}s</p>
            </>
          )}
          {model.state.meta.ai.person && (
            <Button size="sm" variant="outline" className="mt-2 border-violet/50" disabled={analysis.isPending} onClick={() => analysis.mutate()}>
              <Sparkles className="size-4 text-violet" />{analysis.data ? t("ai.again") : t("ai.analyze")}
            </Button>
          )}
        </PanelSection>
      </aside>
      <MemberDialog open={edit} onOpenChange={setEdit} member={m} />
      <AuthorityDialog open={authority !== undefined} onOpenChange={(o) => !o && setAuthority(undefined)} authority={authority ?? undefined} memberId={m.id} />
    </div>
  );
}
