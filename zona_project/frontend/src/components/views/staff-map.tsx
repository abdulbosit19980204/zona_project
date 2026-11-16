"use client";

import {
  Background, BackgroundVariant, Controls, MiniMap, ReactFlow, ReactFlowProvider, useReactFlow,
  type Node, type NodeMouseHandler, type NodeProps,
} from "@xyflow/react";
import { formatDistanceToNow } from "date-fns";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight, Building2, ChevronDown, ChevronRight, Download, ExternalLink, FileJson, FileSpreadsheet, History, List, Mail, PanelRightClose,
  PanelRightOpen, Pencil, Plus, RefreshCw, Repeat2, Search, Upload, UserMinus, UserPlus, Users,
} from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { memo, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { DATE_LOCALES } from "@/components/common/activity";
import { Shell } from "@/components/graph/nodes";
import type { OrgEdge } from "@/components/graph/org-layout";
import { edgeTypes } from "@/components/graph/role-edge";
import { PanelSection } from "@/components/panels/info-panels";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import type { StaffPerson, StaffProject, StaffRole, StaffState } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { matchesTerms, ROLE_TONE, RoleChip, searchTerms, StaffContacts, tenure, type Index } from "./staff-shared";

/* ================================================================== joylashuv */
type Kind = "company" | "project" | "unit" | "person";

interface StaffNodeData extends Record<string, unknown> {
  kind: Kind;
  id: number;
  depth: number;
  title: string;
  sub: string;
  person?: StaffPerson;
  size: number; // shu tugun ostidagi o'rinlar soni
  vacancies: number;
  hasKids: boolean;
  collapsed: boolean;
  onToggle?: () => void;
  dim: boolean;
  selected: boolean;
  match: boolean;
}
type StaffNode = Node<StaffNodeData>;

const SIZE: Record<Kind, { w: number; h: number }> = {
  company: { w: 230, h: 196 }, project: { w: 250, h: 66 }, unit: { w: 240, h: 58 }, person: { w: 260, h: 58 },
};
const COL = 300;
const ROW_GAP = 14;
const GROUP_GAP = 30;
const COMPANY = "company:0";

const key = (kind: Kind, id: number) => `${kind}:${id}`;
const kindOf = (k: string) => k.split(":")[0] as Kind;
const idOf = (k: string) => Number(k.split(":")[1]);

interface Tree {
  kids: Map<string, string[]>;
  parent: Map<string, string>;
  size: Map<string, number>;
  vacancies: Map<string, number>;
}

/**
 * Daraxt: StarGroup → brend jamoasi → (yuqori rahbar) → yo'nalish → guruh rahbari → xodim.
 * Xodim rahbari bilan bir yo'nalishda bo'lsa — rahbari ostida, aks holda yo'nalishi ostida.
 * Yo'nalish — uning yuqori xodimlari bitta rahbarga bo'ysunsa, o'sha rahbar ostida.
 */
function buildTree(projects: StaffProject[], index: Index): Tree {
  const parent = new Map<string, string>();
  for (const pr of projects) {
    const pk = key("project", pr.id);
    parent.set(pk, COMPANY);
    const list = index.byProject.get(pr.id) ?? [];
    const unitIds = new Set(pr.units.map((u) => u.id));
    const boss = (p: StaffPerson) => {
      const m = p.manager ? index.person.get(p.manager) : undefined;
      return m && m.project === pr.id ? m : undefined;
    };
    for (const u of pr.units) {
      const tops = list.filter((p) => p.unit === u.id && boss(p)?.unit !== u.id);
      const bosses = new Set(tops.map((p) => boss(p)?.id ?? 0));
      const only = bosses.size === 1 ? [...bosses][0] : 0;
      parent.set(key("unit", u.id), only ? key("person", only) : pk);
    }
    for (const p of list) {
      const m = boss(p);
      const unit = p.unit && unitIds.has(p.unit) ? p.unit : null;
      parent.set(key("person", p.id), m && (!unit || m.unit === unit) ? key("person", m.id) : unit ? key("unit", unit) : pk);
    }
    // halqa (yo'nalish o'z ichidagi xodimga ulanib qolsa) — yo'nalishni jamoaga ulaymiz
    for (const u of pr.units) {
      const k = key("unit", u.id);
      const seen = new Set([k]);
      for (let cur = parent.get(k); cur && cur !== pk; cur = parent.get(cur)) {
        if (seen.has(cur)) { parent.set(k, pk); break; }
        seen.add(cur);
      }
    }
  }

  // bolalar tartibi: avval xodimlar (tartib bo'yicha), keyin yo'nalishlar
  const people = new Map<string, string[]>();
  const units = new Map<string, string[]>();
  const push = (m: Map<string, string[]>, k: string, v: string) => m.set(k, [...(m.get(k) ?? []), v]);
  for (const pr of projects) {
    push(people, COMPANY, key("project", pr.id));
    for (const p of index.byProject.get(pr.id) ?? []) push(people, parent.get(key("person", p.id))!, key("person", p.id));
    for (const u of pr.units) push(units, parent.get(key("unit", u.id))!, key("unit", u.id));
  }
  const kids = new Map<string, string[]>();
  const size = new Map<string, number>();
  const vacancies = new Map<string, number>();
  const walk = (k: string): [number, number] => {
    const list = [...(people.get(k) ?? []), ...(units.get(k) ?? [])];
    let s = 0;
    let v = 0;
    const shown: string[] = [];
    for (const c of list) {
      const [cs, cv] = walk(c);
      const self = kindOf(c) === "person" ? 1 : 0;
      if (kindOf(c) === "unit" && !cs) continue; // bo'sh yo'nalish ko'rsatilmaydi
      shown.push(c);
      s += cs + self;
      v += cv + (self && index.person.get(idOf(c))?.is_vacancy ? 1 : 0);
    }
    kids.set(k, shown);
    size.set(k, s);
    vacancies.set(k, v);
    return [s, v];
  };
  walk(COMPANY);
  return { kids, parent, size, vacancies };
}

function ancestors(k: string, tree: Tree) {
  const out: string[] = [];
  for (let cur = tree.parent.get(k); cur; cur = tree.parent.get(cur)) out.push(cur);
  return out;
}

interface Placed { x: number; y: number; w: number; h: number; depth: number }

function layout(tree: Tree, collapsed: (k: string) => boolean) {
  const pos = new Map<string, Placed>();
  const edges: [string, string][] = [];
  let cursor = 40;
  const place = (k: string, depth: number): number => {
    const kind = kindOf(k);
    const { w, h } = SIZE[kind];
    const kids = k !== COMPANY && collapsed(k) ? [] : tree.kids.get(k) ?? [];
    let center: number;
    if (!kids.length) {
      center = cursor + h / 2;
      cursor += h + ROW_GAP;
    } else {
      const centers = kids.map((c) => {
        edges.push([k, c]);
        return place(c, depth + 1);
      });
      center = (centers[0] + centers[centers.length - 1]) / 2;
      if (kind === "project" || kind === "unit") cursor += GROUP_GAP;
    }
    pos.set(k, { x: depth * COL, y: center - h / 2, w, h, depth });
    return center;
  };
  place(COMPANY, 0);
  return { pos, edges };
}

/* ================================================================== tugunlar */
function Toggle({ data }: { data: StaffNodeData }) {
  const t = useTranslations("org");
  if (!data.hasKids || !data.onToggle) return null;
  return (
    <button
      type="button"
      className="nodrag flex h-7 shrink-0 items-center gap-0.5 rounded-md px-1.5 font-mono text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground"
      onClick={(e) => { e.stopPropagation(); data.onToggle?.(); }}
      title={data.collapsed ? t("expand") : t("collapse")}
    >
      {data.collapsed && data.size}
      {data.collapsed && data.vacancies > 0 && <span className="ml-0.5 size-1.5 rounded-full bg-destructive" />}
      {data.collapsed ? <ChevronRight className="size-4" /> : <ChevronDown className="size-4" />}
    </button>
  );
}

const CompanyNode = memo(function CompanyNode({ data }: NodeProps<StaffNode>) {
  const t = useTranslations("staff");
  const rows: [string, number, boolean?][] = [
    [t("stats.projects"), Number(data.sub)],
    [t("stats.seats"), data.size],
    [t("stats.vacancies"), data.vacancies, data.vacancies > 0],
  ];
  return (
    <Shell data={data} className="px-4 pb-3 pt-12 text-center">
      <span className="absolute -top-9 left-1/2 grid size-[72px] -translate-x-1/2 place-items-center rounded-full border border-primary/40 bg-[radial-gradient(circle_at_50%_35%,var(--elevated),var(--card)_70%)] shadow-[0_0_0_6px_var(--background),0_0_0_7px_color-mix(in_srgb,var(--primary)_20%,transparent),0_0_40px_-6px_var(--primary),0_0_60px_-24px_var(--violet)]">
        <span className="size-[18px] rounded-full bg-primary shadow-[0_0_0_6px_color-mix(in_srgb,var(--primary)_18%,transparent),0_0_22px_var(--primary)]" />
      </span>
      <div className="text-[15px] font-semibold">{data.title}</div>
      <div className="text-[11.5px] text-muted-foreground">{t("title")}</div>
      <dl className="mt-3 grid gap-1.5 text-left text-[12.5px]">
        {rows.map(([label, value, warn]) => (
          <div key={label} className="flex justify-between text-muted-foreground">
            <dt>{label}</dt><dd className={cn("font-mono font-medium text-foreground", warn && "text-destructive")}>{value}</dd>
          </div>
        ))}
      </dl>
    </Shell>
  );
});

const ProjectNode = memo(function ProjectNode({ data }: NodeProps<StaffNode>) {
  const t = useTranslations("staff");
  return (
    <Shell data={data} className={cn("flex items-center gap-3 px-3", data.collapsed && "border-dashed")}>
      <span className="grid size-10 shrink-0 place-items-center rounded-lg border bg-primary/10 text-primary"><Building2 className="size-[18px]" /></span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[14px] font-semibold">{data.title}</div>
        <div className="truncate text-[11.5px] text-muted-foreground">
          {t("seats", { count: data.size })}
          {data.vacancies > 0 && <span className="text-destructive"> · {t("vacancies", { count: data.vacancies })}</span>}
        </div>
      </div>
      <Toggle data={data} />
    </Shell>
  );
});

const UnitNode = memo(function UnitNode({ data }: NodeProps<StaffNode>) {
  const t = useTranslations("staff");
  return (
    <Shell data={data} className={cn("flex items-center gap-3 px-3", data.collapsed && "border-dashed")}>
      <span className="grid size-8 shrink-0 place-items-center rounded-lg border text-muted-foreground"><Users className="size-4" /></span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium">{data.title}</div>
        <div className="truncate text-[11px] text-muted-foreground">
          {t("seats", { count: data.size })}
          {data.vacancies > 0 && <span className="text-destructive"> · {t("vacancies", { count: data.vacancies })}</span>}
        </div>
      </div>
      <Toggle data={data} />
    </Shell>
  );
});

const PersonNode = memo(function PersonNode({ data }: NodeProps<StaffNode>) {
  const t = useTranslations("staff.roles");
  const p = data.person;
  if (!p) return null;
  return (
    <Shell data={data} className={cn("flex items-center gap-3 px-3", p.is_vacancy && !data.selected && !data.match && "border-dashed border-destructive/50")}>
      <span
        className={cn("grid size-9 shrink-0 place-items-center rounded-full font-mono text-[10.5px] font-bold",
          p.is_vacancy ? "bg-destructive/12 text-destructive" : ROLE_TONE[p.role])}
      >
        {p.role}
      </span>
      <div className="min-w-0 flex-1">
        <div className={cn("truncate text-[13px] font-semibold", p.is_vacancy && "text-destructive")}>{data.title}</div>
        <div className="truncate text-[11.5px] text-muted-foreground">
          {p.territory ? <span className="font-mono">{p.territory}</span> : t(p.role)}{p.city && ` · ${p.city}`}
        </div>
      </div>
      <Toggle data={data} />
    </Shell>
  );
});

const nodeTypes = { company: CompanyNode, project: ProjectNode, unit: UnitNode, person: PersonNode };

/* ================================================================== xarita */
export interface StaffMapProps {
  data: StaffState;
  index: Index;
  canEdit: boolean;
  active: number | "all";
  onActive: (id: number | "all") => void;
  onOpen: (p: StaffPerson) => void;
  onAdd: (project: number) => void;
  onEditProject: (project: StaffProject) => void;
  onSync: (project: StaffProject) => void;
  onImport: () => void;
  onExport: (fmt: "xlsx" | "json") => void;
  exporting: boolean;
  onList: () => void;
  onNewProject: () => void;
  onAssign: (p: StaffPerson) => void;
  onVacate: (p: StaffPerson) => void;
}

function MapCanvas(props: StaffMapProps) {
  const { data, index, canEdit, active, onActive } = props;
  const t = useTranslations();
  const flow = useReactFlow();
  const [selected, setSelected] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [panel, setPanel] = useState(true);
  const [toggled, setToggled] = useState<Map<string, boolean>>(new Map());

  const projects = useMemo(() => (active === "all" ? data.projects : data.projects.filter((p) => p.id === active)), [data.projects, active]);
  const tree = useMemo(() => buildTree(projects, index), [projects, index]);

  // qidiruv: F.I.Sh., hudud, shahar, telefon, rahbar... (kirill/lotin farqsiz)
  const terms = useMemo(() => searchTerms(query), [query]);
  const matches = useMemo(() => {
    if (!terms.length || (terms.length === 1 && terms[0].length < 2)) return null;
    const hit = new Set<string>();
    for (const pr of projects) for (const p of index.byProject.get(pr.id) ?? []) if (matchesTerms(index, p, terms)) hit.add(key("person", p.id));
    return hit;
  }, [terms, projects, index]);
  const matchPath = useMemo(() => {
    const s = new Set<string>();
    for (const k of matches ?? []) for (const a of ancestors(k, tree)) s.add(a);
    return s;
  }, [matches, tree]);

  const toggle = useCallback((k: string, value: boolean) => setToggled((m) => new Map(m).set(k, value)), []);
  const graph = useMemo(() => {
    const collapsed = (k: string) => {
      if (matchPath.has(k)) return false;
      return toggled.get(k) ?? (kindOf(k) === "unit" && active === "all");
    };
    const { pos, edges } = layout(tree, collapsed);
    const nodes: StaffNode[] = [...pos.entries()].map(([k, p]) => {
      const kind = kindOf(k);
      const id = idOf(k);
      const person = kind === "person" ? index.person.get(id) : undefined;
      const hasKids = !!tree.kids.get(k)?.length;
      const isCollapsed = hasKids && collapsed(k);
      return {
        id: k, type: kind, position: { x: p.x, y: p.y }, width: p.w, height: p.h, draggable: false,
        data: {
          kind, id, depth: p.depth, person,
          title: kind === "company" ? "StarGroup" : kind === "project" ? index.project.get(id)?.name ?? "" : kind === "unit" ? index.unit.get(id) ?? ""
            : person?.is_vacancy ? t("staff.vacancy") : person?.name ?? "",
          sub: kind === "company" ? String(projects.length) : "",
          size: tree.size.get(k) ?? 0, vacancies: tree.vacancies.get(k) ?? 0,
          hasKids, collapsed: isCollapsed, onToggle: kind !== "company" ? () => toggle(k, !isCollapsed) : undefined,
          dim: false, selected: false, match: false,
        },
      };
    });
    const edgeList: OrgEdge[] = edges.map(([s, tg]) => ({
      id: `${s}>${tg}`, source: s, target: tg, type: "role", data: { role: "struct", label: "", highlight: false, dim: false },
    }));
    return { nodes, edges: edgeList };
  }, [tree, toggled, matchPath, active, index, projects.length, t, toggle]);

  const focusKey = hover ?? selected;
  const related = useMemo(() => {
    if (!focusKey || focusKey === COMPANY) return null;
    const ids = new Set([focusKey, ...ancestors(focusKey, tree)]);
    for (const e of graph.edges) if (e.source === focusKey) ids.add(e.target);
    return ids;
  }, [focusKey, tree, graph.edges]);

  const nodes = useMemo<StaffNode[]>(() => graph.nodes.map((n) => ({
    ...n,
    data: {
      ...n.data,
      selected: n.id === selected,
      match: !!matches?.has(n.id),
      dim: related ? !related.has(n.id) : !!matches && !matches.has(n.id) && !matchPath.has(n.id),
    },
  })), [graph.nodes, selected, matches, matchPath, related]);
  const edges = useMemo(() => graph.edges.map((e) => ({
    ...e,
    data: e.data
      ? { ...e.data, highlight: !!related?.has(e.source) && !!related?.has(e.target), dim: related ? !(related.has(e.source) && related.has(e.target)) : !!matches && !matchPath.has(e.source) }
      : e.data,
  })), [graph.edges, related, matches, matchPath]);

  // boshida: kompaniya, jamoalar va yo'nalishlar o'qiladigan masshtabda (pastdagilar surib ko'riladi)
  const fitOptions = useMemo(() => ({
    padding: 0.1, maxZoom: 1, minZoom: 0.75,
    nodes: graph.nodes.filter((n) => n.data.depth <= 3).map((n) => ({ id: n.id })),
  }), [graph.nodes]);
  const fitRef = useRef(fitOptions);
  useEffect(() => {
    fitRef.current = fitOptions;
  }, [fitOptions]);
  useEffect(() => {
    const id = setTimeout(() => void flow.fitView({ ...fitRef.current, duration: 400 }), 60);
    return () => clearTimeout(id);
  }, [active, flow]);

  // tanlangan tugunga yaqinlashish (yig'ilgan bo'lsa — avval yoyiladi, keyin markazlanadi)
  const pending = useRef<string | null>(null);
  const centerOn = useCallback((k: string) => {
    const n = graph.nodes.find((x) => x.id === k);
    if (!n) return false;
    void flow.setCenter(n.position.x + (n.width ?? 0) / 2, n.position.y + (n.height ?? 0) / 2, { zoom: 1, duration: 500 });
    return true;
  }, [graph.nodes, flow]);
  useEffect(() => {
    if (pending.current && centerOn(pending.current)) pending.current = null;
  }, [centerOn]);

  const select = (k: string) => {
    setSelected(k);
    setPanel(true);
    const closed = ancestors(k, tree).filter((a) => graph.nodes.find((n) => n.id === a)?.data.collapsed || !graph.nodes.some((n) => n.id === a));
    if (closed.length || !graph.nodes.some((n) => n.id === k)) {
      pending.current = k;
      setToggled((m) => {
        const next = new Map(m);
        for (const a of ancestors(k, tree)) next.set(a, false);
        return next;
      });
    } else centerOn(k);
  };
  const changeProject = (id: number | "all") => {
    setToggled(new Map());
    setSelected(null);
    onActive(id);
  };
  const onNodeClick: NodeMouseHandler<StaffNode> = (_, node) => setSelected((cur) => (cur === node.id ? null : node.id));
  const total = projects.reduce((s, p) => s + (index.byProject.get(p.id)?.length ?? 0), 0);

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
          minZoom={0.1}
          maxZoom={1.8}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="var(--grid-dot)" />
          <Controls position="bottom-left" showInteractive={false} />
          <MiniMap
            position="bottom-right" pannable zoomable
            nodeColor={(n) => {
              const d = (n as StaffNode).data;
              return d.selected ? "var(--primary)" : d.match ? "var(--cyan)" : d.person?.is_vacancy ? "var(--destructive)" : "var(--edge-soft)";
            }}
            maskColor="color-mix(in srgb, var(--background) 70%, transparent)"
          />
        </ReactFlow>

        {/* sarlavha, qidiruv va amallar */}
        <div className="pointer-events-none absolute inset-x-5 top-4 z-10 flex flex-wrap items-start gap-3">
          <div className="pointer-events-auto">
            <h1 className="text-lg font-semibold tracking-tight">{t("staff.title")}</h1>
            <p className="text-xs text-muted-foreground">
              <span className="mr-1.5 inline-block size-1.5 rounded-full bg-cyan shadow-[0_0_8px_var(--cyan)]" />
              {t("staff.subtitle", { projects: projects.length, seats: total, vacancies: tree.vacancies.get(COMPANY) ?? 0 })}
            </p>
          </div>
          <div className="flex-1" />
          <div className="glass pointer-events-auto relative w-72 rounded-lg">
            <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                const first = matches ? [...matches][0] : undefined;
                if (e.key === "Enter" && first) select(first);
              }}
              placeholder={t("staff.searchPlaceholder")}
              className="h-9 border-border bg-transparent pl-8"
            />
          </div>
          {matches && <span className="pointer-events-auto self-center text-xs text-muted-foreground">{t("staff.found", { count: matches.size })}</span>}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button className="pointer-events-auto" variant="outline" disabled={!data.projects.length || props.exporting}>
                <Download className="size-4" />{t("staff.export")}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => props.onExport("xlsx")}><FileSpreadsheet className="size-4" />Excel (.xlsx)</DropdownMenuItem>
              <DropdownMenuItem onClick={() => props.onExport("json")}><FileJson className="size-4" />JSON</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          {canEdit && <Button className="pointer-events-auto" onClick={props.onImport}><Upload className="size-4" />{t("staff.import")}</Button>}
          <Button className="pointer-events-auto" variant="outline" size="icon" onClick={props.onList} aria-label={t("staff.view.list")} title={t("staff.view.list")}>
            <List className="size-4" />
          </Button>
          <Button className="pointer-events-auto" variant="outline" size="icon" onClick={() => setPanel((p) => !p)} aria-label={t("org.panel")}>
            {panel ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
          </Button>
        </div>

        {/* brend jamoalari filtri */}
        <div className="glass absolute bottom-4 left-1/2 z-10 flex max-w-[calc(100%-360px)] -translate-x-1/2 items-center gap-1 overflow-x-auto rounded-2xl border p-1.5 shadow-lg">
          <ProjectButton active={active === "all"} onClick={() => changeProject("all")} label={t("staff.all")} count={data.people.length} />
          {data.projects.map((p) => (
            <ProjectButton key={p.id} active={active === p.id} onClick={() => changeProject(p.id)} label={p.name} count={index.byProject.get(p.id)?.length ?? 0} />
          ))}
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
              <StaffPanel {...props} selected={selected} tree={tree} projects={projects} onSelect={select} />
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  );
}

