"use client";

import {
  Background, BackgroundVariant, Controls, MiniMap, ReactFlow, ReactFlowProvider, useReactFlow, type NodeMouseHandler,
} from "@xyflow/react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, PanelRightClose, PanelRightOpen, Plus, Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { RoleLine } from "@/components/common/role";
import { ProcessDialog } from "@/components/forms/structure-dialogs";
import { edgeTypes } from "@/components/graph/role-edge";
import { nodeTypes } from "@/components/graph/nodes";
import { layoutOrg, relatedTo, type OrgNode } from "@/components/graph/org-layout";
import { InfoPanel } from "@/components/panels/info-panels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCan, useModel, useScope } from "@/hooks/use-org";
import type { RoleKey } from "@/lib/api/types";
import { ROLE_ORDER } from "@/lib/model";
import { cn } from "@/lib/utils";
import { useUI } from "@/stores/ui";

const norm = (s: string) => s.toLowerCase().replace(/[ʻʼ’‘`´]/g, "'");

function MapCanvas() {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const { scope } = useScope();
  const params = useSearchParams();
  const flow = useReactFlow();
  const { collapsedDepts, hiddenRoles, onlyIssues, toggleRole, setOnlyIssues } = useUI();
  const [selected, setSelected] = useState<string | null>(params.get("focus")?.replace(/^p:/, "process:") ?? null);
  const [hover, setHover] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [panel, setPanel] = useState(true);
  const [newProcess, setNewProcess] = useState(false);

  const graph = useMemo(
    () => layoutOrg(model, { scope, collapsed: collapsedDepts, hiddenRoles, onlyIssues, roleLabel: (r) => t(`roles.${r}`) }),
    [model, scope, collapsedDepts, hiddenRoles, onlyIssues, t],
  );

  // xaritada qidiruv: nom, lavozim va jarayon ichidagi vazifalar matni bo'yicha
  const matches = useMemo(() => {
    const q = norm(query.trim());
    if (q.length < 2) return null;
    const hit = new Set<string>();
    for (const n of graph.nodes) {
      const { kind, id } = n.data;
      const text = kind === "member" ? `${model.member.get(id)?.name} ${model.member.get(id)?.role}`
        : kind === "process" ? `${model.process.get(id)?.name} ${(model.tasksOf.get(id) ?? []).map((x) => x.title).join(" ")}`
        : kind === "dept" ? model.dept.get(id)?.name ?? ""
        : kind === "team" ? model.team.get(id)?.name ?? "" : "";
      if (norm(text).includes(q)) hit.add(n.id);
    }
    return hit;
  }, [query, graph.nodes, model]);

  const focusKey = hover ?? selected;
  const related = useMemo(() => (focusKey ? relatedTo(focusKey, graph.edges) : null), [focusKey, graph.edges]);
  const nodes = useMemo<OrgNode[]>(() => graph.nodes.map((n) => ({
    ...n,
    data: {
      ...n.data,
      selected: n.id === selected,
      match: !!matches?.has(n.id),
      dim: related ? !related.nodes.has(n.id) : !!matches && !matches.has(n.id) && n.data.kind !== "company",
    },
  })), [graph.nodes, selected, matches, related]);
  const edges = useMemo(() => graph.edges.map((e) => ({
    ...e,
    data: e.data ? { ...e.data, highlight: !!related?.edges.has(e.id), dim: (!!related && !related.edges.has(e.id)) || (!related && !!matches) } : e.data,
  })), [graph.edges, related, matches]);

  // Boshida tuzilma (kompaniya → xodim) o'qiladigan masshtabda; jarayonlar o'ngda, surib ko'riladi.
  const fitOptions = useMemo(() => ({
    padding: 0.08, maxZoom: 1, minZoom: 0.45,
    nodes: graph.nodes.filter((n) => n.data.kind !== "process").map((n) => ({ id: n.id })),
  }), [graph.nodes]);

  // ?focus= yoki qidiruvdan tanlangan tugunga yaqinlashish
  const centerOn = useCallback((key: string) => {
    const n = graph.nodes.find((x) => x.id === key);
    if (n) void flow.setCenter(n.position.x + (n.width ?? 0) / 2, n.position.y + (n.height ?? 0) / 2, { zoom: 1, duration: 500 });
  }, [graph.nodes, flow]);
  const focusParam = params.get("focus")?.replace(/^p:/, "process:") ?? null;
  const [lastFocus, setLastFocus] = useState(focusParam);
  if (focusParam !== lastFocus) {
    setLastFocus(focusParam);
    if (focusParam) setSelected(focusParam);
  }
  const centerRef = useRef(centerOn);
  useEffect(() => {
    centerRef.current = centerOn;
  }, [centerOn]);
  useEffect(() => {
    if (!focusParam) return;
    const id = setTimeout(() => centerRef.current(focusParam), 150);
    return () => clearTimeout(id);
  }, [focusParam]);

  const select = (key: string) => {
    setSelected(key);
    setPanel(true);
    centerOn(key);
  };
  const onNodeClick: NodeMouseHandler<OrgNode> = (_, node) => setSelected((cur) => (cur === node.id ? null : node.id));

  return (
    <div className="flex h-full">
      <div className="canvas-grid relative min-w-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodeClick={onNodeClick}
          onNodeMouseEnter={(_, n) => setHover(n.id)}
          onNodeMouseLeave={() => setHover(null)}
          onPaneClick={() => setSelected(null)}
          fitView
          fitViewOptions={fitOptions}
          minZoom={0.2}
          maxZoom={1.8}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="var(--grid-dot)" />
          <Controls position="bottom-left" showInteractive={false} />
          <MiniMap
            position="bottom-right" pannable zoomable
            nodeColor={(n) => ((n as OrgNode).data.selected ? "var(--primary)" : (n as OrgNode).data.match ? "var(--cyan)" : "var(--edge-soft)")}
            maskColor="color-mix(in srgb, var(--background) 70%, transparent)"
          />
        </ReactFlow>

        {/* sarlavha va filtrlar */}
        <div className="pointer-events-none absolute inset-x-5 top-4 z-10 flex flex-wrap items-start gap-3">
          <div className="pointer-events-auto">
            <h1 className="text-lg font-semibold tracking-tight">{t("nav.organization")}</h1>
            <p className="text-xs text-muted-foreground">
              <span className="mr-1.5 inline-block size-1.5 rounded-full bg-cyan shadow-[0_0_8px_var(--cyan)]" />
              {t("org.subtitle", { members: model.state.members.length, processes: graph.processCount })}
            </p>
          </div>
          <div className="flex-1" />
          <div className="glass pointer-events-auto relative w-64 rounded-lg">
            <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("org.findOnMap")} className="h-9 border-border bg-transparent pl-8" />
          </div>
          {matches && <span className="pointer-events-auto self-center text-xs text-muted-foreground">{t("org.found", { count: matches.size })}</span>}
          {can.edit && <Button className="pointer-events-auto" variant="outline" onClick={() => setNewProcess(true)}><Plus className="size-4" />{t("forms.process.new")}</Button>}
          <Button className="pointer-events-auto" variant="outline" size="icon" onClick={() => setPanel((p) => !p)} aria-label={t("org.panel")}>
            {panel ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
          </Button>
        </div>

        {/* rol filtrlari (legenda ham) */}
        <div className="glass absolute bottom-4 left-1/2 z-10 flex max-w-[calc(100%-360px)] -translate-x-1/2 items-center gap-1 overflow-x-auto rounded-2xl border p-1.5 shadow-lg">
          {ROLE_ORDER.map((r: RoleKey) => (
            <button
              key={r}
              onClick={() => toggleRole(r)}
              className={cn("flex h-8 shrink-0 items-center gap-2 rounded-xl px-2.5 text-xs hover:bg-muted", hiddenRoles.includes(r) && "opacity-40")}
              title={t(`roles.hint.${r}`)}
            >
              <RoleLine role={r} />{t(`roles.${r}`)}
            </button>
          ))}
          <span className="mx-1 h-5 w-px bg-border" />
          <button
            onClick={() => setOnlyIssues(!onlyIssues)}
            className={cn("flex h-8 shrink-0 items-center gap-2 rounded-xl px-2.5 text-xs hover:bg-muted", onlyIssues && "bg-warning/15 text-warning")}
          >
            <AlertTriangle className="size-3.5" />{t("org.onlyIssues")} · {model.issueProcesses.length}
          </button>
          <span className="shrink-0 px-2 text-xs text-muted-foreground">{graph.processCount}/{model.state.processes.length}</span>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {panel && (
          <motion.aside
            key="panel"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 384, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 380, damping: 38 }}
            className="shrink-0 overflow-hidden border-l bg-card/60 backdrop-blur"
          >
            <div className="h-full w-96 overflow-y-auto">
              <InfoPanel selected={selected} onSelect={select} />
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
      <ProcessDialog open={newProcess} onOpenChange={setNewProcess} />
    </div>
  );
}

export function OrganizationMap() {
  return (
    <ReactFlowProvider>
      <MapCanvas />
    </ReactFlowProvider>
  );
}
