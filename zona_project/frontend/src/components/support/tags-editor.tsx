"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

import { supportApi, type SupportTag } from "./api";
import { Panel, useSupportMutation } from "./common";
import type { ST } from "./i18n";

/** Teglar (savol turlari): nomi va kalit so'zlari — saqlansa, barcha savollarga avtomatik teglar qayta qo'yiladi
 *  (qo'lda tahrirlanganlardan tashqari). Kalit so'z — oddiy so'z yoki "re:" bilan boshlanadigan regex. */
export function TagsEditor({ t }: { t: ST }) {
  const q = useQuery({ queryKey: ["support", "tags"], queryFn: supportApi.tags });
  return q.data ? <Body key={q.dataUpdatedAt} initial={q.data} t={t} /> : null;
}

function Body({ initial, t }: { initial: SupportTag[]; t: ST }) {
  const [rows, setRows] = useState(initial.map((x) => ({ ...x, words: (x.keywords || []).join(", ") })));
  const save = useSupportMutation(() => supportApi.saveTags(rows.map((r) => ({
    key: r.key, title: r.title, color: r.color, active: r.active,
    keywords: r.words.split(",").map((w) => w.trim()).filter(Boolean) }))), t("saved"));
  const upd = (i: number, patch: Partial<(typeof rows)[number]>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <Panel title={t("tagsTitle")} hint={t("tagsHint")}
      actions={<Button size="sm" onClick={() => save.mutate(undefined)} disabled={save.isPending}><Save className="size-4" />{t("save")}</Button>}>
      <div className="grid gap-2">
        {rows.map((r, i) => (
          <div key={i} className="grid items-center gap-2 rounded-lg border p-2 md:grid-cols-[160px_1fr_auto_auto_auto]">
            <Input value={r.title} onChange={(e) => upd(i, { title: e.target.value })} placeholder={t("tagsName")} className="h-8" />
            <Input value={r.words} onChange={(e) => upd(i, { words: e.target.value })} placeholder={t("tagsWords")} className="h-8 font-mono text-xs" />
            <span className="text-xs tabular-nums text-muted-foreground">{r.questions ?? 0}</span>
            <Switch checked={r.active} onCheckedChange={(v) => upd(i, { active: v })} aria-label={t("tagsActive")} />
            <Button size="icon" variant="ghost" className="size-8" onClick={() => setRows(rows.filter((_, j) => j !== i))} aria-label={t("delete")}>
              <Trash2 className="size-4" />
            </Button>
          </div>
        ))}
        <Button size="sm" variant="outline" className="justify-self-start" onClick={() => setRows([...rows, { key: "", title: "", keywords: [], color: "", active: true, words: "", questions: 0 }])}>
          <Plus className="size-4" />{t("tagsAdd")}
        </Button>
      </div>
    </Panel>
  );
}