function ProjectButton({ active, onClick, label, count }: { active: boolean; onClick: () => void; label: string; count: number }) {
  return (
    <button
      type="button" onClick={onClick}
      className={cn("flex h-8 shrink-0 items-center gap-2 rounded-xl px-3 text-xs hover:bg-muted", active && "bg-primary text-primary-foreground hover:bg-primary")}
    >
      <span className="font-medium">{label}</span>
      <span className={cn("font-mono", active ? "text-primary-foreground/80" : "text-muted-foreground")}>{count}</span>
    </button>
  );
}

export function StaffMap(props: StaffMapProps) {
  return (
    <ReactFlowProvider>
      <MapCanvas {...props} />
    </ReactFlowProvider>
  );
}

/* ================================================================== o'ng panel */
function Row({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="-mx-2 flex w-[calc(100%+1rem)] items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-muted">
      {children}
    </button>
  );
}

function Stats({ items }: { items: [string, ReactNode, boolean?][] }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {items.map(([label, value, warn]) => (
        <div key={label} className="rounded-lg border bg-muted/40 px-3 py-2">
          <div className={cn("font-mono text-lg font-semibold", warn && "text-destructive")}>{value}</div>
          <div className="text-[11px] text-muted-foreground">{label}</div>
        </div>
      ))}
    </div>
  );
}

