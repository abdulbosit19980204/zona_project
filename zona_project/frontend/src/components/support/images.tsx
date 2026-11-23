"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Ban, Check, ChevronDown, EyeOff, ExternalLink, FolderPlus, Gauge, HardDrive, Images, Layers, ListTree, MessageSquareText, RefreshCw,
  RotateCcw, ScanSearch, Search, Sparkles, Wand2, X,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/hooks/use-org";
import { cn } from "@/lib/utils";

import { supportApi, type ImageTypes, type MediaInfo, type ScreenTypeInfo, type SupportTag } from "./api";
import { EntryBadge, EntryPicker, Metric, Segmented, useSupportMutation } from "./common";
import { useSt, type SKey, type ST } from "./i18n";
import { MediaThumb } from "./media";
import { SupportShell } from "./shell";

type View = "types" | "new" | "answers" | "ignored";
type Opt = { id: number; title: string; sub?: string };

/** Rasm turlari: o'xshash skrinshotlar umumiy turlarga (ekranlarga) guruhlanadi, savollar tur ichida jamlanadi;
 *  turga kirmagan yangi ekranlar — bir bosishda tur ochish yoki qo'shish. Rasmlarning asli serverda saqlanmaydi. */
export function SupportImages() {
  const t = useSt();
  const [view, setView] = useState<View>("types");
  const q = useQuery({ queryKey: ["support", "images"], queryFn: supportApi.images });
  const entries = useQuery({ queryKey: ["support", "entries", "brief", "approved,review,new"], queryFn: () => supportApi.entriesBrief("approved,review,new"),
    staleTime: 60_000 });
  const tags = useQuery({ queryKey: ["support", "tags"], queryFn: supportApi.tags, staleTime: 60_000 });
  const d = q.data;
  const options = useMemo<Opt[]>(() => {
    const list: Opt[] = (entries.data ?? []).map((e) => ({ id: e.id, title: e.title, sub: t(`e_${e.status}` as SKey) }));
    for (const g of q.data?.unlabeled ?? []) {
      if (g.guess && !list.some((o) => o.id === g.guess)) list.push({ id: g.guess, title: g.guess_title, sub: "" });
    }
    return list;
  }, [entries.data, q.data, t]);
  const screenOpts = useMemo<Opt[]>(() => (d?.screens ?? []).map((s) => ({ id: s.id, title: s.title, sub: s.tag_title || undefined })), [d]);

  return (
    <SupportShell title={t("imgTitle")} description={t("imgDesc2")}>
      {!d && <div className="grid gap-4"><Skeleton className="h-20" /><Skeleton className="h-80" /></div>}
      {d && (
        <div className="grid gap-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Metric label={t("imgStatTotal")} value={d.total} icon={Images} />
            <Metric label={t("imgStatScreens")} value={d.screens.length} icon={Layers} tone="success" hint={t("imgStatScreensHint")} />
            <Metric label={t("imgStatClusters")} value={d.unlabeled.length} icon={ScanSearch} tone={d.unlabeled.length ? "warning" : undefined} />
            <Metric label={t("imgStatDisk")} value={`${d.storage.disk_mb} MB`} icon={HardDrive}
              hint={t("imgStatDiskHint", { mb: d.storage.saved_mb, n: d.storage.slim })} />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Segmented value={view} onChange={setView} options={[
              { value: "types", label: t("imgTabTypes"), count: d.screens.length, icon: Layers },
              { value: "new", label: t("imgTabNew2"), count: d.unlabeled.length, icon: Sparkles },
              { value: "answers", label: t("imgTabAnswers"), count: d.labeled.length, icon: ListTree },
              { value: "ignored", label: t("imgTabIgnored"), count: (d.ignored ?? []).reduce((n, g) => n + g.count, 0), icon: Ban },
            ]} />
            <p className="min-w-0 flex-1 text-xs text-muted-foreground">
              {view === "types" ? t("imgTypesHint") : view === "new" ? t("imgNewHint2") : view === "answers" ? t("imgAnswersHint") : t("imgIgnoredHint")}
            </p>
          </div>

          {view === "types" && <ScreensView d={d} t={t} tags={tags.data ?? []} options={options} />}

          {view === "new" && (
            d.unlabeled.length === 0
              ? <EmptyState icon={Check} title={t("imgAllDone")} hint={t("imgAllDoneHint")} />
              : (
                <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
                  {d.unlabeled.map((g) => <Cluster key={g.ids[0]} g={g} t={t} options={options} screens={screenOpts} />)}
                </div>
              )
          )}

          {view === "answers" && <AnswersTable rows={d.labeled} t={t} />}

          {view === "ignored" && (
            (d.ignored ?? []).length === 0
              ? <EmptyState icon={Ban} title={t("empty")} />
              : (
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                  {d.ignored.map((g) => <IgnoredCard key={g.ids[0]} g={g} t={t} />)}
                </div>
              )
          )}
        </div>
      )}
    </SupportShell>
  );
}

