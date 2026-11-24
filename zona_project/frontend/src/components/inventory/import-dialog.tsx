"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileSpreadsheet, Upload } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/lib/api/client";

import type { ImportResult } from "./api";
import { tr, useT } from "./i18n";
import { Btn, Overlay } from "./ui";

/** Fayl tanlash → avval tekshiruv (hech narsa saqlanmaydi) → natijani ko'rib, tasdiqlash. */
export function ImportDialog({ open, onClose, title, hint, run }: {
  open: boolean; onClose: () => void; title: string; hint?: ReactNode;
  run: (file: File, dryRun: boolean) => Promise<ImportResult>;
}) {
  const t = useT();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setFile(null);
    setPreview(null);
    setDone(null);
    if (input.current) input.current.value = "";
  };
  const close = () => {
    reset();
    onClose();
  };
  const check = async (f: File) => {
    setFile(f);
    setPreview(null);
    setDone(null);
    setBusy(true);
    try {
      setPreview(await run(f, true));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const apply = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const r = await run(file, false);
      setDone(r);
      setPreview(null);
      qc.invalidateQueries({ queryKey: ["inv"], predicate: (q) => q.queryKey[1] !== "boot" });
      toast.success(t("Import tugadi"));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const result = done ?? preview;

  return (
    <Overlay open={open} onClose={close} title={title}
      footer={preview && !done ? (
        <div className="flex gap-2">
          <Btn variant="outline" className="flex-1" onClick={reset}>{t("Boshqa fayl")}</Btn>
          <Btn className="flex-1" loading={busy} onClick={apply}>{t("Tasdiqlash va saqlash")}</Btn>
        </div>
      ) : done ? <Btn className="w-full" onClick={close}>{t("Yopish")}</Btn> : undefined}>
      <div className="space-y-4 p-4">
        {hint && <div className="rounded-xl bg-muted/60 p-3 text-sm text-muted-foreground">{hint}</div>}
        <button onClick={() => input.current?.click()} disabled={busy}
          className="flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed p-6 text-center hover:border-primary/50 hover:bg-primary/5">
          {file ? <FileSpreadsheet className="size-8 text-emerald-600" /> : <Upload className="size-8 text-muted-foreground" />}
          <span className="font-semibold">{file ? file.name : t("Faylni tanlang")}</span>
          <span className="text-xs text-muted-foreground">{t("Excel (.xlsx) yoki CSV")}</span>
        </button>
        <input ref={input} type="file" hidden accept=".xlsx,.xlsm,.csv,.txt" onChange={(e) => e.target.files?.[0] && check(e.target.files[0])} />
        {busy && !result && <div className="text-center text-sm text-muted-foreground">{t("Tekshirilmoqda…")}</div>}
        {result && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              {done ? <><CheckCircle2 className="size-4 text-emerald-600" />{t("Saqlandi")}</> : t("Tekshiruv natijasi (hali saqlanmadi)")}
            </div>
            <div className="grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
              {result.created !== undefined && <Stat label={t("Yangi qurilma")} value={result.created} />}
              {result.updated !== undefined && <Stat label={t("Yangilanadi")} value={result.updated} />}
              <Stat label={t("Yangi xodim")} value={result.employees_created} />
              <Stat label={t("Xodim yangilanadi")} value={result.employees_updated} />
            </div>
            {!!result.errors.length && (
              <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-3">
                <div className="mb-1 text-sm font-semibold text-red-700 dark:text-red-400">{t("{n} ta qator o'tkazib yuboriladi", { n: result.errors.length })}</div>
                <div className="max-h-48 space-y-0.5 overflow-y-auto text-xs">
                  {result.errors.map((e, i) => <div key={i}>{e.sheet ? `${e.sheet}, ` : ""}{tr("{n}-qator", { n: e.row })}: {e.message}</div>)}
                </div>
              </div>
            )}
            {!!result.warnings.length && (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-xs">
                {result.warnings.map((e, i) => <div key={i}>{tr("{n}-qator", { n: e.row })}: {e.message}</div>)}
              </div>
            )}
          </div>
        )}
      </div>
    </Overlay>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border bg-card p-2">
      <div className="text-xl font-bold tabular-nums">{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}