function PersonRow({ person: p, onSelect, extra }: { person: StaffPerson; onSelect: (k: string) => void; extra?: ReactNode }) {
  const t = useTranslations("staff");
  return (
    <Row onClick={() => onSelect(key("person", p.id))}>
      <RoleChip role={p.role} vacancy={p.is_vacancy} />
      <span className={cn("min-w-0 flex-1 truncate", p.is_vacancy && "text-destructive")}>{p.is_vacancy ? t("vacancy") : p.name}</span>
      <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{extra ?? p.territory}</span>
    </Row>
  );
}

function Header({ icon, title, sub, actions }: { icon: ReactNode; title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="border-b px-5 py-5">
      <div className="flex items-start gap-3">
        {icon}
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold leading-tight">{title}</h2>
          {sub && <p className="mt-0.5 text-[13px] text-muted-foreground">{sub}</p>}
        </div>
      </div>
      {actions && <div className="mt-3 flex flex-wrap gap-1.5">{actions}</div>}
    </div>
  );
}

type PanelProps = StaffMapProps & { selected: string | null; tree: Tree; projects: StaffProject[]; onSelect: (k: string) => void };

function StaffPanel(props: PanelProps) {
  const { selected, tree } = props;
  if (selected && tree.parent.has(selected)) {
    const kind = kindOf(selected);
    if (kind === "person") return <PersonPanel {...props} personId={idOf(selected)} />;
    if (kind === "project") return <ProjectPanel {...props} projectId={idOf(selected)} />;
    if (kind === "unit") return <UnitPanel {...props} unitId={idOf(selected)} />;
  }
  return <OverviewPanel {...props} />;
}