/** Turlar teg (umumiy tur: moderatsiya, vizit, lokatsiya...) bo'yicha bo'limlarda; qidiruv va teg filtri. */
function ScreensView({ d, t, tags, options }: { d: ImageTypes; t: ST; tags: SupportTag[]; options: Opt[] }) {
  const can = useCan();
  const [search, setSearch] = useState("");
  const [tag, setTag] = useState("");
  const rebuild = useSupportMutation(() => supportApi.screensRebuild(), t("imgRebuildStarted"));
  const shown = useMemo(() => {
    const s = search.trim().toLowerCase();
    return d.screens.filter((x) => (!tag || (x.tag || "—") === tag)
      && (!s || x.title.toLowerCase().includes(s) || x.top.some((tq) => tq.q.toLowerCase().includes(s))));
  }, [d.screens, search, tag]);
  const sections = useMemo(() => {
    const by = new Map<string, ScreenTypeInfo[]>();
    for (const x of shown) by.set(x.tag || "—", [...(by.get(x.tag || "—") ?? []), x]);
    return [...by.entries()].sort((a, b) => (a[0] === "—" ? 1 : b[0] === "—" ? -1 : 0)
      || b[1].reduce((n, x) => n + x.count, 0) - a[1].reduce((n, x) => n + x.count, 0));
  }, [shown]);
  const tagTitle = (k: string) => (k === "—" ? t("imgNoTag") : tags.find((x) => x.key === k)?.title ?? k);
  const used = useMemo(() => [...new Set(d.screens.map((x) => x.tag || "—"))], [d.screens]);

  if (d.screens.length === 0) {
    return (
      <EmptyState icon={Layers} title={t("imgNoScreens")} hint={t("imgNoScreensHint")}
        action={can.edit ? <Button size="sm" onClick={() => rebuild.mutate(undefined)} disabled={rebuild.isPending}><RefreshCw className="size-4" />{t("imgRebuild")}</Button> : undefined} />
    );
  }
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-48 flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("imgSearch")} className="h-9 pl-8" />
        </div>
        <select className="h-9 rounded-md border bg-background px-2 text-sm" value={tag} onChange={(e) => setTag(e.target.value)} aria-label={t("dTags")}>
          <option value="">{t("imgAllTags")}</option>
          {used.map((k) => <option key={k} value={k}>{tagTitle(k)}</option>)}
        </select>
        {can.edit && (
          <Button size="sm" variant="outline" className="ml-auto" onClick={() => rebuild.mutate(undefined)} disabled={rebuild.isPending}
            title={t("imgRebuildHint")}>
            <RefreshCw className={cn("size-4", rebuild.isPending && "animate-spin")} />{t("imgRebuild")}
          </Button>
        )}
      </div>
      {sections.map(([k, list]) => (
        <section key={k} className="grid gap-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            {tagTitle(k)}
            <Badge variant="secondary" className="font-normal tabular-nums">{t("imgTypesN", { n: list.length, m: list.reduce((n, x) => n + x.count, 0) })}</Badge>
          </h3>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {list.map((s) => <ScreenCard key={s.id} s={s} t={t} tags={tags} options={options} />)}
          </div>
        </section>
      ))}
    </div>
  );
}

