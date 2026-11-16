"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { CheckCircle2, CircleAlert, KeyRound, Languages, Loader2, Pencil, Plug, Plus, Sparkles, Zap } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { DATE_LOCALES } from "@/components/common/activity";
import { SectionTitle } from "@/components/common/page";
import { CheckboxField, FormDialog, fromId, NONE, NumberField, Row, SelectField, TextareaField, TextField, toId } from "@/components/forms/form-kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FieldGroup } from "@/components/ui/field";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { queryKeys } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/client";
import { adminApi } from "@/lib/api/endpoints";
import type { AIProvider, AIProviderKind, AITaskConfig, Effort } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const KEYS = {
  providers: ["admin", "ai", "providers"] as const,
  kinds: ["admin", "ai", "kinds"] as const,
  tasks: ["admin", "ai", "tasks"] as const,
  usage: ["admin", "ai", "usage"] as const,
  summary: ["admin", "ai", "summary"] as const,
  translate: ["admin", "ai", "translate"] as const,
};

/** AI ulanishlari: provayderlar (kalitlar shifrlangan holda saqlanadi), har bir vazifa uchun model, sarf. */
export function AiTab() {
  const t = useTranslations();
  const providers = useQuery({ queryKey: KEYS.providers, queryFn: adminApi.providers.list });
  const kinds = useQuery({ queryKey: KEYS.kinds, queryFn: adminApi.providers.kinds, staleTime: Infinity });
  const tasks = useQuery({ queryKey: KEYS.tasks, queryFn: adminApi.aiTasks.list });
  const [edit, setEdit] = useState<AIProvider | null | undefined>(undefined);
  const kindMap = new Map((kinds.data ?? []).map((k) => [k.kind, k]));

  return (
    <>
      <SectionTitle actions={<Button size="sm" onClick={() => setEdit(null)}><Plus className="size-4" />{t("ai.addProvider")}</Button>}>
        {t("ai.providers")}
      </SectionTitle>
      <p className="-mt-1 mb-3 text-sm text-muted-foreground">{t("ai.providersHint")}</p>
      {providers.data?.filter((p) => p.kind === "gemini" && !p.has_key).map((p) => (
        <Card key={`free-${p.id}`} className="mb-3 gap-2 border-primary/40 bg-primary/5 p-4">
          <div className="flex items-center gap-2 font-semibold"><Sparkles className="size-4 text-primary" />{t("ai.free.title")}</div>
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            <li>{t("ai.free.step1")} <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer" className="font-medium text-primary underline">aistudio.google.com/apikey</a></li>
            <li>{t("ai.free.step2")}</li>
            <li>{t("ai.free.step3")}</li>
          </ol>
          <p className="text-xs text-muted-foreground">{t("ai.free.note")}</p>
          <Button size="sm" className="w-fit" onClick={() => setEdit(p)}><KeyRound className="size-4" />{t("ai.free.enterKey")}</Button>
        </Card>
      ))}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {providers.data?.map((p) => <ProviderCard key={p.id} provider={p} kind={kindMap.get(p.kind)} onEdit={() => setEdit(p)} />)}
        {providers.data && !providers.data.length && (
          <Card className="items-center gap-2 border-dashed p-6 text-center text-sm text-muted-foreground md:col-span-2 xl:col-span-3">
            <Plug className="size-6" />{t("ai.noProviders")}
          </Card>
        )}
      </div>

      <SectionTitle>{t("ai.tasks")}</SectionTitle>
      <p className="-mt-1 mb-3 text-sm text-muted-foreground">{t("ai.tasksHint")}</p>
      <div className="grid gap-4 xl:grid-cols-3">
        {tasks.data?.map((c) => <TaskConfigCard key={c.task} config={c} providers={providers.data ?? []} kinds={kindMap} />)}
      </div>

      <TranslateSection />

      <UsageSection />
      <ProviderDialog open={edit !== undefined} onOpenChange={(o) => !o && setEdit(undefined)} provider={edit ?? undefined} kinds={kinds.data ?? []} />
    </>
  );
}