function OverviewPanel({ index, tree, projects, canEdit, onSelect, onNewProject }: PanelProps) {
  const t = useTranslations("staff");
  const people = projects.flatMap((p) => index.byProject.get(p.id) ?? []);
  const vacant = people.filter((p) => p.is_vacancy);
  const roles = (Object.keys(ROLE_TONE) as StaffRole[]).filter((r) => people.some((p) => p.role === r));
  return (
    <>
      <Header
        icon={<span className="grid size-12 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary to-violet font-bold text-white">SG</span>}
        title="StarGroup" sub={t("panel.hint")}
        actions={canEdit ? <Button variant="outline" size="sm" onClick={onNewProject}><Plus className="size-4" />{t("newProject")}</Button> : undefined}
      />
      <PanelSection title={t("panel.overview")}>
        <Stats items={[[t("stats.seats"), tree.size.get(COMPANY) ?? 0], [t("stats.teams"), people.filter((p) => p.role === "SVR").length], [t("stats.vacancies"), vacant.length, vacant.length > 0]]} />
      </PanelSection>
      <PanelSection title={t("stats.projects")} count={projects.length}>
        {projects.map((p) => (
          <Row key={p.id} onClick={() => onSelect(key("project", p.id))}>
            <Building2 className="size-4 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate">{p.name}</span>
            <span className="font-mono text-[11px] text-muted-foreground">{tree.size.get(key("project", p.id)) ?? 0}</span>
            {(tree.vacancies.get(key("project", p.id)) ?? 0) > 0 && <span className="font-mono text-[11px] text-destructive">{tree.vacancies.get(key("project", p.id))}</span>}
          </Row>
        ))}
      </PanelSection>
      <PanelSection title={t("panel.openVacancies")} count={vacant.length}>
        {vacant.slice(0, 12).map((p) => <PersonRow key={p.id} person={p} onSelect={onSelect} extra={`${index.project.get(p.project)?.name} · ${p.territory}`} />)}
        {!vacant.length && <p className="text-sm text-muted-foreground">{t("panel.noVacancies")}</p>}
      </PanelSection>
      <PanelSection title={t("panel.legend")} className="border-b-0">
        <div className="grid gap-1.5">
          {roles.map((r) => (
            <div key={r} className="flex items-center gap-2.5 text-[13px]"><RoleChip role={r} /><span className="text-muted-foreground">{t(`roles.${r}`)}</span></div>
          ))}
        </div>
      </PanelSection>
    </>
  );
}

