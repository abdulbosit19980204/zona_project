"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, Images, Sparkles } from "lucide-react";
import { useState } from "react";

import { EmptyState, SectionTitle } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/hooks/use-org";

import { supportApi, type ImageTypes } from "./api";
import { EntryBadge, useSupportMutation } from "./common";
import { useSt, type ST } from "./i18n";
import { MediaThumb } from "./media";
import { SupportShell } from "./shell";

/** Rasm turlari: bot qaysi ekranlarni taniydi (o'rgatilgan namunalar) va hali tanimaydigan rasmlar guruhlari. */
export function SupportImages() {
  const t = useSt();
  const q = useQuery({ queryKey: ["support", "images"], queryFn: supportApi.images });
  const entries = useQuery({ queryKey: ["support", "entries", "for-label"], queryFn: () => supportApi.entries({ status: "approved,review,new" }) });
  return (
    <SupportShell title={t("imgTitle")} description={t("imgDesc")}>
      {!q.data && <Skeleton className="h-64" />}
      {q.data && (
        <div className="grid gap-6">
          <section>
            <SectionTitle><span className="inline-flex items-center gap-1.5"><Sparkles className="size-4" />{t("imgUnlabeled")} · {q.data.unlabeled.length}</span></SectionTitle>
            <p className="mb-3 text-xs text-muted-foreground">{t("imgUnlabeledHint")}</p>
            {q.data.unlabeled.length === 0 && <p className="text-sm text-muted-foreground">{t("empty")}</p>}
            <div className="grid gap-3 lg:grid-cols-2">
              {q.data.unlabeled.map((g) => <Cluster key={g.ids[0]} g={g} t={t} options={entries.data ?? []} />)}
            </div>
          </section>
          <section>
            <SectionTitle><span className="inline-flex items-center gap-1.5"><Images className="size-4" />{t("imgLabeled")} · {q.data.labeled.length}</span></SectionTitle>
            {q.data.labeled.length === 0 && <EmptyState icon={Images} title={t("empty")} />}
            <div className="grid gap-3 lg:grid-cols-2">
              {q.data.labeled.map((r) => (
                <Card key={r.entry} className="gap-2 p-3">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-medium">{r.title}</span><EntryBadge status={r.status} t={t} />
                    <Badge variant="outline" className="font-normal">{t("imgCount", { n: r.count })}{r.auto ? ` · ${t("imgAutoN", { n: r.auto })}` : ""}</Badge>
                  </div>
                  <div className="flex flex-wrap gap-2">{r.samples.map((m) => <MediaThumb key={m.id} m={m} />)}</div>
                </Card>
              ))}
            </div>
          </section>
        </div>
      )}
    </SupportShell>
  );
}

function Cluster({ g, t, options }: { g: ImageTypes["unlabeled"][number]; t: ST; options: { id: number; title: string }[] }) {
  const can = useCan();
  const [entry, setEntry] = useState(g.guess ? String(g.guess) : "");
  const label = useSupportMutation(() => supportApi.label(g.ids, Number(entry)), (r) => t("imgTaught", { n: r.done }));
  return (
    <Card className="gap-2 p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="outline" className="font-mono">{g.count}</Badge>
        {g.guess_title && <span className="text-xs text-muted-foreground">{t("imgGuess")}: {g.guess_title}</span>}
      </div>
      <div className="flex flex-wrap gap-2">{g.samples.map((m) => <MediaThumb key={m.id} m={m} />)}</div>
      {g.ocr && <p className="line-clamp-2 text-xs text-muted-foreground">{g.ocr}</p>}
      {can.edit && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <Select value={entry} onValueChange={setEntry}>
            <SelectTrigger className="flex-1"><SelectValue placeholder={t("imgChoose")} /></SelectTrigger>
            <SelectContent>{options.map((e) => <SelectItem key={e.id} value={String(e.id)}>{e.title}</SelectItem>)}</SelectContent>
          </Select>
          <Button disabled={!entry || label.isPending} onClick={() => label.mutate(undefined)}><Check className="size-4" />{t("imgTeach")}</Button>
        </div>
      )}
    </Card>
  );
}
