"use client";

import { useQuery } from "@tanstack/react-query";
import { Archive, Check, History, RotateCcw, Save, X } from "lucide-react";
import { useState } from "react";

import { FormRow } from "@/components/qrdrive/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useCan } from "@/hooks/use-org";
import { cn } from "@/lib/utils";

import { supportApi, type Entry, type EntryKind, type MediaInfo } from "./api";
import { EntryBadge, fmtDate, lines, OwnerSelect, Segmented, unlines, useSupportMutation } from "./common";
import { MediaThumb } from "./media";
import { useSt, type SKey } from "./i18n";

interface Draft {
  kind: EntryKind; title: string; questions: string; triggers: string; extract: string; answer: string; answer_ru: string;
  ask_first: string; creates_task: boolean; task_assignee: string; answer_mode: "" | "on" | "off"; responsible: number | null;
  auto_close: number;
}

const blank: Draft = { kind: "faq", title: "", questions: "", triggers: "", extract: "", answer: "", answer_ru: "", ask_first: "",
  creates_task: false, task_assignee: "", answer_mode: "", responsible: null, auto_close: 0 };

function toDraft(e?: Entry): Draft {
  if (!e) return blank;
  const p = e.pending ?? {};
  return {
    kind: e.kind, title: p.title ?? e.title, questions: unlines(p.questions ?? e.questions), triggers: unlines(p.triggers ?? e.triggers),
    extract: unlines(p.extract ?? e.extract), answer: p.answer ?? e.answer, answer_ru: p.answer_ru ?? e.answer_ru,
    ask_first: (p as { ask_first?: string }).ask_first ?? e.ask_first ?? "",
    creates_task: !!e.creates_task, task_assignee: e.task_assignee ?? "", answer_mode: e.answer_mode ?? "",
    responsible: e.responsible ?? null, auto_close: e.auto_close ?? 0,
  };
}

/** Yozuvni yaratish/tahrirlash, tasdiqlash va versiyalar tarixi (orqaga qaytarish bilan). */
export function EntryEditor({ entryId, open, onOpenChange, preset }: {
  entryId: number | null; open: boolean; onOpenChange: (v: boolean) => void; preset?: Partial<Draft>;
}) {
  const q = useQuery({ queryKey: ["support", "entry", entryId], queryFn: () => supportApi.entry(entryId!), enabled: open && !!entryId });
  const e = entryId ? q.data : undefined;
  const ready = !entryId || !!e;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 p-0 sm:max-w-2xl">
        {ready && (
          // kalit faqat yozuv raqami: bot yozuvni ishlatganda (uses++) updated_at o'zgaradi — oyna qayta yaratilsa yuklangan
          // fayl va yozilgan matn yo'qolardi (28.11: javobga rasm qo'shib bo'lmagan)
          <EditorBody key={entryId ?? "new"} e={e} onOpenChange={onOpenChange}
            initial={e ? toDraft(e) : { ...blank, ...preset }} />
        )}
      </SheetContent>
    </Sheet>
  );
}

