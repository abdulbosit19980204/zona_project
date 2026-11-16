"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { Download, ExternalLink, FileJson, FileSpreadsheet, Network, Pencil, Phone, Plus, RefreshCw, Search, Upload, UserPlus, UserRound, Users } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
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

import { StaffMap } from "./staff-map";
import { buildIndex, matchesTerms, personLabel, RoleChip, searchTerms, STAFF_KEY, StaffContacts, type Index } from "./staff-shared";

export { STAFF_KEY };

/** Dala jamoalari: StarGroup ichidagi brendlar (Heinz, BIC, L'Oréal...) savdo tuzilmasi — ko'rish, qidirish, import/eksport. */
export function Staff() {
  const t = useTranslations("staff");
  const can = useCan();
  const query = useQuery({ queryKey: STAFF_KEY, queryFn: staffApi.state });
  const [active, setActive] = useState<number | "all">("all");
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState<{ person?: StaffPerson; project: number } | null>(null);
  const [projectEdit, setProjectEdit] = useState<StaffProject | null | undefined>(undefined);
  const [importing, setImporting] = useState<ImportPreset | null>(null);
  const [staffing, setStaffing] = useState<{ kind: "assign" | "vacate"; id: number } | null>(null);

  const data = query.data;
  const index = useMemo(() => buildIndex(data), [data]);
  const projects = data?.projects ?? [];
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

function PersonLine({ person: p, onOpen, onAssign, compact }: {
  person: StaffPerson; onOpen?: (p: StaffPerson) => void; onAssign?: (p: StaffPerson) => void; compact?: boolean;
}) {
  const t = useTranslations("staff");
  return (
    <div
      className={cn("group grid grid-cols-[auto_1fr_auto] items-start gap-x-2.5 px-3.5 py-2", onOpen && "cursor-pointer hover:bg-muted/50")}
      onClick={() => onOpen?.(p)}
    >
      <RoleChip role={p.role} vacancy={p.is_vacancy} />
      <div className="min-w-0">
        <div className={cn("truncate text-sm font-medium", p.is_vacancy && "text-destructive")}>{p.is_vacancy ? t("vacancy") : p.name}</div>
        <div className="flex flex-wrap gap-x-2.5 text-xs text-muted-foreground">
          <span className="font-mono">{p.territory || "—"}</span>
          {!compact && p.city && <span>{p.city}</span>}
          {p.phone && (
            <a href={`tel:${p.phone.replace(/\s/g, "")}`} onClick={(e) => e.stopPropagation()} className="font-mono hover:text-foreground">{p.phone}</a>
          )}
        </div>
      </div>
      <div className="flex items-center gap-0.5">
        {p.is_vacancy && onAssign ? (
          <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={(e) => { e.stopPropagation(); onAssign(p); }}>
            <UserPlus className="size-3.5" />{t("staffing.assignShort")}
          </Button>
        ) : (
          <StaffContacts person={p} compact className="opacity-60 group-hover:opacity-100" />
        )}
        {onOpen && <Pencil className="ml-1 size-3.5 text-muted-foreground opacity-0 group-hover:opacity-100" />}
      </div>
    </div>
  );
}

/** Bitta jamoa: yuqori rahbar → yo'nalishlar → supervayzer guruhlari (rahbarlik zanjiri bo'yicha). */
function ProjectView({ project, index, canEdit, onOpen, onAssign, onAdd, onEditProject, onSync }: {
  project: StaffProject; index: Index; canEdit: boolean; onAssign?: (p: StaffPerson) => void;
  onOpen: (p: StaffPerson) => void; onAdd: () => void; onEditProject: () => void; onSync: () => void;
}) {
  const t = useTranslations("staff");
  const locale = useLocale() as keyof typeof DATE_LOCALES;
  const people = index.byProject.get(project.id) ?? [];
  const roots = people.filter((p) => !p.manager || !index.person.has(p.manager));
  const open = canEdit ? onOpen : undefined;
  const sections = [...project.units.map((u) => ({ id: u.id as number | null, title: u.title })), { id: null, title: t("noUnit") }]
    .map((u) => ({ ...u, people: people.filter((p) => p.unit === u.id && !roots.includes(p)) }))
    .filter((s) => s.people.length);

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-end gap-x-4 gap-y-2 border-b-2 border-foreground pb-2">
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

      {!!roots.length && (
        <div className="mb-4 flex flex-wrap justify-center gap-3">
          {roots.map((r) => (
            <Card key={r.id} className="min-w-72 gap-0 border-2 border-foreground/80 p-0">
              <div className="px-3.5 pt-2.5 text-center text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">{t(`roles.${r.role}`)}</div>
              <PersonLine person={r} onOpen={open} onAssign={onAssign} />
            </Card>
          ))}
        </div>
      )}

      {sections.map((s) => <UnitBlock key={String(s.id)} title={s.title} people={s.people} index={index} onOpen={open} onAssign={onAssign} />)}
    </section>
  );
}

function UnitBlock({ title, people, index, onOpen, onAssign }: {
  title: string; people: StaffPerson[]; index: Index; onOpen?: (p: StaffPerson) => void; onAssign?: (p: StaffPerson) => void;
}) {
  const t = useTranslations("staff");
  const inUnit = new Set(people.map((p) => p.id));
  // guruh boshlig'i: shu yo'nalishda qo'l ostidagilari bor xodim (RSM, SVR...)
  const heads = people.filter((p) => (index.children.get(p.id) ?? []).some((c) => inUnit.has(c.id)));
  const headIds = new Set(heads.map((h) => h.id));
  const loose = people.filter((p) => !headIds.has(p.id) && !(p.manager && headIds.has(p.manager)));
  const looseByManager = new Map<number | null, StaffPerson[]>();
  for (const p of loose) looseByManager.set(p.manager, [...(looseByManager.get(p.manager) ?? []), p]);

  return (
    <div className="mb-5">
      <div className="mb-2 flex items-baseline gap-3">
        <h3 className="font-semibold">{title}</h3>
        <span className="text-xs text-muted-foreground">{t("seats", { count: people.length })}</span>
      </div>
      <div className="grid items-start gap-3 md:grid-cols-2 xl:grid-cols-3">
        {heads.map((h) => {
          const members = (index.children.get(h.id) ?? []).filter((c) => inUnit.has(c.id) && !headIds.has(c.id));
          return (
            <Card key={h.id} className="gap-0 overflow-hidden p-0">
              <div className={cn("border-b bg-muted/40", h.is_vacancy && "bg-destructive/5")}><PersonLine person={h} onOpen={onOpen} onAssign={onAssign} /></div>
              <div className="divide-y">{members.map((m) => <PersonLine key={m.id} person={m} onOpen={onOpen} onAssign={onAssign} compact />)}</div>
              {!members.length && <div className="px-3.5 py-2 text-xs text-muted-foreground">{t("subTeams", { count: (index.children.get(h.id) ?? []).length })}</div>}
            </Card>
          );
        })}
        {[...looseByManager.entries()].map(([mid, list]) => {
          const boss = mid ? index.person.get(mid) : undefined;
          return (
            <Card key={`loose-${mid}`} className="gap-0 overflow-hidden p-0">
              <div className="border-b bg-muted/40 px-3.5 py-2 text-xs text-muted-foreground">
                {boss ? t("directTo", { name: personLabel(boss, t("vacancy")) }) : t("noManager")}
              </div>
              <div className="divide-y">{list.map((m) => <PersonLine key={m.id} person={m} onOpen={onOpen} onAssign={onAssign} compact />)}</div>
            </Card>
          );
        })}
      </div>
    </div>
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