function ProjectPanel({ projectId, index, tree, canEdit, onSelect, onAdd, onEditProject, onSync }: PanelProps & { projectId: number }) {
  const t = useTranslations("staff");
  const locale = useLocale() as keyof typeof DATE_LOCALES;
  const project = index.project.get(projectId);
  if (!project) return null;
  const pk = key("project", projectId);
  const people = index.byProject.get(projectId) ?? [];
  const vac = tree.vacancies.get(pk) ?? 0;
  const tops = (tree.kids.get(pk) ?? []).filter((k) => kindOf(k) === "person").map((k) => index.person.get(idOf(k))!).filter(Boolean);
  const units = project.units.filter((u) => tree.parent.has(key("unit", u.id)) && (tree.size.get(key("unit", u.id)) ?? 0) > 0);
  return (
    <>
      <Header
        icon={<span className="grid size-12 shrink-0 place-items-center rounded-xl border bg-primary/10 text-primary"><Building2 className="size-5" /></span>}
        title={project.name}
        sub={project.synced_at
          ? t("synced", { when: formatDistanceToNow(new Date(project.synced_at), { addSuffix: true, locale: DATE_LOCALES[locale] }) })
          : project.description || undefined}
        actions={(
          <>
            {project.source_url && (
              <Button asChild variant="ghost" size="sm"><a href={project.source_url} target="_blank" rel="noreferrer"><ExternalLink className="size-4" />{t("source")}</a></Button>
            )}
            {canEdit && project.source_url && <Button variant="outline" size="sm" onClick={() => onSync(project)}><RefreshCw className="size-4" />{t("sync")}</Button>}
            {canEdit && <Button variant="outline" size="sm" onClick={() => onAdd(project.id)}><Plus className="size-4" />{t("addPerson")}</Button>}
            {canEdit && <Button variant="ghost" size="icon" className="size-8" onClick={() => onEditProject(project)} aria-label={t("editProject")}><Pencil className="size-4" /></Button>}
          </>
        )}
      />
      <PanelSection title={t("panel.overview")}>
        <Stats items={[[t("stats.seats"), people.length], [t("stats.teams"), people.filter((p) => p.role === "SVR").length], [t("stats.vacancies"), vac, vac > 0]]} />
      </PanelSection>
      {!!tops.length && (
        <PanelSection title={t("panel.leaders")} count={tops.length}>
          {tops.map((p) => <PersonRow key={p.id} person={p} onSelect={onSelect} />)}
        </PanelSection>
      )}
      <PanelSection title={t("panel.units")} count={units.length} className="border-b-0">
        {units.map((u) => (
          <Row key={u.id} onClick={() => onSelect(key("unit", u.id))}>
            <Users className="size-4 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate">{u.title}</span>
            <span className="font-mono text-[11px] text-muted-foreground">{tree.size.get(key("unit", u.id))}</span>
            <ArrowRight className="size-3.5 text-muted-foreground" />
          </Row>
        ))}
      </PanelSection>
    </>
  );
}