function EditorBody({ e, initial, onOpenChange }: { e?: Entry; initial: Draft; onOpenChange: (v: boolean) => void }) {
  const t = useSt();
  const can = useCan();
  const [d, setD] = useState<Draft>(initial);
  const [files, setFiles] = useState<MediaInfo[]>(e?.attachments_info ?? []);

  const body = () => ({
    kind: d.kind, title: d.title.trim(), questions: lines(d.questions), triggers: lines(d.triggers), extract: lines(d.extract),
    answer: d.answer.trim(), answer_ru: d.answer_ru.trim(), ask_first: d.ask_first.trim(),
    creates_task: d.creates_task, task_assignee: d.task_assignee.trim().replace(/^@/, ""), answer_mode: d.answer_mode,
    attachments: files.map((f) => f.id), responsible: d.responsible, auto_close: Math.max(0, Math.min(1440, d.auto_close || 0)),
  });
  const save = useSupportMutation(
    (approve: boolean) => (e ? supportApi.updateEntry(e.id, body()).then((r) => (approve ? supportApi.approve(r.id) : r))
      : supportApi.createEntry({ ...body(), approve })),
    t("saved"),
  );
  const act = useSupportMutation((fn: () => Promise<unknown>) => fn(), t("saved"));
  const upload = useSupportMutation((list: File[]) => supportApi.upload(list, { source: "answer" }));
  const teach = useSupportMutation((list: File[]) => supportApi.upload(list, { label: e!.id, source: "seed" }), t("taught"));
  const set = (k: keyof Draft) => (v: string) => setD({ ...d, [k]: v });
  const valid = d.title.trim().length >= 2 && d.answer.trim().length >= 2;
  const waits = e?.status === "approved" && !can.edit;

  return (
    <div className="flex h-full flex-col">
      <SheetHeader className="border-b">
        <SheetTitle className="flex flex-wrap items-center gap-2 pr-6">
          <span className="line-clamp-2">{e ? e.title : t("newEntry")}</span>{e && <EntryBadge status={e.status} t={t} />}
        </SheetTitle>
        {e && <p className="text-xs text-muted-foreground">{t("uses")}: {e.uses} · 👍 {e.likes} · 👎 {e.dislikes} · {t("createdBy")}: {e.author || "—"}</p>}
      </SheetHeader>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {e?.pending && (
          <div className="mb-3 rounded-lg border border-warning/50 bg-warning/5 p-2 text-xs">
            <b>{t("pendingEdit")}</b> · {e.pending.by} · {t("pendingEditHint")}
          </div>
        )}
        {waits && <p className="mb-3 text-xs text-muted-foreground">{t("editWillWait")}</p>}
        <Tabs defaultValue="answer">
          <TabsList className="mb-3 w-full">
            <TabsTrigger value="answer">{t("edAnswer")}</TabsTrigger>
            <TabsTrigger value="questions">{t("edQuestions")}</TabsTrigger>
            <TabsTrigger value="media">{t("edMedia")}{files.length ? ` · ${files.length}` : ""}</TabsTrigger>
            {e && <TabsTrigger value="history">{t("edHistory")}</TabsTrigger>}
          </TabsList>

          <TabsContent value="answer" className="grid gap-3">
            <FormRow label={t("title")}><Input value={d.title} onChange={(x) => set("title")(x.target.value)} /></FormRow>
            <FormRow label={t("answer")} hint={t("answerHint")}>
              <Textarea rows={7} value={d.answer} onChange={(x) => set("answer")(x.target.value)} />
            </FormRow>
            <FormRow label={t("answerRu")}>
              <Textarea rows={5} value={d.answer_ru} onChange={(x) => set("answer_ru")(x.target.value)} />
            </FormRow>
            <FormRow label={t("owner")} hint={t("ownerHint")}>
              <OwnerSelect t={t} value={d.responsible} onChange={(id) => setD({ ...d, responsible: id })} className="h-9 w-full" />
            </FormRow>
            <FormRow label={t("edAutoClose")} hint={t("edAutoCloseHint")}>
              <Input type="number" min={0} max={1440} className="w-32" value={d.auto_close}
                onChange={(x) => setD({ ...d, auto_close: Number(x.target.value) || 0 })} />
            </FormRow>
            <FormRow label={t("askFirst")} hint={t("askFirstHint")}>
              <Textarea rows={2} value={d.ask_first} onChange={(x) => set("ask_first")(x.target.value)} />
            </FormRow>
            <div className="grid gap-2 rounded-lg border p-3">
              <div className="text-sm font-medium">{t("modeTitle")}</div>
              <Segmented size="sm" value={d.answer_mode || "auto"} onChange={(v) => setD({ ...d, answer_mode: v === "auto" ? "" : v as "on" | "off" })}
                options={[{ value: "auto", label: t("mode_auto") }, { value: "on", label: t("mode_on") }, { value: "off", label: t("mode_offL") }]} />
              <p className="text-xs text-muted-foreground">{t("modeHint3")}</p>
            </div>
            {e && <Variants e={e} />}
            <div className={cn("grid gap-2 rounded-lg border p-3", d.creates_task && "border-primary/40 bg-primary/[0.04]")}>
              <label className="flex items-start gap-3 text-sm">
                <Switch checked={d.creates_task} onCheckedChange={(v) => setD({ ...d, creates_task: v })} className="mt-0.5" />
                <span><span className="font-medium">{t("edCreatesTask")}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">{t("edCreatesTaskHint")}</span></span>
              </label>
              {d.creates_task && (
                <FormRow label={t("edTaskAssignee")} hint={t("edTaskAssigneeHint")}>
                  <Input value={d.task_assignee} placeholder="@username" onChange={(x) => set("task_assignee")(x.target.value)} />
                </FormRow>
              )}
            </div>
          </TabsContent>

          <TabsContent value="questions" className="grid gap-3">
            <FormRow label={t("kind")}>
              <Segmented size="sm" value={d.kind} onChange={(v) => setD({ ...d, kind: v })}
                options={[{ value: "faq" as EntryKind, label: t("k_faq") }, { value: "template" as EntryKind, label: t("k_template") }]} />
            </FormRow>
            <FormRow label={t("questions")} hint={t("questionsHint")}>
              <Textarea rows={8} value={d.questions} onChange={(x) => set("questions")(x.target.value)} />
            </FormRow>
            {d.kind === "template" && (
              <>
                <FormRow label={t("triggers")} hint={t("triggersHint")}>
                  <Textarea rows={3} className="font-mono text-xs" value={d.triggers} onChange={(x) => set("triggers")(x.target.value)} />
                </FormRow>
                <FormRow label={t("extract")} hint={t("extractHint")}>
                  <Textarea rows={2} className="font-mono text-xs" value={d.extract} onChange={(x) => set("extract")(x.target.value)} />
                </FormRow>
              </>
            )}
          </TabsContent>

          <TabsContent value="media" className="grid gap-4">
            <FormRow label={t("attachments")} hint={t("attachmentsHint")}>
              <div className="grid gap-2">
                <div className="flex flex-wrap gap-2">
                  {files.map((f) => (
                    <div key={f.id} className="relative">
                      <MediaThumb m={f} />
                      <button type="button" className="absolute -right-1 -top-1 grid size-5 place-items-center rounded-full bg-destructive text-[10px] text-white"
                        onClick={() => setFiles(files.filter((x) => x.id !== f.id))} aria-label={t("delete")}>✕</button>
                    </div>
                  ))}
                </div>
                <Input type="file" multiple accept="image/*,video/*,application/pdf,.doc,.docx,.xls,.xlsx" disabled={upload.isPending}
                  onChange={(x) => { const list = Array.from(x.target.files ?? []); x.target.value = "";
                    if (list.length) upload.mutate(list, { onSuccess: (r) => setFiles((prev) => [...prev, ...r].slice(0, 10)) }); }} />
              </div>
            </FormRow>
            {e ? (
              <FormRow label={t("examples")} hint={t("examplesHint", { n: e.image_examples_count ?? 0 })}>
                <Input type="file" multiple accept="image/*" disabled={teach.isPending}
                  onChange={(x) => { const list = Array.from(x.target.files ?? []); x.target.value = ""; if (list.length) teach.mutate(list); }} />
              </FormRow>
            ) : <p className="text-xs text-muted-foreground">{t("examplesAfterSave")}</p>}
          </TabsContent>

          {e && (
            <TabsContent value="history" className="grid gap-3">
              <div className="grid gap-1 text-xs text-muted-foreground">
                <span>{t("createdBy")}: {e.author || "—"} · {fmtDate(e.created_at)} · {t(`src_${e.source}` as SKey)}</span>
                {e.approved_by && <span>{t("approvedBy")}: {e.approved_by} · {fmtDate(e.approved_at)}</span>}
              </div>
              <div className="flex items-center gap-1.5 text-sm font-medium"><History className="size-4" />{t("versions")}</div>
              {(e.versions ?? []).length === 0 && <p className="text-xs text-muted-foreground">{t("noVersions")}</p>}
              {e.versions?.map((v) => (
                <div key={v.id} className="grid gap-1 rounded-lg border p-2 text-xs">
                  <div className="flex flex-wrap items-center gap-2 text-muted-foreground">
                    <span>{fmtDate(v.at)} · {v.editor || "—"}{v.note && ` · ${v.note}`}</span>
                    {can.edit && (
                      <Button size="sm" variant="ghost" className="ml-auto h-7" onClick={() => act.mutate(() => supportApi.revert(e.id, v.id))}>
                        <RotateCcw className="size-3.5" />{t("revert")}
                      </Button>
                    )}
                  </div>
                  <p className="line-clamp-4 whitespace-pre-wrap">{v.answer}</p>
                </div>
              ))}
              {(e.messages ?? []).length > 0 && (
                <div className="grid gap-1">
                  <div className="text-sm font-medium">{t("usedIn")}</div>
                  {e.messages!.map((m) => <p key={m.id} className="truncate text-xs text-muted-foreground">{fmtDate(m.at)} · {m.text}</p>)}
                </div>
              )}
            </TabsContent>
          )}
        </Tabs>
      </div>
      <div className="flex flex-wrap gap-2 border-t bg-card px-4 py-3">
        <Button disabled={!valid || save.isPending} onClick={() => save.mutate(false, { onSuccess: () => !e && onOpenChange(false) })}>
          <Save className="size-4" />{t("save")}
        </Button>
        {can.edit && (
          <Button variant="outline" disabled={!valid || save.isPending} onClick={() => save.mutate(true, { onSuccess: () => onOpenChange(false) })}>
            <Check className="size-4" />{t("saveAndApprove")}
          </Button>
        )}
        {can.edit && e && e.status !== "approved" && e.status !== "rejected" && (
          <Button variant="ghost" onClick={() => act.mutate(() => supportApi.reject(e.id), { onSuccess: () => onOpenChange(false) })}>
            <X className="size-4" />{t("reject")}
          </Button>
        )}
        {can.edit && e && e.status === "approved" && (
          <Button variant="ghost" className="ml-auto" onClick={() => act.mutate(() => supportApi.archive(e.id), { onSuccess: () => onOpenChange(false) })}>
            <Archive className="size-4" />{t("archive")}
          </Button>
        )}
      </div>
    </div>
  );
}