function ProviderCard({ provider: p, kind, onEdit }: { provider: AIProvider; kind?: AIProviderKind; onEdit: () => void }) {
  const t = useTranslations();
  const locale = useLocale() as keyof typeof DATE_LOCALES;
  const qc = useQueryClient();
  const test = useMutation({
    mutationFn: () => adminApi.providers.test(p.id),
    onSuccess: async (r) => {
      await qc.invalidateQueries({ queryKey: KEYS.providers });
      if (r.ok) toast.success(t("ai.testOk", { ms: r.latency_ms ?? 0, models: r.models?.length ?? 0 }));
      else toast.error(r.error ?? t("ai.testFail"));
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card className={cn("gap-3 p-4", !p.is_active && "opacity-60")}>
      <div className="flex items-start gap-3">
        <span className="grid size-9 place-items-center rounded-lg border bg-muted/50"><KeyRound className="size-4" /></span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold">{p.name}</div>
          <div className="truncate text-xs text-muted-foreground">{kind?.label ?? p.kind}</div>
        </div>
        <Button variant="ghost" size="icon" className="size-8" onClick={onEdit}><Pencil className="size-4" /></Button>
      </div>
      <div className="space-y-1 text-xs text-muted-foreground">
        <div className="truncate font-mono">{p.base_url || kind?.base_url || "—"}</div>
        <div className="font-mono">{p.has_key ? p.api_key_masked : t("ai.noKey")}</div>
      </div>
      <div className="mt-auto flex items-center gap-2 text-xs">
        {p.last_check_ok === true && <span className="flex items-center gap-1 text-success"><CheckCircle2 className="size-3.5" />{t("ai.connected")}</span>}
        {p.last_check_ok === false && <span className="flex min-w-0 items-center gap-1 text-destructive" title={p.last_error}><CircleAlert className="size-3.5 shrink-0" /><span className="truncate">{p.last_error || t("ai.testFail")}</span></span>}
        {p.last_check_at && <span className="text-muted-foreground">· {formatDistanceToNow(new Date(p.last_check_at), { addSuffix: true, locale: DATE_LOCALES[locale] })}</span>}
        <Button size="sm" variant="outline" className="ml-auto" disabled={test.isPending} onClick={() => test.mutate()}>
          {test.isPending ? <Loader2 className="size-4 animate-spin" /> : <Zap className="size-4" />}{t("ai.test")}
        </Button>
      </div>
    </Card>
  );
}

const providerSchema = z.object({
  kind: z.string().min(1),
  name: z.string().min(1).max(100),
  base_url: z.string().max(300),
  api_version: z.string().max(50),
  api_key: z.string().max(500),
  is_active: z.boolean(),
});
type ProviderValues = z.infer<typeof providerSchema>;

function ProviderDialog({ open, onOpenChange, provider, kinds }: {
  open: boolean; onOpenChange: (o: boolean) => void; provider?: AIProvider; kinds: AIProviderKind[];
}) {
  const t = useTranslations();
  const qc = useQueryClient();
  const form = useForm<ProviderValues>({ resolver: zodResolver(providerSchema) });
  const kind = useWatch({ control: form.control, name: "kind" });
  const preset = kinds.find((k) => k.kind === kind);

  useEffect(() => {
    if (!open) return;
    form.reset({
      kind: provider?.kind ?? kinds[0]?.kind ?? "anthropic", name: provider?.name ?? "", base_url: provider?.base_url ?? "",
      api_version: provider?.api_version ?? "", api_key: "", is_active: provider?.is_active ?? true,
    });
  }, [open, provider, kinds, form]);

  const done = async () => {
    await Promise.all([qc.invalidateQueries({ queryKey: KEYS.providers }), qc.invalidateQueries({ queryKey: queryKeys.state })]);
  };
  const save = useMutation({
    mutationFn: (v: ProviderValues) => {
      const body = { ...v, api_key: v.api_key || undefined };
      return provider ? adminApi.providers.update(provider.id, body) : adminApi.providers.create(body);
    },
    onSuccess: async () => { await done(); toast.success(t("settings.saved")); onOpenChange(false); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: () => adminApi.providers.remove(provider?.id ?? 0),
    onSuccess: done,
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <FormDialog
      wide open={open} onOpenChange={onOpenChange}
      title={provider ? provider.name : t("ai.addProvider")} description={preset?.hint}
      onSubmit={form.handleSubmit((v) => save.mutate(v))} submitting={save.isPending}
      onDelete={provider ? () => remove.mutateAsync() : undefined}
    >
      <Row>
        <SelectField control={form.control} name="kind" label={t("ai.kind")} options={kinds.map((k) => ({ value: k.kind, label: k.label }))} />
        <TextField control={form.control} name="name" label={t("ai.name")} placeholder={preset?.label} />
      </Row>
      <TextField
        control={form.control} name="api_key" label={t("ai.apiKey")} type="password"
        placeholder={provider?.has_key ? `${provider.api_key_masked} — ${t("ai.keepKey")}` : preset?.key === false ? t("ai.keyOptional") : "sk-..."}
        description={t("ai.keyHint")}
      />
      <Row>
        <TextField control={form.control} name="base_url" label={t("ai.baseUrl")} placeholder={preset?.base_url ?? "https://..."} description={t("ai.baseUrlHint")} />
        <TextField control={form.control} name="api_version" label={t("ai.apiVersion")} placeholder="—" />
      </Row>
      {preset?.docs && <a href={preset.docs} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">{t("ai.docs")} ↗</a>}
      <CheckboxField control={form.control} name="is_active" label={t("ai.active")} />
    </FormDialog>
  );
}

const taskSchema = z.object({
  enabled: z.boolean(),
  provider: z.string(),
  model: z.string().max(120),
  effort: z.string(),
  temperature: z.number().min(0).max(2).nullable(),
  max_tokens: z.number().int().min(64).max(64000),
  fallback_provider: z.string(),
  fallback_model: z.string().max(120),
  instructions: z.string().max(4000),
});
type TaskValues = z.infer<typeof taskSchema>;
const EFFORTS: Effort[] = ["", "low", "medium", "high", "xhigh", "max"];

function TaskConfigCard({ config, providers, kinds }: { config: AITaskConfig; providers: AIProvider[]; kinds: Map<string, AIProviderKind> }) {
  const t = useTranslations();
  const qc = useQueryClient();
  const form = useForm<TaskValues>({ resolver: zodResolver(taskSchema) });
  const providerId = useWatch({ control: form.control, name: "provider" });
  const provider = providers.find((p) => String(p.id) === providerId);
  const kind = provider ? kinds.get(provider.kind) : undefined;
  const models = [...new Set([...(kind?.models ?? []), ...(provider?.models_cache ?? [])])];

  useEffect(() => {
    form.reset({
      enabled: config.enabled, provider: fromId(config.provider), model: config.model, effort: config.effort || NONE,
      temperature: config.temperature, max_tokens: config.max_tokens, fallback_provider: fromId(config.fallback_provider),
      fallback_model: config.fallback_model, instructions: config.instructions,
    });
  }, [config, form]);

  const save = useMutation({
    mutationFn: (v: TaskValues) => adminApi.aiTasks.update(config.task, {
      ...v, provider: toId(v.provider), fallback_provider: toId(v.fallback_provider), effort: (v.effort === NONE ? "" : v.effort) as Effort,
    }),
    onSuccess: async () => {
      await Promise.all([qc.invalidateQueries({ queryKey: KEYS.tasks }), qc.invalidateQueries({ queryKey: queryKeys.state })]);
      toast.success(t("settings.saved"));
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const test = useMutation({
    mutationFn: () => adminApi.aiTasks.test(config.task),
    onSuccess: (r) => {
      if (r.ok) toast.success(`${r.meta.model} · ${r.meta.latency_ms} ms`, { description: (r.result.answer ?? r.result.text ?? "").slice(0, 160) });
      else toast.error(r.error);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const providerOptions = [{ value: NONE, label: "—" }, ...providers.map((p) => ({ value: String(p.id), label: p.name }))];

  return (
    <Card className="gap-4 p-5">
      <div>
        <div className="flex items-center gap-2 font-semibold">{t(`ai.task.${config.task}`)}<Badge variant="outline" className="font-mono text-[10px]">{config.task}</Badge></div>
        <p className="text-xs text-muted-foreground">{t(`ai.taskHint.${config.task}`)}</p>
      </div>
      <form noValidate onSubmit={form.handleSubmit((v) => save.mutate(v))}>
        <FieldGroup>
          <CheckboxField control={form.control} name="enabled" label={t("ai.enabled")} />
          <SelectField control={form.control} name="provider" label={t("ai.provider")} options={providerOptions} />
          <TextField control={form.control} name="model" label={t("ai.model")} placeholder={models[0] ?? "model-id"} />
          {!!models.length && (
            <div className="-mt-3 flex flex-wrap gap-1">
              {models.slice(0, 8).map((m) => (
                <button key={m} type="button" onClick={() => form.setValue("model", m, { shouldDirty: true })} className="rounded border px-1.5 py-0.5 font-mono text-[10.5px] text-muted-foreground hover:border-primary/40 hover:text-foreground">{m}</button>
              ))}
            </div>
          )}
          <Row>
            <SelectField
              control={form.control} name="effort" label={t("ai.effort")}
              options={EFFORTS.map((e) => ({ value: e || NONE, label: e || t("ai.default") }))}
              description={kind?.effort ? undefined : t("ai.effortNa")}
            />
            <NumberField control={form.control} name="max_tokens" label={t("ai.maxTokens")} />
          </Row>
          <NumberField control={form.control} name="temperature" label={t("ai.temperature")} step="0.1" description={t("ai.temperatureHint")} />
          <Row>
            <SelectField control={form.control} name="fallback_provider" label={t("ai.fallbackProvider")} options={providerOptions} />
            <TextField control={form.control} name="fallback_model" label={t("ai.fallbackModel")} />
          </Row>
          <TextareaField control={form.control} name="instructions" label={t("ai.instructions")} rows={3} placeholder={t("ai.instructionsHint")} />
        </FieldGroup>
        <div className="mt-5 flex gap-2">
          <Button type="submit" disabled={save.isPending}>{save.isPending ? t("common.saving") : t("common.save")}</Button>
          <Button type="button" variant="outline" disabled={test.isPending || !config.provider} onClick={() => test.mutate()}>
            {test.isPending ? <Loader2 className="size-4 animate-spin" /> : <Zap className="size-4" />}{t("ai.test")}
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** Mavjud ma'lumotlarni (masalan, avval kiritilganlarini) bir bosishda barcha tillarga tarjima qilish. */
function TranslateSection() {
  const t = useTranslations("ai.translation");
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: KEYS.translate,
    queryFn: adminApi.translate.status,
    refetchInterval: (q) => (q.state.data?.running ? 2500 : false),
  });
  const start = useMutation({
    mutationFn: adminApi.translate.start,
    onSuccess: async (data) => {
      qc.setQueryData(KEYS.translate, data);
      if (data.filled) {
        toast.success(t("filled", { count: data.filled }));
        await qc.invalidateQueries({ queryKey: queryKeys.state });
      }
      if (data.running) toast.success(t("started"));
      else if (!data.filled) toast.info(data.pending ? t("needAi", { count: data.pending }) : t("allDone"));
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const s = status.data;
  const wasRunning = useRef(false);
  useEffect(() => {
    // fon tarjimasi tugadi: tuzilmani yangilaymiz
    if (wasRunning.current && s && !s.running) void qc.invalidateQueries({ queryKey: queryKeys.state });
    wasRunning.current = !!s?.running;
  }, [s, qc]);

  return (
    <Card className="mt-6 gap-3 p-5">
      <div className="flex flex-wrap items-start gap-3">
        <span className="grid size-9 place-items-center rounded-lg border bg-muted/50"><Languages className="size-4" /></span>
        <div className="min-w-0 flex-1">
          <div className="font-semibold">{t("title")}</div>
          <p className="text-sm text-muted-foreground">{t("hint")}</p>
        </div>
        <Button disabled={!s || s.running || start.isPending || !s.pending} onClick={() => start.mutate()}>
          {s?.running || start.isPending ? <Loader2 className="size-4 animate-spin" /> : <Languages className="size-4" />}
          {s?.running ? t("running") : t("run")}
        </Button>
      </div>
      {s && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          {!s.enabled && s.pending ? (
            <span className="text-muted-foreground">{t("pendingNoAi", { count: s.pending })}</span>
          ) : s.pending ? (
            <span>{t("pending", { count: s.pending })}</span>
          ) : (
            <span className="flex items-center gap-1 text-success"><CheckCircle2 className="size-4" />{t("allDone")}</span>
          )}
          {s.last_error && (
            <span className="flex min-w-0 items-center gap-1 text-destructive" title={s.last_error}>
              <CircleAlert className="size-4 shrink-0" /><span className="truncate">{s.last_error}</span>
            </span>
          )}
        </div>
      )}
    </Card>
  );
}

function UsageSection() {
  const t = useTranslations();
  const locale = useLocale() as keyof typeof DATE_LOCALES;
  const summary = useQuery({ queryKey: KEYS.summary, queryFn: adminApi.usage.summary });
  const usage = useQuery({ queryKey: KEYS.usage, queryFn: adminApi.usage.list });
  const n = (v: number) => v.toLocaleString(locale === "en" ? "en-US" : "ru-RU");
  return (
    <>
      <SectionTitle>{t("ai.usage")}</SectionTitle>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="gap-0 overflow-hidden p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("ai.model")}</TableHead>
                <TableHead className="text-right">{t("ai.calls")}</TableHead>
                <TableHead className="text-right">{t("ai.errors")}</TableHead>
                <TableHead className="text-right">{t("ai.inTokens")}</TableHead>
                <TableHead className="text-right">{t("ai.outTokens")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.data?.models.map((m) => (
                <TableRow key={`${m.provider}/${m.model}`}>
                  <TableCell><div className="font-mono text-xs">{m.model}</div><div className="text-xs text-muted-foreground">{m.provider}</div></TableCell>
                  <TableCell className="text-right font-mono">{n(m.calls)}</TableCell>
                  <TableCell className={cn("text-right font-mono", m.errors && "text-destructive")}>{n(m.errors)}</TableCell>
                  <TableCell className="text-right font-mono">{n(m.input_tokens)}</TableCell>
                  <TableCell className="text-right font-mono">{n(m.output_tokens)}</TableCell>
                </TableRow>
              ))}
              {summary.data && !summary.data.models.length && (
                <TableRow><TableCell colSpan={5} className="py-6 text-center text-sm text-muted-foreground">{t("ai.noUsage")}</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </Card>
        <Card className="max-h-96 gap-0 overflow-y-auto p-2">
          {usage.data?.slice(0, 50).map((u) => (
            <div key={u.id} className="flex items-center gap-3 rounded-lg px-3 py-2 text-xs">
              <span className={cn("size-1.5 shrink-0 rounded-full", u.ok ? "bg-success" : "bg-destructive")} />
              <Badge variant="outline" className="font-mono text-[10px]">{u.task}</Badge>
              <span className="min-w-0 flex-1 truncate text-muted-foreground" title={u.error || u.prompt}>{u.error || u.prompt || u.model}</span>
              <span className="font-mono text-muted-foreground">{u.latency_ms} ms</span>
              <span className="w-24 text-right text-muted-foreground">{formatDistanceToNow(new Date(u.at), { addSuffix: true, locale: DATE_LOCALES[locale] })}</span>
            </div>
          ))}
          {usage.data && !usage.data.length && <p className="p-6 text-center text-sm text-muted-foreground">{t("ai.noUsage")}</p>}
        </Card>
      </div>
    </>
  );
}