function UnitPanel({ unitId, index, tree, onSelect }: PanelProps & { unitId: number }) {
  const t = useTranslations("staff");
  const uk = key("unit", unitId);
  const project = [...index.project.values()].find((p) => p.units.some((u) => u.id === unitId));
  const people = (index.byProject.get(project?.id ?? -1) ?? []).filter((p) => p.unit === unitId);
  const kids = (tree.kids.get(uk) ?? []).filter((k) => kindOf(k) === "person").map((k) => index.person.get(idOf(k))!).filter(Boolean);
  const vac = people.filter((p) => p.is_vacancy).length;
  const parent = tree.parent.get(uk);
  const boss = parent && kindOf(parent) === "person" ? index.person.get(idOf(parent)) : undefined;
  return (
    <>
      <Header
        icon={<span className="grid size-12 shrink-0 place-items-center rounded-xl border text-muted-foreground"><Users className="size-5" /></span>}
        title={index.unit.get(unitId)}
        sub={project?.name}
      />
      <PanelSection title={t("panel.overview")}>
        <Stats items={[[t("stats.seats"), people.length], [t("stats.teams"), people.filter((p) => p.role === "SVR").length], [t("stats.vacancies"), vac, vac > 0]]} />
      </PanelSection>
      {boss && (
        <PanelSection title={t("fields.manager")}><PersonRow person={boss} onSelect={onSelect} /></PanelSection>
      )}
      <PanelSection title={t("panel.reports")} count={kids.length} className="border-b-0">
        {kids.map((p) => (
          <PersonRow key={p.id} person={p} onSelect={onSelect} extra={index.children.get(p.id)?.length ? `${p.territory} · ${index.children.get(p.id)!.length}` : undefined} />
        ))}
      </PanelSection>
    </>
  );
}