/** Javobning AI yozgan variantlari (mazmuni bir xil) — bot har safar shulardan birini tanlaydi. O'chirish va qayta yozish. */
function Variants({ e }: { e: Entry }) {
  const t = useSt();
  const can = useCan();
  const list = e.variants ?? [];
  const save = useSupportMutation((v: { uz: string; ru: string }[]) => supportApi.updateEntry(e.id, { variants: v.length ? v : null }), t("saved"));
  const gen = useSupportMutation(() => supportApi.startAIJob("variants", { ids: [e.id] }), t("varQueued"));
  return (
    <div className="grid gap-2 rounded-lg border p-3">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{t("varTitle")}</span>
        <span className="text-xs text-muted-foreground">{list.length ? t("varCount", { n: list.length }) : t("varNone")}</span>
        {can.edit && <Button size="sm" variant="outline" className="ml-auto h-7 text-xs" disabled={gen.isPending} onClick={() => gen.mutate(undefined)}>{t("varGen")}</Button>}
      </div>
      <p className="text-xs text-muted-foreground">{t("varHint")}</p>
      {list.map((v, i) => (
        <div key={i} className="relative rounded-md bg-muted/50 p-2 pr-8 text-xs">
          <p className="whitespace-pre-wrap">{v.uz}</p>
          {v.ru && <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{v.ru}</p>}
          {can.edit && (
            <button type="button" className="absolute right-1.5 top-1.5 grid size-5 place-items-center rounded-full hover:bg-destructive hover:text-white"
              aria-label={t("delete")} onClick={() => save.mutate(list.filter((_x, j) => j !== i))}>✕</button>
          )}
        </div>
      ))}
    </div>
  );
}
