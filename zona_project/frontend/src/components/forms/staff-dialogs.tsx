"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ExternalLink, FileUp, Link2, TriangleAlert, Loader2, Minus, Plus, Repeat2, SquarePen, Type } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { CheckboxField, FormDialog, fromId, NONE, Row, SelectField, TextareaField, TextField, toId } from "@/components/forms/form-kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { splitContact, StaffContacts } from "@/components/views/staff-shared";
import { queryKeys } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/client";
import { staffApi } from "@/lib/api/endpoints";
import type { StaffDiff, StaffImportBody, StaffPerson, StaffProject, StaffRole, StaffState } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STAFF_KEY = ["staff"] as const;
const ROLES: StaffRole[] = ["ROP", "ASM", "RSM", "SVR", "KAM", "TP", "MER", "OTHER"];

function useStaffRefresh() {
  const qc = useQueryClient();
  return () => Promise.all([qc.invalidateQueries({ queryKey: STAFF_KEY }), qc.invalidateQueries({ queryKey: ["events"] }),
    qc.invalidateQueries({ queryKey: queryKeys.state })]);
}

/* ------------------------------------------------------------------ xodim */
const personSchema = z.object({
  name: z.string().max(150),
  is_vacancy: z.boolean(),
  role: z.string(),
  position: z.string().max(80),
  territory: z.string().max(80),
  city: z.string().max(80),
  region: z.string().max(80),
  phone: z.string().max(40),
  email: z.union([z.literal(""), z.string().email()]),
  telegram: z.string().max(80),
  since: z.string(),
  unit: z.string(),
  manager: z.string(),
  note: z.string().max(255),
});
type PersonValues = z.infer<typeof personSchema>;