function PersonPanel({ personId, index, canEdit, onSelect, onOpen, onAssign, onVacate }: PanelProps & { personId: number }) {
  const t = useTranslations();
  const p = index.person.get(personId);
  if (!p) return null;
  const chain: StaffPerson[] = [];
  const seen = new Set([p.id]);
  for (let m = p.manager ? index.person.get(p.manager) : undefined; m && !seen.has(m.id); m = m.manager ? index.person.get(m.manager) : undefined) {
    chain.unshift(m);
    seen.add(m.id);
  }
  const reports = index.children.get(p.id) ?? [];
  const project = index.project.get(p.project);
  const rows: [string, ReactNode][] = ([
    [t("staff.panel.since"), p.since && !p.is_vacancy ? `${new Date(p.since).toLocaleDateString()} · ${tenure(p.since, (k, v) => t(`staff.tenure.${k}`, v))}` : ""],
    [t("staff.fields.position"), p.position],
    [t("staff.fields.territory"), p.territory && <span className="font-mono">{p.territory}</span>],
    [t("staff.fields.region"), p.region],
    [t("staff.fields.city"), p.city],
    [t("staff.fields.unit"), p.unit ? index.unit.get(p.unit) : ""],
    [t("staff.fields.project"), project?.name],
    [t("staff.fields.note"), p.note],
  ] as [string, ReactNode][]).filter(([, v]) => !!v);
  return (
    <>
      <Header
        icon={(
          <span className={cn("grid size-12 shrink-0 place-items-center rounded-full font-mono text-xs font-bold", p.is_vacancy ? "bg-destructive/12 text-destructive" : ROLE_TONE[p.role])}>
            {p.role}
          </span>
        )}
        title={<span className={cn(p.is_vacancy && "text-destructive")}>{p.is_vacancy ? t("staff.vacancy") : p.name}</span>}
        sub={t(`staff.roles.${p.role}`)}
        actions={canEdit && (
          p.is_vacancy ? (
            <>
              <Button size="sm" onClick={() => onAssign(p)}><UserPlus className="size-4" />{t("staff.staffing.assign")}</Button>
              <Button variant="ghost" size="sm" onClick={() => onOpen(p)}><Pencil className="size-4" />{t("common.edit")}</Button>
            </>
          ) : (
            <>
              <Button variant="outline" size="sm" onClick={() => onAssign(p)}><Repeat2 className="size-4" />{t("staff.staffing.replace")}</Button>
              <Button variant="outline" size="sm" className="text-destructive hover:text-destructive" onClick={() => onVacate(p)}>
                <UserMinus className="size-4" />{t("staff.staffing.vacate")}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => onOpen(p)}><Pencil className="size-4" />{t("common.edit")}</Button>
            </>
          )
        )}
      />
      {(p.phone || p.telegram || p.email) && (
        <PanelSection title={t("staff.panel.contact")}>
          <StaffContacts person={p} />
          {p.telegram && <p className="mt-2 font-mono text-xs text-muted-foreground">@{p.telegram}</p>}
          {p.email && (
            <a href={`mailto:${p.email}`} className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"><Mail className="size-3.5" />{p.email}</a>
          )}
        </PanelSection>
      )}
      <PanelSection title={t("staff.panel.details")}>
        <dl className="grid gap-1.5 text-[13px]">
          {rows.map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3">
              <dt className="text-muted-foreground">{label}</dt><dd className="min-w-0 text-right">{value}</dd>
            </div>
          ))}
        </dl>
      </PanelSection>
      {!!chain.length && (
        <PanelSection title={t("staff.panel.chain")} count={chain.length}>
          {chain.map((m) => <PersonRow key={m.id} person={m} onSelect={onSelect} />)}
        </PanelSection>
      )}
      <PanelSection title={t("staff.panel.reports")} count={reports.length} className={cn(!p.history?.length && "border-b-0")}>
        {reports.map((m) => <PersonRow key={m.id} person={m} onSelect={onSelect} />)}
        {!reports.length && <p className="text-sm text-muted-foreground">{t("staff.panel.noReports")}</p>}
      </PanelSection>
      {!!p.history?.length && (
        <PanelSection title={t("staff.panel.history")} count={p.history.length} className="border-b-0">
          <ol className="relative ml-1.5 space-y-3 border-l pl-4">
            {p.history.map((h, i) => (
              <li key={i} className="relative text-[13px]">
                <span className="absolute -left-[21px] top-1.5 size-2 rounded-full border-2 border-background bg-muted-foreground" />
                <div className="flex items-center gap-1.5 font-medium"><History className="size-3.5 text-muted-foreground" />{h.name}</div>
                <div className="text-xs text-muted-foreground">
                  {[h.since && new Date(h.since).toLocaleDateString(), new Date(h.until).toLocaleDateString()].filter(Boolean).join(" — ")}
                  {h.reason && h.reason !== "edit" && h.reason !== "import" && ` · ${h.reason}`}
                  {h.reason === "import" && ` · ${t("staff.staffing.viaImport")}`}
                </div>
                {h.phone && <StaffContacts person={h} compact className="-ml-1.5 mt-0.5" />}
              </li>
            ))}
          </ol>
        </PanelSection>
      )}
    </>
  );
}
