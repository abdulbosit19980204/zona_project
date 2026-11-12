"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { SectionTitle } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCan, useOrgMutation } from "@/hooks/use-org";
import { adminApi } from "@/lib/api/endpoints";

/** Qidiruv lug'ati: sinonim guruhlari (bir xil ma'noli so'zlar) va qidiruv qanday tushunishini tekshirish. */
export function DictionaryTab() {
  const t = useTranslations();
  const can = useCan();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["synonyms"], queryFn: adminApi.synonyms.list });
  const [words, setWords] = useState("");
  const [probe, setProbe] = useState("");
  const [asked, setAsked] = useState("");
  const explain = useQuery({ queryKey: ["explain", asked], queryFn: () => adminApi.synonyms.explain(asked), enabled: asked.length > 1 });
  const refresh = () => qc.invalidateQueries({ queryKey: ["synonyms"] });
  const add = useOrgMutation(async (w: string) => { await adminApi.synonyms.create({ words: w }); await refresh(); }, t("settings.saved"));
  const remove = useOrgMutation(async (id: number) => { await adminApi.synonyms.remove(id); await refresh(); }, t("settings.deleted"));

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <div>
        <SectionTitle>{t("dictionary.synonyms")}</SectionTitle>
        <p className="-mt-1 mb-3 text-sm text-muted-foreground">{t("dictionary.hint")}</p>
        {can.edit && (
          <form className="mb-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (words.trim()) add.mutate(words.trim(), { onSuccess: () => setWords("") }); }}>
            <Input value={words} onChange={(e) => setWords(e.target.value)} placeholder={t("dictionary.placeholder")} />
            <Button type="submit" disabled={add.isPending}><Plus className="size-4" />{t("dictionary.add")}</Button>
          </form>
        )}
        <Card className="gap-0 p-2">
          {list.data?.map((s) => (
            <div key={s.id} className="group flex items-center gap-2 rounded-lg px-2 py-1.5">
              <div className="flex flex-1 flex-wrap gap-1">
                {s.words.split(/[,;\n]/).map((w) => w.trim()).filter(Boolean).map((w) => <Badge key={w} variant="outline">{w}</Badge>)}
              </div>
              {can.edit && (
                <Button variant="ghost" size="icon" className="size-7 opacity-0 group-hover:opacity-100" onClick={() => remove.mutate(s.id)} aria-label={t("common.delete")}>
                  <Trash2 className="size-3.5" />
                </Button>
              )}
            </div>
          ))}
          {list.data && !list.data.length && <p className="p-4 text-center text-sm text-muted-foreground">{t("dictionary.empty")}</p>}
        </Card>
      </div>
      <div>
        <SectionTitle>{t("dictionary.explain")}</SectionTitle>
        <p className="-mt-1 mb-3 text-sm text-muted-foreground">{t("dictionary.explainHint")}</p>
        <form className="mb-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); setAsked(probe.trim()); }}>
          <Input value={probe} onChange={(e) => setProbe(e.target.value)} placeholder="Парол / parol / пароль" />
          <Button type="submit" variant="outline"><Search className="size-4" />{t("dictionary.check")}</Button>
        </form>
        {explain.data && (
          <Card className="gap-3 p-4 text-sm">
            <div><div className="mb-1 text-xs text-muted-foreground">{t("dictionary.terms")}</div>
              <div className="flex flex-wrap gap-1">{explain.data.terms.map((w) => <Badge key={w}>{w}</Badge>)}</div></div>
            <div><div className="mb-1 text-xs text-muted-foreground">{t("dictionary.expanded")}</div>
              <div className="flex flex-wrap gap-1">{explain.data.expanded.map((w) => <Badge key={w} variant="outline">{w}</Badge>)}</div></div>
            {Object.entries(explain.data.matches).map(([term, hits]) => (
              <div key={term}>
                <div className="mb-1 font-mono text-xs">{term}</div>
                <div className="flex flex-wrap gap-1 text-xs text-muted-foreground">
                  {hits.slice(0, 12).map(([w, score]) => <span key={w} className="rounded border px-1.5">{w} <span className="font-mono">{score.toFixed(2)}</span></span>)}
                </div>
              </div>
            ))}
          </Card>
        )}
      </div>
    </div>
  );
}