function ScreenCard({ s, t, tags, options }: { s: ScreenTypeInfo; t: ST; tags: SupportTag[]; options: Opt[] }) {
  const can = useCan();
  const [title, setTitle] = useState(s.title);
  const [more, setMore] = useState(false);
  const save = useSupportMutation((body: { title?: string; tag?: string; entry?: number | null }) => supportApi.screenUpdate(s.id, body), t("saved"));
  const hide = useSupportMutation(() => supportApi.screenHide(s.id), t("imgHidden"));
  const inbox = `/support?${new URLSearchParams({ ex: "1", scope: "all", days: "3650", f_screen: s.title }).toString()}`;
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border bg-card shadow-xs">
      <Shots items={s.samples} total={s.count} max={4} />
      <div className="flex flex-1 flex-col gap-2.5 p-3">
        {can.edit ? (
          <Input value={title} onChange={(e) => setTitle(e.target.value)} aria-label={t("tagsName")}
            onBlur={() => title.trim() && title !== s.title && save.mutate({ title })}
            onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
            className="h-8 border-transparent px-1 text-sm font-medium shadow-none hover:border-input focus-visible:border-input" />
        ) : <div className="line-clamp-2 text-sm font-medium">{s.title}</div>}
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <Badge variant="outline" className="font-normal tabular-nums">{t("imgCount", { n: s.count })}</Badge>
          <Link href={inbox} className="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-primary hover:bg-primary/5">
            <MessageSquareText className="size-3" />{t("imgQuestionsN", { n: s.questions })}
          </Link>
          {can.edit ? (
            <select className="ml-auto h-7 max-w-36 rounded-md border bg-background px-1.5 text-xs" value={s.tag}
              onChange={(e) => save.mutate({ tag: e.target.value })} aria-label={t("dTags")}>
              <option value="">{t("imgNoTag")}</option>
              {tags.map((x) => <option key={x.key} value={x.key}>{x.title}</option>)}
            </select>
          ) : s.tag_title && <Badge variant="secondary" className="ml-auto font-normal">{s.tag_title}</Badge>}
        </div>
        {s.top.length > 0 && (
          <ul className="grid gap-1 rounded-lg bg-muted/50 p-2 text-xs">
            {(more ? s.top : s.top.slice(0, 3)).map((x) => (
              <li key={x.q} className="flex gap-2">
                <span className="min-w-0 flex-1 truncate" title={x.q}>{x.q}</span>
                <span className="shrink-0 tabular-nums text-muted-foreground">{x.n}</span>
              </li>
            ))}
            {s.top.length > 3 && (
              <button type="button" onClick={() => setMore(!more)} className="inline-flex items-center gap-1 justify-self-start text-muted-foreground hover:text-foreground">
                {more ? t("less") : t("more")}<ChevronDown className={cn("size-3 transition-transform", more && "rotate-180")} />
              </button>
            )}
          </ul>
        )}
        {can.edit && (
          <div className="mt-auto grid gap-1.5">
            <span className="text-[11px] text-muted-foreground">{t("imgStdAnswer")}</span>
            <div className="flex gap-1.5">
              <EntryPicker value={s.entry ? String(s.entry) : ""} onChange={(v) => save.mutate({ entry: Number(v) })} options={options}
                className="h-8 flex-1 text-xs" placeholder={t("imgStdAnswerNone")} searchPlaceholder={t("pickSearch")} emptyText={t("pickNone")} />
              {s.entry && (
                <Button size="icon" variant="ghost" className="size-8" title={t("imgStdAnswerClear")} aria-label={t("imgStdAnswerClear")}
                  onClick={() => save.mutate({ entry: null })}><X className="size-4" /></Button>
              )}
              <Button size="icon" variant="ghost" className="size-8 text-muted-foreground" title={t("imgHide")} aria-label={t("imgHide")}
                disabled={hide.isPending} onClick={() => window.confirm(t("imgHideConfirm")) && hide.mutate(undefined)}>
                <EyeOff className="size-4" />
              </Button>
            </div>
          </div>
        )}
        {!can.edit && s.entry_title && <div className="text-xs text-muted-foreground">{t("imgStdAnswer")}: {s.entry_title}</div>}
      </div>
    </div>
  );
}

