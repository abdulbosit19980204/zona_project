"use client";

import { useQuery } from "@tanstack/react-query";
import { Ban, Check, ChevronDown, ExternalLink, Gauge, Images, RotateCcw, ScanSearch, Sparkles, Wand2, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/hooks/use-org";
import { cn } from "@/lib/utils";

import { supportApi, type ImageTypes, type MediaInfo } from "./api";
import { EntryBadge, EntryPicker, Metric, Segmented, useSupportMutation } from "./common";
import { useSt, type SKey, type ST } from "./i18n";
import { MediaThumb } from "./media";
import { SupportShell } from "./shell";

type View = "new" | "known" | "ignored";

/** Rasm turlari: bot qaysi ekranlarni taniydi (o'rgatilgan namunalar) va hali tanimaydigan rasmlar guruhlari. */
export function SupportImages() {
  const t = useSt();
  const [view, setView] = useState<View>("new");
  const q = useQuery({ queryKey: ["support", "images"], queryFn: supportApi.images });
  const entries = useQuery({ queryKey: ["support", "entries", "for-label"], queryFn: () => supportApi.entries({ status: "approved,review,new" }) });
  const d = q.data;
  const can = useCan();
  const [removing, setRemoving] = useState<MediaInfo | null>(null);
  const unlabel = useSupportMutation((ids: number[]) => supportApi.label(ids, null), t("imgUnlabeled1"));
  const ignore = useSupportMutation((ids: number[]) => supportApi.ignoreImages(ids, true), t("imgIgnoredDone"));
  const options = useMemo(() => {
    const list = (entries.data ?? []).map((e) => ({ id: e.id, title: e.title, sub: t(`e_${e.status}` as SKey) }));
    // taxmin qilingan javob ro'yxatda bo'lmasa ham (masalan, arxivda) tanlangan holda ko'rinsin
    for (const g of q.data?.unlabeled ?? []) {
      if (g.guess && !list.some((o) => o.id === g.guess)) list.push({ id: g.guess, title: g.guess_title, sub: "" });
    }
    return list;
  }, [entries.data, q.data, t]);

  return (
    <SupportShell title={t("imgTitle")} description={t("imgDesc")}>
      {!d && <div className="grid gap-4"><Skeleton className="h-20" /><Skeleton className="h-80" /></div>}
      {d && (
        <div className="grid gap-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Metric label={t("imgStatTotal")} value={d.total} icon={Images} />
            <Metric label={t("imgStatTypes")} value={d.labeled.length} icon={Check} tone="success" />
            <Metric label={t("imgStatClusters")} value={d.unlabeled.length} icon={ScanSearch} tone={d.unlabeled.length ? "warning" : undefined} />
            <Metric label={t("imgStatThreshold")} value={d.threshold} hint={t("imgStatThresholdHint")} icon={Gauge} />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Segmented value={view} onChange={setView} options={[
              { value: "new", label: t("imgTabNew"), count: d.unlabeled.length, icon: Sparkles },
              { value: "known", label: t("imgTabKnown"), count: d.labeled.length, icon: Images },
              { value: "ignored", label: t("imgTabIgnored"), count: (d.ignored ?? []).reduce((n, g) => n + g.count, 0), icon: Ban },
            ]} />
            <p className="min-w-0 flex-1 text-xs text-muted-foreground">
              {view === "new" ? t("imgUnlabeledHint") : view === "known" ? t("imgKnownHint") : t("imgIgnoredHint")}
            </p>
          </div>

          {view === "new" && (
            d.unlabeled.length === 0
              ? <EmptyState icon={Check} title={t("imgAllDone")} hint={t("imgAllDoneHint")} />
              : (
                <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
                  {d.unlabeled.map((g) => <Cluster key={g.ids[0]} g={g} t={t} options={options} />)}
                </div>
              )
          )}

          {view === "ignored" && (
            (d.ignored ?? []).length === 0
              ? <EmptyState icon={Ban} title={t("empty")} />
              : (
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                  {d.ignored.map((g) => <IgnoredCard key={g.ids[0]} g={g} t={t} />)}
                </div>
              )
          )}

          {view === "known" && (
            d.labeled.length === 0
              ? <EmptyState icon={Images} title={t("empty")} />
              : (
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                  {d.labeled.map((r) => (
                    <div key={r.entry} className="flex flex-col overflow-hidden rounded-xl border bg-card shadow-xs">
                      <Shots items={r.samples} total={r.count} max={3} onRemove={can.edit ? (m) => setRemoving(m) : undefined} t={t} />
                      <div className="grid gap-2 p-3">
                        <div className="line-clamp-2 text-sm font-medium leading-snug" title={r.title}>{r.title}</div>
                        <div className="flex flex-wrap items-center gap-1.5 text-xs">
                          <EntryBadge status={r.status} t={t} />
                          <Badge variant="outline" className="font-normal">{t("imgCount", { n: r.count })}</Badge>
                          {r.auto > 0 && <Badge variant="outline" className="font-normal text-muted-foreground">{t("imgAutoN", { n: r.auto })}</Badge>}
                          <Link href={`/support/knowledge?entry=${r.entry}`}
                            className="ml-auto inline-flex items-center gap-1 text-primary hover:underline">
                            {t("imgOpenEntry")}<ExternalLink className="size-3" />
                          </Link>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )
          )}
        </div>
      )}
      <Dialog open={!!removing} onOpenChange={(v) => !v && setRemoving(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{t("imgWrongTitle")}</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">{t("imgWrongHint")}</p>
          <div className="grid gap-2">
            <Button variant="outline" disabled={unlabel.isPending} onClick={() => removing && unlabel.mutate([removing.id], { onSuccess: () => setRemoving(null) })}>
              <RotateCcw className="size-4" />{t("imgUnlabelBtn")}
            </Button>
            <Button variant="destructive" disabled={ignore.isPending} onClick={() => removing && ignore.mutate([removing.id], { onSuccess: () => setRemoving(null) })}>
              <Ban className="size-4" />{t("imgIgnoreBtn")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </SupportShell>
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
function Shots({ items, total, max = 4, onRemove, t }: {
  items: MediaInfo[]; total: number; max?: number; onRemove?: (m: MediaInfo) => void; t?: ST;
}) {
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
          {onRemove && (
            <button type="button" onClick={() => onRemove(m)} title={t?.("imgWrongTitle")} aria-label={t?.("imgWrongTitle")}
              className="absolute right-1 top-1 grid size-6 place-items-center rounded-full bg-black/60 text-white opacity-80 transition-opacity hover:bg-destructive hover:opacity-100">
              <X className="size-3.5" />
            </button>
          )}
        </div>
      ))}
      {Array.from({ length: max - shown.length }).map((_, i) => <div key={`e${i}`} className="aspect-[9/16] rounded-md border border-dashed bg-background/40" />)}
    </div>
  );
}

function Cluster({ g, t, options }: { g: ImageTypes["unlabeled"][number]; t: ST; options: { id: number; title: string }[] }) {
  const can = useCan();
  const [entry, setEntry] = useState(g.guess ? String(g.guess) : "");
  const [ocr, setOcr] = useState(false);
  const label = useSupportMutation(() => supportApi.label(g.ids, Number(entry)), (r) => t("imgTaught", { n: r.done }));
  const ignore = useSupportMutation(() => supportApi.ignoreImages(g.ids, true), t("imgIgnoredDone"));
  const isGuess = !!g.guess && entry === String(g.guess);

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

        {g.guess_title ? (
          <div className="rounded-lg border border-primary/25 bg-primary/5 px-3 py-2">
            <div className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-primary"><Wand2 className="size-3" />{t("imgGuess")}</div>
            <div className="mt-0.5 line-clamp-2 text-sm leading-snug" title={g.guess_title}>{g.guess_title}</div>
          </div>
        ) : (
          <div className="rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground">{t("imgNoGuess")}</div>
        )}

        {ocr && g.ocr && <p className="max-h-28 overflow-y-auto rounded-lg bg-muted/60 p-2 text-xs leading-relaxed text-muted-foreground">{g.ocr}</p>}

        {can.edit && (
          <div className="mt-auto grid gap-2">
            <EntryPicker value={entry} onChange={setEntry} options={options} className="w-full"
              placeholder={t("imgChoose")} searchPlaceholder={t("pickSearch")} emptyText={t("pickNone")}
              hintId={g.guess} hintLabel={t("imgGuess")} />
            <div className="flex gap-2">
              <Button className="flex-1" disabled={!entry || label.isPending} onClick={() => label.mutate(undefined)}>
                <Check className="size-4" />{isGuess ? t("imgTeachGuess") : t("imgTeach")}
              </Button>
              <Button variant="outline" className="text-destructive hover:text-destructive" disabled={ignore.isPending}
                title={t("imgIgnoreHint")} onClick={() => ignore.mutate(undefined)}>
                <Ban className="size-4" />{t("imgIgnore")}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
