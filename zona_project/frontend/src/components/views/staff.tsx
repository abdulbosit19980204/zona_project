"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { Building2, Download, ExternalLink, FileJson, FileSpreadsheet, Network, Pencil, Phone, Plus, RefreshCw, Search, Upload, UserPlus, UserRound, Users } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { DATE_LOCALES } from "@/components/common/activity";
import { EmptyState, Page, PageHeader, StatCard } from "@/components/common/page";
import { AssignDialog, ImportDialog, PersonDialog, ProjectDialog, VacateDialog, type ImportPreset } from "@/components/forms/staff-dialogs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCan } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/client";
import { staffApi } from "@/lib/api/endpoints";
import type { StaffPerson, StaffProject } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { buildTree, StaffMap, type StaffTree } from "./staff-map";
import { buildIndex, matchesTerms, personLabel, ROLE_TONE, RoleChip, searchTerms, STAFF_KEY, StaffContacts, type Index } from "./staff-shared";

export { STAFF_KEY };

/** Kontaktlar: StarGroup ichidagi brendlar (Heinz, BIC, L'Oréal...) savdo tuzilmasi — ko'rish, qidirish, import/eksport. */
export function Staff() {
  const t = useTranslations("staff");
  const can = useCan();
  const query = useQuery({ queryKey: STAFF_KEY, queryFn: staffApi.state });
  const [chosen, setActive] = useState<number | "all">("all");
  const params = useSearchParams();
  const initialQuery = params.get("q") ?? "";
  const [q, setQ] = useState(initialQuery);
  const [edit, setEdit] = useState<{ person?: StaffPerson; project: number } | null>(null);
  const [projectEdit, setProjectEdit] = useState<StaffProject | null | undefined>(undefined);
  const [importing, setImporting] = useState<ImportPreset | null>(null);
  const [staffing, setStaffing] = useState<{ kind: "assign" | "vacate"; id: number } | null>(null);

  const data = query.data;
  const index = useMemo(() => buildIndex(data), [data]);
  const projects = data?.projects ?? [];
  // tanlangan jamoa o'chirilgan bo'lsa — "Hammasi"ga qaytamiz
  const active = chosen !== "all" && !projects.some((p) => p.id === chosen) ? "all" : chosen;
  const current = active === "all" ? null : projects.find((p) => p.id === active) ?? null;
  const scoped = (data?.people ?? []).filter((p) => !current || p.project === current.id);

  const [view, setView] = useState<"map" | "list">("map");
  const terms = searchTerms(q);
  const found = terms.length ? scoped.filter((p) => matchesTerms(index, p, terms)) : [];

  const exporter = useMutation({
    mutationFn: ({ fmt }: { fmt: "xlsx" | "json" }) => staffApi.export(fmt, current?.id),
    onSuccess: (blob, { fmt }) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `tuzilma_${current?.name ?? "stargroup"}_${new Date().toISOString().slice(0, 10)}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const stats = {
    seats: scoped.length,
    vacancies: scoped.filter((p) => p.is_vacancy).length,
    teams: scoped.filter((p) => p.role === "SVR").length,
    projects: current ? 1 : projects.length,
  };

  const staffingPerson = staffing ? index.person.get(staffing.id) : undefined;
  const assign = can.edit ? (p: StaffPerson) => setStaffing({ kind: "assign", id: p.id }) : undefined;
  const dialogs = (
    <>
      {edit && data && (
        <PersonDialog open onOpenChange={(o) => !o && setEdit(null)} state={data} projectId={edit.project} person={edit.person} />
      )}
      <ProjectDialog open={projectEdit !== undefined} onOpenChange={(o) => !o && setProjectEdit(undefined)} project={projectEdit ?? undefined} />
      {importing && <ImportDialog open onOpenChange={(o) => !o && setImporting(null)} preset={importing} projects={projects} />}
      {staffingPerson && staffing?.kind === "assign" && <AssignDialog open onOpenChange={(o) => !o && setStaffing(null)} person={staffingPerson} />}
      {staffingPerson && staffing?.kind === "vacate" && <VacateDialog open onOpenChange={(o) => !o && setStaffing(null)} person={staffingPerson} />}
    </>
  );

  if (view === "map" && data && projects.length) {
    return (
      <>
        <StaffMap
          data={data} index={index} canEdit={can.edit} active={active} onActive={setActive}
          onOpen={(p) => setEdit({ person: p, project: p.project })}
          onAdd={(project) => setEdit({ project })}
          onEditProject={(project) => setProjectEdit(project)}
          onSync={(project) => setImporting({ project: project.id, sync: true })}
          onImport={() => setImporting({ project: current?.id ?? null })}
          onExport={(fmt) => exporter.mutate({ fmt })}
          exporting={exporter.isPending}
          onList={() => setView("list")}
          initialQuery={initialQuery}
          onNewProject={() => setProjectEdit(null)}
          onAssign={(p) => setStaffing({ kind: "assign", id: p.id })}
          onVacate={(p) => setStaffing({ kind: "vacate", id: p.id })}
        />
        {dialogs}
      </>
    );
  }

  return (
    <Page>
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={(
          <>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" disabled={!projects.length || exporter.isPending}><Download className="size-4" />{t("export")}</Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => exporter.mutate({ fmt: "xlsx" })}><FileSpreadsheet className="size-4" />Excel (.xlsx)</DropdownMenuItem>
                <DropdownMenuItem onClick={() => exporter.mutate({ fmt: "json" })}><FileJson className="size-4" />JSON</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            {can.edit && <Button onClick={() => setImporting({ project: current?.id ?? null })}><Upload className="size-4" />{t("import")}</Button>}
            {!!projects.length && <Button variant="outline" onClick={() => setView("map")}><Network className="size-4" />{t("view.map")}</Button>}
          </>
        )}
      />

      {query.isLoading && <Skeleton className="h-64 w-full" />}
      {data && !projects.length && (
        <EmptyState
          icon={Users} title={t("empty")} hint={t("emptyHint")}
          action={can.edit ? <Button onClick={() => setImporting({ project: null })}><Upload className="size-4" />{t("import")}</Button> : undefined}
        />
      )}

      {!!projects.length && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <ProjectChip active={active === "all"} onClick={() => setActive("all")} label={t("all")} count={data?.people.length ?? 0} />
            {projects.map((p) => (
              <ProjectChip key={p.id} active={active === p.id} onClick={() => setActive(p.id)} label={p.name} count={index.byProject.get(p.id)?.length ?? 0} />
            ))}
            {can.edit && (
              <Button variant="ghost" size="sm" onClick={() => setProjectEdit(null)}><Plus className="size-4" />{t("newProject")}</Button>
            )}
          </div>

          <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label={t("stats.seats")} value={stats.seats} icon={Users} />
            <StatCard label={t("stats.teams")} value={stats.teams} icon={UserRound} />
            <StatCard label={t("stats.vacancies")} value={stats.vacancies} tone={stats.vacancies ? "warning" : "default"} icon={UserRound} />
            <StatCard label={t("stats.projects")} value={stats.projects} icon={FileSpreadsheet} />
          </div>

          <div className="relative mb-5">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="h-10 pl-9" placeholder={t("searchPlaceholder")} value={q} onChange={(e) => setQ(e.target.value)} />
            {!!terms.length && <span className="absolute top-1/2 right-3 -translate-y-1/2 text-xs text-muted-foreground tabular-nums">{t("found", { count: found.length })}</span>}
          </div>

          {terms.length ? (
            <Results people={found} index={index} showProject={!current} onOpen={can.edit ? (p) => setEdit({ person: p, project: p.project }) : undefined} />
          ) : (
            <div className="space-y-8">
              {(current ? [current] : projects).map((project) => (
                <ProjectView
                  key={project.id} project={project} index={index} canEdit={can.edit}
                  onOpen={(p) => setEdit({ person: p, project: project.id })}
                  onAssign={assign}
                  onAdd={() => setEdit({ project: project.id })}
                  onEditProject={() => setProjectEdit(project)}
                  onSync={() => setImporting({ project: project.id, sync: true })}
                />
              ))}
            </div>
          )}
        </>
      )}

      {dialogs}
    </Page>
  );
}

function ProjectChip({ active, onClick, label, count }: { active: boolean; onClick: () => void; label: string; count: number }) {
  return (
    <button
      type="button" onClick={onClick}
      className={cn("flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors",
        active ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:border-primary/40")}
    >
      <span className="font-medium">{label}</span>
      <span className={cn("font-mono text-xs", active ? "text-primary-foreground/80" : "text-muted-foreground")}>{count}</span>
    </button>
  );
}

interface TreeHandlers {
  index: Index;
  tree: StaffTree;
  onOpen?: (p: StaffPerson) => void;
  onAssign?: (p: StaffPerson) => void;
}

/** Daraxtdagi xodim kartasi: rol, ism, hudud · shahar, telefon; vakansiyada — "Tayinlash". */
function PersonCard({ person: p, onOpen, onAssign, lead, reports }: {
  person: StaffPerson; onOpen?: (p: StaffPerson) => void; onAssign?: (p: StaffPerson) => void; lead?: boolean; reports?: number;
}) {
  const t = useTranslations("staff");
  return (
    <div
      className={cn(
        "group relative flex min-h-11 items-center gap-2.5 rounded-xl border bg-card px-2.5 py-1.5 shadow-[0_6px_16px_-14px_rgba(0,0,0,0.6)] transition-colors",
        onOpen && "cursor-pointer hover:border-primary/50",
        lead && "border-foreground/20 bg-muted/40",
        p.is_vacancy && "border-dashed border-destructive/50 bg-destructive/5",
      )}
      onClick={() => onOpen?.(p)}
    >
      <span className={cn("grid size-8 shrink-0 place-items-center rounded-full font-mono text-[10px] font-bold", p.is_vacancy ? "bg-destructive/12 text-destructive" : ROLE_TONE[p.role])}>
        {p.role}
      </span>
      <div className="min-w-0 flex-1">
        <div className={cn("truncate text-[13px] font-semibold leading-tight", p.is_vacancy && "text-destructive")}>{p.is_vacancy ? t("vacancy") : p.name}</div>
        <div className="truncate text-[11.5px] text-muted-foreground">
          <span className="font-mono">{p.territory || t(`roles.${p.role}`)}</span>
          {p.city && ` · ${p.city}`}
          {!!reports && <span> · {t("seats", { count: reports })}</span>}
        </div>
      </div>
      {p.is_vacancy && onAssign ? (
        <Button size="sm" variant="outline" className="h-7 shrink-0 px-2 text-xs" onClick={(e) => { e.stopPropagation(); onAssign(p); }}>
          <UserPlus className="size-3.5" />{t("staffing.assignShort")}
        </Button>
      ) : (
        <StaffContacts person={p} compact className="shrink-0 opacity-50 group-hover:opacity-100" />
      )}
    </div>
  );
}

/** Yo'nalish sarlavhasi (ustun boshi). */
function UnitPill({ title, size, vacancies }: { title: string; size: number; vacancies: number }) {
  const t = useTranslations("staff");
  return (
    <div className="mx-auto flex w-fit max-w-full items-center gap-2 rounded-full border bg-card px-3.5 py-1.5 shadow-sm">
      <Users className="size-3.5 shrink-0 text-primary" />
      <span className="truncate text-[13px] font-semibold">{title}</span>
      <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{size}</span>
      {vacancies > 0 && <span className="shrink-0 rounded-full bg-destructive/12 px-1.5 font-mono text-[10.5px] text-destructive">{t("vacancies", { count: vacancies })}</span>}
    </div>
  );
}

/** Tugun va uning bolalari — chapdagi chiziqlar bilan bog'langan ichma-ich daraxt. */
function Branch({ keys, h }: { keys: string[]; h: TreeHandlers }) {
  if (!keys.length) return null;
  return (
    <ul className="org-tree">
      {keys.map((k) => {
        const kids = h.tree.kids.get(k) ?? [];
        return (
          <li key={k}>
            <TreeNode k={k} h={h} lead={!!kids.length} />
            <Branch keys={kids} h={h} />
          </li>
        );
      })}
    </ul>
  );
}

function TreeNode({ k, h, lead }: { k: string; h: TreeHandlers; lead?: boolean }) {
  const [kind, raw] = k.split(":");
  const id = Number(raw);
  if (kind === "unit") return <UnitPill title={h.index.unit.get(id) ?? ""} size={h.tree.size.get(k) ?? 0} vacancies={h.tree.vacancies.get(k) ?? 0} />;
  const p = h.index.person.get(id);
  if (!p) return null;
  return <PersonCard person={p} onOpen={h.onOpen} onAssign={h.onAssign} lead={lead} reports={lead ? h.tree.size.get(k) : undefined} />;
}

/** Ustun: tepada yo'nalish (yoki guruh rahbari), ostida ichma-ich daraxt. */
function Column({ k, h }: { k: string; h: TreeHandlers }) {
  const kids = h.tree.kids.get(k) ?? [];
  return (
    <div className="org-col">
      <TreeNode k={k} h={h} lead={!!kids.length} />
      <Branch keys={kids} h={h} />
    </div>
  );
}

/** Bitta jamoa: yuqori rahbar → yo'nalishlar (ustunlar) → guruh rahbarlari → xodimlar, chiziqlar bilan bog'langan. */
function ProjectView({ project, index, canEdit, onOpen, onAssign, onAdd, onEditProject, onSync }: {
  project: StaffProject; index: Index; canEdit: boolean; onAssign?: (p: StaffPerson) => void;
  onOpen: (p: StaffPerson) => void; onAdd: () => void; onEditProject: () => void; onSync: () => void;
}) {
  const t = useTranslations("staff");
  const locale = useLocale() as keyof typeof DATE_LOCALES;
  const tree = useMemo(() => buildTree([project], index), [project, index]);
  const pk = `project:${project.id}`;
  const people = index.byProject.get(project.id) ?? [];
  const h: TreeHandlers = { index, tree, onOpen: canEdit ? onOpen : undefined, onAssign };
  const top = tree.kids.get(pk) ?? [];
  // bitta yuqori rahbar bo'lsa — u tepada, uning bolalari ustunlar; aks holda yuqori darajaning o'zi ustunlar
  const rootKey = top.length === 1 && top[0].startsWith("person:") ? top[0] : null;
  const columns = rootKey ? tree.kids.get(rootKey) ?? [] : top;
  const root = rootKey ? index.person.get(Number(rootKey.split(":")[1])) : undefined;

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-end gap-x-4 gap-y-2 border-b pb-2.5">
        <h2 className="text-xl font-bold">{project.name}</h2>
        <span className="text-sm text-muted-foreground">
          {t("seats", { count: people.length })} · {t("vacancies", { count: people.filter((p) => p.is_vacancy).length })}
        </span>
        {project.synced_at && (
          <span className="text-xs text-muted-foreground">
            {t("synced", { when: formatDistanceToNow(new Date(project.synced_at), { addSuffix: true, locale: DATE_LOCALES[locale] }) })}
          </span>
        )}
        <div className="ml-auto flex flex-wrap gap-1.5">
          {project.source_url && (
            <Button asChild variant="ghost" size="sm">
              <a href={project.source_url} target="_blank" rel="noreferrer"><ExternalLink className="size-4" />{t("source")}</a>
            </Button>
          )}
          {canEdit && project.source_url && <Button variant="outline" size="sm" onClick={onSync}><RefreshCw className="size-4" />{t("sync")}</Button>}
          {canEdit && <Button variant="outline" size="sm" onClick={onAdd}><Plus className="size-4" />{t("addPerson")}</Button>}
          {canEdit && <Button variant="ghost" size="icon" className="size-8" onClick={onEditProject} aria-label={t("editProject")}><Pencil className="size-4" /></Button>}
        </div>
      </div>

      {root && (
        <div className="flex flex-col items-center">
          <div className="mb-1.5 flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-0.5 text-[10.5px] font-semibold tracking-wider text-primary uppercase">
            <Building2 className="size-3" />{project.name}
          </div>
          <div className="w-full max-w-sm">
            <PersonCard person={root} onOpen={h.onOpen} onAssign={onAssign} lead reports={people.length - 1} />
          </div>
          {!!columns.length && <div className="h-6 border-l-[1.5px] border-[var(--edge-struct)]" />}
        </div>
      )}
      {!!columns.length && (
        <div className="org-cols">
          {columns.map((k) => <Column key={k} k={k} h={h} />)}
        </div>
      )}
    </section>
  );
}

function Results({ people, index, showProject, onOpen }: { people: StaffPerson[]; index: Index; showProject: boolean; onOpen?: (p: StaffPerson) => void }) {
  const t = useTranslations("staff");
  if (!people.length) return <EmptyState icon={Search} title={t("nothing")} />;
  return (
    <Card className="overflow-hidden p-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-16">{t("fields.role")}</TableHead>
            <TableHead>{t("fields.name")}</TableHead>
            <TableHead>{t("fields.territory")}</TableHead>
            <TableHead>{t("fields.city")}</TableHead>
            <TableHead>{t("fields.phone")}</TableHead>
            <TableHead>{t("fields.manager")}</TableHead>
            {showProject && <TableHead>{t("fields.project")}</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {people.slice(0, 200).map((p) => {
            const boss = p.manager ? index.person.get(p.manager) : undefined;
            return (
              <TableRow key={p.id} className={cn(onOpen && "cursor-pointer")} onClick={() => onOpen?.(p)}>
                <TableCell><RoleChip role={p.role} vacancy={p.is_vacancy} /></TableCell>
                <TableCell className={cn("font-medium", p.is_vacancy && "text-destructive")}>{p.is_vacancy ? t("vacancy") : p.name}</TableCell>
                <TableCell className="font-mono text-xs">{p.territory}</TableCell>
                <TableCell className="text-sm">{p.city}{p.unit && <span className="block text-xs text-muted-foreground">{index.unit.get(p.unit)}</span>}</TableCell>
                <TableCell>
                  {p.phone && (
                    <div className="flex items-center gap-1">
                      <a href={`tel:${p.phone.replace(/\s/g, "")}`} onClick={(e) => e.stopPropagation()} className="flex items-center gap-1 font-mono text-xs hover:text-primary">
                        <Phone className="size-3" />{p.phone}
                      </a>
                      <StaffContacts person={p} compact />
                    </div>
                  )}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{boss ? personLabel(boss, t("vacancy")) : "—"}</TableCell>
                {showProject && <TableCell><Badge variant="outline">{index.project.get(p.project)?.name}</Badge></TableCell>}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Card>
  );
}