/** Rasm bo'yicha o'rgatilgan javoblar — ixcham jadval (har biri alohida katta kartochka bo'lib joy olmaydi). */
function AnswersTable({ rows, t }: { rows: ImageTypes["labeled"]; t: ST }) {
  const [search, setSearch] = useState("");
  const shown = useMemo(() => {
    const s = search.trim().toLowerCase();
    return s ? rows.filter((r) => r.title.toLowerCase().includes(s)) : rows;
  }, [rows, search]);
  if (rows.length === 0) return <EmptyState icon={ListTree} title={t("empty")} />;
  return (
    <div className="grid gap-3">
      <div className="relative max-w-xs">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("imgSearch")} className="h-9 pl-8" />
      </div>
      <div className="overflow-x-auto rounded-xl border bg-card">
        <table className="w-full text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr className="border-b text-left">
              <th className="px-3 py-2 font-medium">{t("imgAnswer")}</th>
              <th className="px-3 py-2 font-medium">{t("imgScreensCol")}</th>
              <th className="px-3 py-2 text-right font-medium">{t("imgPhotosCol")}</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {shown.slice(0, 300).map((r) => (
              <tr key={r.entry} className="border-b last:border-0 hover:bg-muted/40">
                <td className="max-w-md px-3 py-1.5">
                  <div className="flex items-center gap-2"><EntryBadge status={r.status} t={t} /><span className="truncate" title={r.title}>{r.title}</span></div>
                </td>
                <td className="max-w-56 truncate px-3 py-1.5 text-xs text-muted-foreground">{r.screens.join(", ") || "—"}</td>
                <td className="px-3 py-1.5 text-right font-mono text-xs tabular-nums">
                  {r.count}{r.auto > 0 && <span className="text-muted-foreground"> ({t("imgAutoN", { n: r.auto })})</span>}
                </td>
                <td className="px-3 py-1.5 text-right">
                  <Link href={`/support/knowledge?entry=${r.entry}`} className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
                    {t("imgOpenEntry")}<ExternalLink className="size-3" />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length > 300 && <p className="p-2 text-xs text-muted-foreground">{t("exTrunc", { n: 300, all: shown.length })}</p>}
      </div>
    </div>
  );
}

function IgnoredCard({ g, t }: { g: ImageTypes["ignored"][number]; t: ST }) {
  const can = useCan();
  const restore = useSupportMutation(() => supportApi.ignoreImages(g.ids, false), t("imgRestored"));
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border bg-card opacity-90 shadow-xs">
      <Shots items={g.samples} total={g.count} max={3} />
      <div className="flex items-center gap-2 p-3">
        <span className="text-xs text-muted-foreground">{t("imgPhotos", { n: g.count })}</span>
        {can.edit && (
          <Button size="sm" variant="outline" className="ml-auto" disabled={restore.isPending} onClick={() => restore.mutate(undefined)}>
            <RotateCcw className="size-4" />{t("imgRestore")}
          </Button>
        )}
      </div>
    </div>
  );
}

/** Telefon ekrani nisbatidagi namunalar qatori; ko'rsatilmaganlar soni oxirgi rasm ustida. */
function Shots({ items, total, max = 4 }: { items: MediaInfo[]; total: number; max?: number }) {
  const shown = items.slice(0, max);
  const rest = total - shown.length;
  return (
    <div className="grid gap-1.5 bg-muted/50 p-2" style={{ gridTemplateColumns: `repeat(${max}, minmax(0, 1fr))` }}>
      {shown.map((m, i) => (
        <div key={m.id} className="relative">
          <MediaThumb m={m} className="aspect-[9/16] size-auto w-full rounded-md bg-background" />
          {i === shown.length - 1 && rest > 0 && (
            <span className="pointer-events-none absolute inset-0 grid place-items-center rounded-md bg-black/55 text-sm font-semibold text-white">+{rest}</span>
          )}
        </div>
      ))}
      {Array.from({ length: max - shown.length }).map((_, i) => <div key={`e${i}`} className="aspect-[9/16] rounded-md border border-dashed bg-background/40" />)}
    </div>
  );
}