export function PersonDialog({ open, onOpenChange, state, projectId, person }: {
  open: boolean; onOpenChange: (o: boolean) => void; state: StaffState; projectId: number; person?: StaffPerson;
}) {
  const t = useTranslations("staff");
  const refresh = useStaffRefresh();
  const project = state.projects.find((p) => p.id === projectId);
  const form = useForm<PersonValues>({ resolver: zodResolver(personSchema) });
  const vacancy = useWatch({ control: form.control, name: "is_vacancy" });

  useEffect(() => {
    if (!open) return;
    form.reset({
      name: person?.name ?? "", is_vacancy: person?.is_vacancy ?? false, role: person?.role ?? "TP", position: person?.position ?? "",
      territory: person?.territory ?? "", city: person?.city ?? "", region: person?.region ?? "", phone: person?.phone ?? "",
      email: person?.email ?? "", telegram: person?.telegram ?? "", since: person?.since ?? "", unit: fromId(person?.unit), manager: fromId(person?.manager), note: person?.note ?? "",
    });
  }, [open, person, form]);

  const save = useMutation({
    mutationFn: (v: PersonValues) => {
      const body = { ...v, role: v.role as StaffRole, unit: toId(v.unit), manager: toId(v.manager), project: projectId, since: v.since || null };
      return person ? staffApi.people.update(person.id, body) : staffApi.people.create(body);
    },
    onSuccess: async () => { await refresh(); toast.success(t("saved")); onOpenChange(false); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: () => staffApi.people.remove(person!.id),
    onSuccess: async () => { await refresh(); toast.success(t("deleted")); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const label = (p: StaffPerson) => `${p.is_vacancy ? t("vacancy") : p.name} · ${p.role}${p.territory ? ` · ${p.territory}` : ""}`;
  const managers = state.people.filter((p) => p.project === projectId && p.id !== person?.id && p.role !== "TP");

  return (
    <FormDialog
      wide open={open} onOpenChange={onOpenChange}
      title={person ? (person.is_vacancy ? `${t("vacancy")} · ${person.territory}` : person.name) : t("addPerson")}
      description={project?.name}
      onSubmit={form.handleSubmit((v) => save.mutate(v))} submitting={save.isPending}
      onDelete={person ? () => remove.mutateAsync() : undefined}
    >
      <Row>
        <TextField control={form.control} name="name" label={t("fields.name")} placeholder={vacancy ? t("vacancy") : ""} />
        <TextField control={form.control} name="territory" label={t("fields.territory")} description={t("territoryHint")} />
      </Row>
      <CheckboxField control={form.control} name="is_vacancy" label={t("isVacancy")} description={t("isVacancyHint")} />
      <Row>
        <SelectField control={form.control} name="role" label={t("fields.role")} options={ROLES.map((r) => ({ value: r, label: `${r} — ${t(`roles.${r}`)}` }))} />
        <TextField control={form.control} name="position" label={t("fields.position")} />
      </Row>
      <Row>
        <TextField control={form.control} name="phone" label={t("fields.phone")} placeholder="+998 90 123 45 67" />
        <TextField control={form.control} name="telegram" label={t("fields.telegram")} placeholder="@username" description={t("telegramHint")} />
      </Row>
      <Row>
        <TextField control={form.control} name="email" label="Email" />
        <TextField control={form.control} name="since" type="date" label={t("fields.since")} />
      </Row>
      <Row>
        <TextField control={form.control} name="city" label={t("fields.city")} />
        <TextField control={form.control} name="region" label={t("fields.region")} />
      </Row>
      <Row>
        <SelectField
          control={form.control} name="unit" label={t("fields.unit")}
          options={[{ value: NONE, label: "—" }, ...(project?.units ?? []).map((u) => ({ value: String(u.id), label: u.title }))]}
        />
        <SelectField
          control={form.control} name="manager" label={t("fields.manager")}
          options={[{ value: NONE, label: "—" }, ...managers.map((p) => ({ value: String(p.id), label: label(p) }))]}
        />
      </Row>
      <TextareaField control={form.control} name="note" label={t("fields.note")} rows={2} />
    </FormDialog>
  );
}

/* ------------------------------------------------------------------ tayinlash / almashtirish */
const today = () => new Date().toLocaleDateString("sv-SE"); // YYYY-MM-DD (mahalliy vaqt)
const REASONS = ["own", "fired", "moved", "transfer", "leave"] as const;

function ReasonChips({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const t = useTranslations("staff.staffing");
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {REASONS.map((r) => {
          const label = t(`reasons.${r}`);
          return (
            <button
              key={r} type="button" onClick={() => onChange(value === label ? "" : label)}
              className={cn("rounded-full border px-2.5 py-1 text-xs transition-colors", value === label ? "border-primary bg-primary text-primary-foreground" : "hover:border-primary/50")}
            >
              {label}
            </button>
          );
        })}
      </div>
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={t("reasonOther")} maxLength={120} />
    </div>
  );
}

const EMPTY_ASSIGN = { name: "", phone: "", telegram: "", since: "", reason: "" };

/**
 * Bo'sh o'ringa xodim tayinlash yoki o'rindagini almashtirish — faqat kerakli maydonlar.
 * Ism, telefon va @telegram bitta qatorga joylashtirilsa ham o'zi ajratadi.
 */
export function AssignDialog({ open, onOpenChange, person }: { open: boolean; onOpenChange: (o: boolean) => void; person: StaffPerson }) {
  const t = useTranslations("staff");
  const refresh = useStaffRefresh();
  const replacing = !person.is_vacancy;
  const [v, setV] = useState(EMPTY_ASSIGN);
  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) setV({ ...EMPTY_ASSIGN, since: today() });
  }
  const set = (patch: Partial<typeof v>) => setV((cur) => ({ ...cur, ...patch }));
  // bitta qatorga joylangan "Ism +998... @user" ni maydonlarga ajratish
  const smartName = (text: string) => {
    const parts = splitContact(text);
    if (parts.phone || parts.telegram) setV((cur) => ({ ...cur, name: parts.name, phone: cur.phone || parts.phone, telegram: cur.telegram || parts.telegram }));
    else set({ name: text });
  };
  const save = useMutation({
    mutationFn: () => staffApi.assign(person.id, { ...v, since: v.since || null }),
    onSuccess: async (p) => { await refresh(); toast.success(t("staffing.assigned", { name: p.name })); onOpenChange(false); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const seat = [person.role, person.territory].filter(Boolean).join(" · ");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{replacing ? t("staffing.replaceTitle", { name: person.name }) : t("staffing.assignTitle", { seat })}</DialogTitle>
          <DialogDescription>{replacing ? seat : t("staffing.assignHint")}</DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (v.name.trim()) save.mutate(); }}>
          <div className="space-y-1.5">
            <Label htmlFor="as-name">{t("fields.name")}</Label>
            <Input
              id="as-name" autoFocus value={v.name} maxLength={200}
              onChange={(e) => set({ name: e.target.value })}
              onPaste={(e) => { e.preventDefault(); smartName(`${v.name} ${e.clipboardData.getData("text")}`.trim()); }}
              onBlur={(e) => smartName(e.target.value)}
              placeholder={t("staffing.namePlaceholder")}
            />
            <p className="text-xs text-muted-foreground">{t("staffing.pasteHint")}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="as-phone">{t("fields.phone")}</Label>
              <Input id="as-phone" type="tel" inputMode="tel" value={v.phone} onChange={(e) => set({ phone: e.target.value })} placeholder="+998 90 123 45 67" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="as-tg">{t("fields.telegram")}</Label>
              <Input id="as-tg" value={v.telegram} onChange={(e) => set({ telegram: e.target.value })} placeholder={t("staffing.telegramPlaceholder")} />
            </div>
          </div>
          {v.phone && <StaffContacts person={{ phone: v.phone, telegram: v.telegram }} compact />}
          <div className="space-y-1.5">
            <Label htmlFor="as-since">{t("fields.since")}</Label>
            <Input id="as-since" type="date" value={v.since} onChange={(e) => set({ since: e.target.value })} className="w-44" />
          </div>
          {replacing && (
            <div className="space-y-1.5">
              <Label>{t("staffing.replaceReason", { name: person.name })}</Label>
              <ReasonChips value={v.reason} onChange={(reason) => set({ reason })} />
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>{t("back")}</Button>
            <Button type="submit" disabled={!v.name.trim() || save.isPending}>
              {save.isPending && <Loader2 className="size-4 animate-spin" />}{replacing ? t("staffing.replace") : t("staffing.assign")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Xodim ishdan bo'shadi: bir bosish — o'rin vakansiya bo'ladi, odam o'rin tarixiga yoziladi. */
export function VacateDialog({ open, onOpenChange, person }: { open: boolean; onOpenChange: (o: boolean) => void; person: StaffPerson }) {
  const t = useTranslations("staff");
  const refresh = useStaffRefresh();
  const [reason, setReason] = useState("");
  const [date, setDate] = useState("");
  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setReason("");
      setDate(today());
    }
  }
  const save = useMutation({
    mutationFn: () => staffApi.vacate(person.id, { reason, date: date || null }),
    onSuccess: async () => { await refresh(); toast.success(t("staffing.vacated")); onOpenChange(false); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("staffing.vacateTitle", { name: person.name })}</DialogTitle>
          <DialogDescription>{t("staffing.vacateHint", { name: person.name })}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>{t("staffing.reason")}</Label>
            <ReasonChips value={reason} onChange={setReason} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="va-date">{t("staffing.date")}</Label>
            <Input id="va-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-44" />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>{t("back")}</Button>
          <Button type="button" variant="destructive" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 className="size-4 animate-spin" />}{t("staffing.vacateBtn")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ jamoa (brend) */
const projectSchema = z.object({
  name: z.string().trim().min(1).max(80),
  description: z.string().max(200),
  source_url: z.union([z.literal(""), z.string().url()]),
});
type ProjectValues = z.infer<typeof projectSchema>;

export function ProjectDialog({ open, onOpenChange, project }: { open: boolean; onOpenChange: (o: boolean) => void; project?: StaffProject }) {
  const t = useTranslations("staff");
  const refresh = useStaffRefresh();
  const form = useForm<ProjectValues>({ resolver: zodResolver(projectSchema) });
  useEffect(() => {
    if (open) form.reset({ name: project?.name ?? "", description: project?.description ?? "", source_url: project?.source_url ?? "" });
  }, [open, project, form]);
  const save = useMutation({
    mutationFn: (v: ProjectValues) => (project ? staffApi.projects.update(project.id, v) : staffApi.projects.create(v)),
    onSuccess: async () => { await refresh(); toast.success(t("saved")); onOpenChange(false); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: () => staffApi.projects.remove(project!.id),
    onSuccess: async () => { await refresh(); toast.success(t("deleted")); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <FormDialog
      open={open} onOpenChange={onOpenChange} title={project ? project.name : t("newProject")}
      onSubmit={form.handleSubmit((v) => save.mutate(v))} submitting={save.isPending}
      onDelete={project ? () => remove.mutateAsync() : undefined} deleteConfirm={t("deleteProjectConfirm")}
    >
      <TextField control={form.control} name="name" label={t("fields.projectName")} />
      <TextField control={form.control} name="source_url" label={t("fields.source")} placeholder="https://..." description={t("sourceHint")} />
      <TextField control={form.control} name="description" label={t("fields.description")} />
    </FormDialog>
  );
}

/* ------------------------------------------------------------------ import */
export interface ImportPreset {
  project: number | null;
  /** Saqlangan manba linkidan qayta o'qish. */
  sync?: boolean;
}

type Source = "url" | "file" | "text";

async function toBase64(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

/** Server ocha olmaydigan (faqat brauzerda, hisob orqali ochiladigan) sahifalar. */
/** Linklarni solishtirish uchun: #bo'lim, oxirgi "/" va bo'shliqlarsiz. */
const sameLink = (a: string, b: string) => !!a && !!b && a.trim().replace(/[#?].*$/, "").replace(/\/+$/, "") === b.trim().replace(/[#?].*$/, "").replace(/\/+$/, "");

export const browserOnly = (url: string) => /^https?:\/\/(www\.)?claude\.ai\/(artifact|public\/artifacts)\//i.test(url.trim());

/** Claude artifact kabi sahifa: ochib, Ctrl+A / Ctrl+C qilib, shu yerga joylash — joylanishi bilan tahlil boshlanadi. */
function PasteFromPage({ url, value, onChange, onPasted }: { url: string; value: string; onChange: (v: string) => void; onPasted: (v: string) => void }) {
  const t = useTranslations("staff.paste");
  return (
    <div className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-4">
      <div className="text-sm font-medium">{t("title")}</div>
      <ol className="grid gap-2 text-sm sm:grid-cols-3">
        {[1, 2, 3].map((n) => (
          <li key={n} className="flex gap-2 rounded-md border bg-card px-3 py-2">
            <span className="grid size-5 shrink-0 place-items-center rounded-full bg-primary text-[11px] font-bold text-primary-foreground">{n}</span>
            <span className="text-[13px] leading-snug">{t(`step${n}`)}</span>
          </li>
        ))}
      </ol>
      <Button asChild variant="outline" size="sm">
        <a href={url} target="_blank" rel="noopener noreferrer"><ExternalLink className="size-4" />{t("open")}</a>
      </Button>
      <Textarea
        rows={5} className="max-h-40 text-xs" placeholder={t("placeholder")} value={value}
        onChange={(e) => onChange(e.target.value)}
        onPaste={(e) => {
          const pasted = e.clipboardData.getData("text");
          if (pasted.trim().length > 50) {
            e.preventDefault();
            onChange(pasted);
            onPasted(pasted);
          }
        }}
      />
      {!!value && <p className="text-xs text-muted-foreground">{t("chars", { count: value.length })}</p>}
    </div>
  );
}

export function ImportDialog({ open, onOpenChange, preset, projects }: {
  open: boolean; onOpenChange: (o: boolean) => void; preset: ImportPreset; projects: StaffProject[];
}) {
  const t = useTranslations("staff");
  const refresh = useStaffRefresh();
  const syncProject = preset.sync ? projects.find((p) => p.id === preset.project) : undefined;
  const [source, setSource] = useState<Source>("url");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [target, setTarget] = useState<string>(preset.project ? String(preset.project) : NONE);
  const [name, setName] = useState("");
  const [preview, setPreview] = useState<StaffDiff[] | null>(null);
  const [pageText, setPageText] = useState("");
  const syncBrowserOnly = !!syncProject && browserOnly(syncProject.source_url);
  const urlBrowserOnly = source === "url" && browserOnly(url);

  const body = async (pasted?: string): Promise<StaffImportBody> => {
    const common = { project: toId(target), name: name.trim() || undefined };
    if (source === "url") return { ...common, url: url.trim(), ...(browserOnly(url) ? { text: pasted ?? pageText } : {}) };
    if (source === "text") return { ...common, text };
    if (!file) throw new Error(t("chooseFile"));
    return { ...common, file_b64: await toBase64(file), filename: file.name };
  };

  const run = useMutation({
    mutationFn: async ({ apply, pasted }: { apply: boolean; pasted?: string }) => (syncProject
      ? staffApi.sync(syncProject.id, apply, syncBrowserOnly ? pasted ?? pageText : "")
      : staffApi.import({ ...(await body(pasted)), apply })),
    onSuccess: async (res, { apply }) => {
      if (!apply) {
        setPreview(res.projects);
        return;
      }
      await refresh();
      toast.success(t("applied", { count: res.projects.length }));
      onOpenChange(false);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  // manba linki saqlangan jamoa uchun: darhol farqlarni ko'rsatamiz
  useEffect(() => {
    if (syncProject && !syncBrowserOnly) run.mutate({ apply: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pageReady = pageText.trim().length > 50;
  const ready = syncProject
    ? !syncBrowserOnly || pageReady
    : source === "url" ? /^https?:\/\//.test(url.trim()) && (!urlBrowserOnly || pageReady) : source === "text" ? text.trim().length > 10 : !!file;
  const autoPreview = (pasted: string) => run.mutate({ apply: false, pasted });
  const changes = preview?.reduce((n, d) => n + d.summary.added + d.summary.removed + d.summary.replaced + d.summary.changed + (d.project.exists ? 0 : 1), 0) ?? 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{syncProject ? t("syncTitle", { name: syncProject.name }) : t("importTitle")}</DialogTitle>
          <DialogDescription>{syncProject ? syncProject.source_url : t("importHint")}</DialogDescription>
        </DialogHeader>

        {!syncProject && !preview && (
          <div className="space-y-4">
            <Tabs value={source} onValueChange={(v) => setSource(v as Source)}>
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="url"><Link2 className="size-4" />{t("src.url")}</TabsTrigger>
                <TabsTrigger value="file"><FileUp className="size-4" />{t("src.file")}</TabsTrigger>
                <TabsTrigger value="text"><Type className="size-4" />{t("src.text")}</TabsTrigger>
              </TabsList>
            </Tabs>
            {source === "url" && (
              <div className="space-y-1.5">
                <Input
                  placeholder="https://..." value={url} autoFocus
                  onChange={(e) => {
                    const v = e.target.value;
                    setUrl(v);
                    // link qaysi jamoaning manbasi bo'lsa — o'sha jamoa; yangi link — yangi jamoa (boshqasining ustiga yozilmasin)
                    const owner = projects.find((p) => sameLink(p.source_url, v));
                    if (v.trim()) setTarget(owner ? String(owner.id) : NONE);
                  }}
                />
                {(() => {
                  const owner = projects.find((p) => sameLink(p.source_url, url));
                  return owner ? <p className="text-xs text-success">{t("linkOwner", { name: owner.name })}</p> : null;
                })()}
                {!urlBrowserOnly && <p className="text-xs text-muted-foreground">{t("urlHint")}</p>}
                {urlBrowserOnly && <PasteFromPage url={url} value={pageText} onChange={setPageText} onPasted={autoPreview} />}
              </div>
            )}
            {source === "file" && (
              <div className="space-y-1.5">
                <Input type="file" accept=".xlsx,.json,.html,.htm,.csv,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                <p className="text-xs text-muted-foreground">{t("fileHint")}</p>
              </div>
            )}
            {source === "text" && (
              <div className="space-y-1.5">
                <Textarea rows={7} className="font-mono text-xs" placeholder={t("textPlaceholder")} value={text} onChange={(e) => setText(e.target.value)} />
                <p className="text-xs text-muted-foreground">{t("textHint")}</p>
              </div>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>{t("target")}</Label>
                <Select value={target} onValueChange={setTarget}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>{t("targetAuto")}</SelectItem>
                    {projects.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              {target === NONE && (
                <div className="space-y-1.5">
                  <Label>{t("fields.projectName")}</Label>
                  <Input placeholder={t("nameAuto")} value={name} onChange={(e) => setName(e.target.value)} />
                </div>
              )}
            </div>
          </div>
        )}

        {syncBrowserOnly && !preview && <PasteFromPage url={syncProject.source_url} value={pageText} onChange={setPageText} onPasted={autoPreview} />}
        {run.isPending && !preview && <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />{t("reading")}</div>}
        {preview && <Preview diffs={preview} />}

        <DialogFooter className="gap-2">
          {preview && (!syncProject || syncBrowserOnly) && <Button variant="ghost" onClick={() => setPreview(null)}>{t("back")}</Button>}
          {!preview ? (
            <Button disabled={!ready || run.isPending} onClick={() => run.mutate({ apply: false })}>
              {run.isPending && <Loader2 className="size-4 animate-spin" />}{t("previewBtn")}
            </Button>
          ) : (
            <Button disabled={run.isPending || !changes} onClick={() => run.mutate({ apply: true })}>
              {run.isPending && <Loader2 className="size-4 animate-spin" />}{changes ? t("apply") : t("noChanges")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Preview({ diffs }: { diffs: StaffDiff[] }) {
  const t = useTranslations("staff");
  const who = (name: string, territory: string) => (name || t("vacancy")) + (territory ? ` · ${territory}` : "");
  return (
    <div className="space-y-4">
      {diffs.filter((d) => d.project.exists && d.summary.removed >= 5 && d.summary.removed > d.summary.total / 2).map((d) => (
        <div key={`warn-${d.project.name}`} className="flex gap-2.5 rounded-lg border border-destructive/40 bg-destructive/8 px-4 py-3 text-sm text-destructive">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <span>{t("bigRemoval", { name: d.project.name, removed: d.summary.removed, added: d.summary.added })}</span>
        </div>
      ))}
      {diffs.map((d) => (
        <div key={d.project.name} className="rounded-lg border">
          <div className="flex flex-wrap items-center gap-2 border-b bg-muted/40 px-4 py-2.5">
            <span className="font-semibold">{d.project.name}</span>
            <Badge variant={d.project.exists ? "outline" : "default"}>{d.project.exists ? t("existing") : t("newOne")}</Badge>
            <span className="text-xs text-muted-foreground">{t("seats", { count: d.summary.total })} · {t("vacancies", { count: d.summary.vacancies })}</span>
            <div className="ml-auto flex flex-wrap gap-1.5 text-xs">
              <Stat icon={Plus} n={d.summary.added} cls="text-success" label={t("diff.added")} />
              <Stat icon={Minus} n={d.summary.removed} cls="text-destructive" label={t("diff.removed")} />
              <Stat icon={Repeat2} n={d.summary.replaced} cls="text-primary" label={t("diff.replaced")} />
              <Stat icon={SquarePen} n={d.summary.changed} cls="text-warning" label={t("diff.changed")} />
            </div>
          </div>
          <div className="max-h-72 space-y-3 overflow-y-auto px-4 py-3 text-sm">
            {!d.added.length && !d.removed.length && !d.replaced.length && !d.changed.length && (
              <p className="text-muted-foreground">{d.project.exists ? t("diff.none") : ""}</p>
            )}
            <DiffList title={t("diff.replaced")} items={d.replaced.map((r) => (
              <><span className="font-mono text-xs text-muted-foreground">{r.territory}</span> {r.from || t("vacancy")} <ArrowRight className="inline size-3" /> <b>{r.to || t("vacancy")}</b></>
            ))} />
            {d.project.exists && <DiffList title={t("diff.added")} cls="text-success" items={d.added.map((a) => <>+ {who(a.name, a.territory)}</>)} />}
            <DiffList title={t("diff.removed")} cls="text-destructive" items={d.removed.map((a) => <>− {who(a.name, a.territory)}</>)} />
            <DiffList title={t("diff.changed")} items={d.changed.map((c) => (
              <>{who(c.name, c.territory)}: <span className="text-muted-foreground">{c.changes.map((x) => `${t(`fields.${x.field}`)} ${x.from || "—"} → ${x.to || "—"}`).join("; ")}</span></>
            ))} />
          </div>
        </div>
      ))}
    </div>
  );
}

function Stat({ icon: Icon, n, cls, label }: { icon: typeof Plus; n: number; cls: string; label: string }) {
  return <span title={label} className={cn("flex items-center gap-0.5 rounded-full border px-2 py-0.5 font-mono", n ? cls : "text-muted-foreground")}><Icon className="size-3" />{n}</span>;
}

function DiffList({ title, items, cls }: { title: string; items: React.ReactNode[]; cls?: string }) {
  if (!items.length) return null;
  return (
    <div>
      <div className="mb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title} · {items.length}</div>
      <ul className={cn("space-y-0.5", cls)}>{items.slice(0, 100).map((it, i) => <li key={i}>{it}</li>)}</ul>
    </div>
  );
}
