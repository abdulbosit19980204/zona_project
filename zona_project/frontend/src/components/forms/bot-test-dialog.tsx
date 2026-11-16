"use client";

import { useMutation } from "@tanstack/react-query";
import { Bot, Copy, Loader2, Send } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ContactLinks } from "@/components/common/contacts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api/client";
import { knowledgeApi } from "@/lib/api/endpoints";
import type { KnowledgeContact } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** Telegram bot qanday javob berishini sinash: savol → zona, qoida, mas'ul va kontaktlari. */
export function BotTestDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const t = useTranslations("knowledge");
  const [q, setQ] = useState("");
  const ask = useMutation({ mutationFn: (question: string) => knowledgeApi.ask(question), onError: (e) => toast.error(errorMessage(e)) });
  const res = ask.data;
  const best = res?.best;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Bot className="size-5 text-primary" />{t("botTest")}</DialogTitle>
          <DialogDescription>{t("botTestHint")}</DialogDescription>
        </DialogHeader>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 3) ask.mutate(q.trim()); }}>
          <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("botPlaceholder")} className="h-10" />
          <Button type="submit" className="h-10" disabled={q.trim().length < 3 || ask.isPending}>
            {ask.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}{t("botAsk")}
          </Button>
        </form>
        <div className="flex flex-wrap gap-1.5">
          {["klient agentda ko'rinmayapti", "parolni unutdim", "aksiya ishlamayapti", "marshrutga tochka qo'shish", "zakazni o'chirish"].map((s) => (
            <button key={s} type="button" onClick={() => { setQ(s); ask.mutate(s); }} className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground">{s}</button>
          ))}
        </div>

        {res && (
          <div className="space-y-3">
            <div className={cn("flex items-center gap-2 text-sm", res.found ? "text-success" : "text-warning")}>
              <span className={cn("size-2 rounded-full", res.found ? "bg-success" : "bg-warning")} />
              {res.found ? t("botFound", { confidence: res.confidence }) : t("botNotFound")}
            </div>
            {best && (
              <div className="rounded-xl border">
                <div className="border-b bg-muted/40 px-4 py-2.5">
                  <div className="text-[11px] text-muted-foreground">{[best.zone, best.process].filter(Boolean).join(" → ")}</div>
                  <div className="font-semibold">{best.question}</div>
                </div>
                <div className="space-y-3 px-4 py-3">
                  {best.responsible && <Who label={t("botWho")} c={best.responsible} primary />}
                  {best.rule && (
                    <div className="rounded-lg border-l-[3px] border-primary bg-muted/30 px-3 py-2">
                      <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-primary">{t("rule")}</div>
                      <p className="whitespace-pre-line text-[13px] leading-relaxed">{best.rule}</p>
                    </div>
                  )}
                  {best.escalation.map((c, i) => <Who key={c.id} label={`${i + 2}-${t("botNext")}${c.condition ? ` — ${c.condition}` : ""}`} c={c} />)}
                </div>
              </div>
            )}
            <div>
              <div className="mb-1 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                {t("botTelegramPreview")}
                <Button
                  variant="ghost" size="sm" className="h-6 px-2 text-xs"
                  onClick={async () => { await navigator.clipboard.writeText(res.answer_text); toast.success(t("copied")); }}
                ><Copy className="size-3" />{t("copy")}</Button>
              </div>
              <pre className="whitespace-pre-wrap rounded-lg border bg-muted/40 p-3 font-sans text-[12.5px] leading-relaxed">{res.answer_text}</pre>
            </div>
            {!!res.alternatives.length && (
              <div className="text-xs text-muted-foreground">
                {t("botAlternatives")}: {res.alternatives.map((a) => a.question).join(" · ")}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Who({ label, c, primary }: { label: string; c: KnowledgeContact; primary?: boolean }) {
  return (
    <div className={cn("rounded-lg border px-3 py-2", primary && "border-primary/40 bg-primary/5")}>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mb-1.5 text-sm font-medium">{c.name} <span className="font-normal text-muted-foreground">· {c.role}</span></div>
      <ContactLinks contact={{ phone: c.phone, telegram: c.telegram, email: c.email }} empty="—" />
    </div>
  );
}