/** Turga kirmagan o'xshash rasmlar: yangi tur ochish yoki mavjud turga qo'shish (asosiy); ixtiyoriy — javobga o'rgatish. */
function Cluster({ g, t, options, screens }: { g: ImageTypes["unlabeled"][number]; t: ST; options: Opt[]; screens: Opt[] }) {
  const can = useCan();
  const [screen, setScreen] = useState("");
  const [name, setName] = useState("");
  const [teach, setTeach] = useState(false);
  const [entry, setEntry] = useState(g.guess ? String(g.guess) : "");
  const [ocr, setOcr] = useState(false);
  const assign = useSupportMutation(() => supportApi.screenAssign(screen ? { ids: g.ids, screen: Number(screen) } : { ids: g.ids, title: name.trim() }),
    (r) => t("imgAssigned", { n: r.done }));
  const label = useSupportMutation(() => supportApi.label(g.ids, Number(entry)), (r) => t("imgTaught", { n: r.done }));
  const ignore = useSupportMutation(() => supportApi.ignoreImages(g.ids, true), t("imgIgnoredDone"));
  const isGuess = !!g.guess && entry === String(g.guess);
  const [creating, setCreating] = useState(false);

  return (
    <div className="flex flex-col overflow-hidden rounded-xl border bg-card shadow-xs">
      <Shots items={g.samples} total={g.count} />
      <div className="flex flex-1 flex-col gap-3 p-3">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="font-medium tabular-nums">{t("imgPhotos", { n: g.count })}</Badge>
          {g.ocr && (
            <button type="button" onClick={() => setOcr(!ocr)} className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              {t("imgOcr")}<ChevronDown className={cn("size-3.5 transition-transform", ocr && "rotate-180")} />
            </button>
          )}
        </div>
        {ocr && g.ocr && <p className="max-h-28 overflow-y-auto rounded-lg bg-muted/60 p-2 text-xs leading-relaxed text-muted-foreground">{g.ocr}</p>}

        {can.edit && (
          <div className="mt-auto grid gap-2">
            <div className="flex gap-1.5">
              {creating ? (
                <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder={t("imgNewTypeName")} className="h-9 flex-1" />
              ) : (
                <EntryPicker value={screen} onChange={setScreen} options={screens} className="w-full flex-1"
                  placeholder={t("imgChooseType")} searchPlaceholder={t("pickSearch")} emptyText={t("pickNone")} />
              )}
              <Button size="icon" variant="outline" className="size-9 shrink-0" title={creating ? t("imgChooseType") : t("imgNewType")}
                aria-label={creating ? t("imgChooseType") : t("imgNewType")} onClick={() => { setCreating(!creating); setScreen(""); }}>
                {creating ? <Layers className="size-4" /> : <FolderPlus className="size-4" />}
              </Button>
            </div>
            <div className="flex gap-2">
              <Button className="flex-1" disabled={(creating ? !name.trim() : !screen) || assign.isPending} onClick={() => assign.mutate(undefined)}>
                <Check className="size-4" />{creating ? t("imgCreateType") : t("imgAddToType")}
              </Button>
              <Button variant="outline" className="text-destructive hover:text-destructive" disabled={ignore.isPending}
                title={t("imgIgnoreHint")} onClick={() => ignore.mutate(undefined)}>
                <Ban className="size-4" />{t("imgIgnore")}
              </Button>
            </div>
            <button type="button" onClick={() => setTeach(!teach)} className="inline-flex items-center gap-1 justify-self-start text-xs text-muted-foreground hover:text-foreground">
              <Wand2 className="size-3" />{t("imgTeachOptional")}<ChevronDown className={cn("size-3 transition-transform", teach && "rotate-180")} />
            </button>
            {teach && (
              <div className="grid gap-2 rounded-lg border border-dashed p-2">
                {g.guess_title && <p className="text-xs text-muted-foreground"><span className="font-medium text-primary">{t("imgGuess")}:</span> {g.guess_title}</p>}
                <EntryPicker value={entry} onChange={setEntry} options={options} className="w-full"
                  placeholder={t("imgChoose")} searchPlaceholder={t("pickSearch")} emptyText={t("pickNone")} hintId={g.guess} hintLabel={t("imgGuess")} />
                <Button size="sm" variant="secondary" disabled={!entry || label.isPending} onClick={() => label.mutate(undefined)}>
                  <Gauge className="size-4" />{isGuess ? t("imgTeachGuess") : t("imgTeach")}
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
