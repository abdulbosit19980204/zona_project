"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Eraser, Loader2, PenLine, ShieldCheck, X } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { useUI } from "@/stores/ui";

import { inv, type Ack } from "./api";
import { condLabel, useLang, useT } from "./i18n";
import { Btn, dt, inputCls } from "./ui";

/* ------------------------------------------------------------------ imzo maydoni (barmoq / sichqoncha) */
function SignaturePad({ onChange }: { onChange: (dataUrl: string) => void }) {
  const t = useT();
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const strokes = useRef(0);
  const last = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const ratio = Math.max(1, window.devicePixelRatio || 1);
    const rect = c.getBoundingClientRect();
    c.width = rect.width * ratio;
    c.height = rect.height * ratio;
    const ctx = c.getContext("2d")!;
    ctx.scale(ratio, ratio);
    ctx.lineWidth = 2.4;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#0f172a";
  }, []);

  const point = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const down = (e: React.PointerEvent<HTMLCanvasElement>) => {
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* ba'zi brauzerlar */ }
    drawing.current = true;
    last.current = point(e);
  };
  const move = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current || !last.current) return;
    const ctx = e.currentTarget.getContext("2d")!;
    const p = point(e);
    ctx.beginPath();
    ctx.moveTo(last.current.x, last.current.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    last.current = p;
  };
  const up = () => {
    if (!drawing.current) return;
    drawing.current = false;
    strokes.current += 1;
    if (strokes.current >= 1 && canvas.current) onChange(canvas.current.toDataURL("image/png"));
  };
  const clear = () => {
    const c = canvas.current;
    if (!c) return;
    c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
    strokes.current = 0;
    onChange("");
  };

  return (
    <div>
      <div className="relative overflow-hidden rounded-2xl border-2 border-dashed bg-white">
        <canvas ref={canvas} className="block h-44 w-full touch-none" onPointerDown={down} onPointerMove={move}
          onPointerUp={up} onPointerCancel={up} onPointerLeave={up} />
        <div className="pointer-events-none absolute bottom-3 left-4 right-4 border-b border-slate-300" />
        <span className="pointer-events-none absolute left-4 top-3 flex items-center gap-1 text-xs text-slate-400"><PenLine className="size-3.5" />{t("Shu yerga barmog'ingiz bilan imzo qo'ying")}</span>
      </div>
      <button type="button" onClick={clear} className="mt-2 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <Eraser className="size-4" />{t("Tozalash")}
      </button>
    </div>
  );
}

function LangSwitch() {
  const lang = useLang();
  const setLocale = useUI((s) => s.setLocale);
  return (
    <div className="flex rounded-xl border bg-card p-0.5 text-sm font-semibold">
      {(["uz", "ru"] as const).map((l) => (
        <button key={l} onClick={() => setLocale(l)} className={cn("h-9 rounded-lg px-3", lang === l ? "bg-indigo-600 text-white" : "text-muted-foreground")}>
          {l === "uz" ? "O'zbek" : "Русский"}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ sahifa */
export function AckPublicPage() {
  const t = useT();
  const lang = useLang();
  const { token } = useParams<{ token: string }>();
  const q = useQuery({ queryKey: ["ack-public", token], queryFn: () => inv.publicAck(token), retry: false });
  const [answers, setAnswers] = useState<Record<number, { ok: boolean; comment: string }>>({});
  const [name, setName] = useState("");
  const [comment, setComment] = useState("");
  const [signature, setSignature] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<Ack | null>(null);
  const [zoom, setZoom] = useState<string | null>(null);
  const a = done ?? q.data;

  useEffect(() => {
    // birinchi ochilishda — telefon tili rus bo'lsa, rus tilida
    try {
      if (!localStorage.getItem("inv-ack-lang") && navigator.language?.toLowerCase().startsWith("ru")) useUI.getState().setLocale("ru");
      localStorage.setItem("inv-ack-lang", "1");
    } catch { /* yo'q */ }
  }, []);

  const submit = async () => {
    setError("");
    if (name.trim().split(/\s+/).length < 2) return setError(t("Ism-familiyangizni to'liq yozing."));
    if (!signature) return setError(t("Imzo qo'ying (barmoq bilan chizing)."));
    setBusy(true);
    try {
      const items = (a?.items ?? []).map((it) => ({ id: it.id, ok: answers[it.id]?.ok ?? true, comment: answers[it.id]?.comment ?? "" }));
      setDone(await inv.publicSign(token, { name: name.trim(), signature, items, comment, lang }));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-background">
      <div className="mx-auto max-w-xl px-4 pb-16 pt-5">
        <div className="mb-5 flex items-center gap-3">
          <span className="grid size-11 place-items-center rounded-2xl bg-indigo-600 text-white"><ShieldCheck className="size-6" /></span>
          <div className="min-w-0 flex-1 leading-tight">
            <div className="font-bold">StarGroup</div>
            <div className="text-xs text-muted-foreground">{t("IT inventarizatsiya — qurilmalarni tasdiqlash")}</div>
          </div>
          <LangSwitch />
        </div>

        {q.isLoading && <div className="grid place-items-center py-20"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>}
        {q.isError && !done && (
          <div className="rounded-2xl border border-red-500/30 bg-red-500/5 p-6 text-center">
            <X className="mx-auto mb-2 size-8 text-red-500" />
            <div className="font-semibold">{t("Havola topilmadi yoki bekor qilingan.")}</div>
            <p className="mt-1 text-sm text-muted-foreground">{t("Inventarizatsiya o'tkazayotgan xodimdan yangi havola so'rang.")}</p>
          </div>
        )}

        {a && (
          <>
            <div className="mb-4 rounded-2xl border bg-card p-4">
              <div className="text-xs text-muted-foreground">{t("Xodim")}</div>
              <div className="text-lg font-bold">{a.employee_name}</div>
              <div className="text-sm text-muted-foreground">{[a.position, a.branch].filter(Boolean).join(" · ")}</div>
            </div>

            {a.status === "signed" ? (
              <div className="mb-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-5 text-center">
                <CheckCircle2 className="mx-auto mb-2 size-10 text-emerald-600" />
                <div className="text-lg font-bold">{t("Rahmat! Tasdiqlandi.")}</div>
                <p className="mt-1 text-sm text-muted-foreground">{t("{n} imzoladi · {d}", { n: a.signer_name, d: dt(a.signed_at) })}</p>
              </div>
            ) : (
              <div className="mb-4 rounded-2xl bg-indigo-500/[0.06] p-4 text-sm">
                {t("Quyida sizga biriktirilgan qurilmalar. Har birini tekshiring: sizda bo'lsa — «Menda bor», bo'lmasa — «Menda yo'q» ni bosib sababini yozing. Oxirida ismingizni yozib, imzo qo'ying.")}
              </div>
            )}

            <div className="space-y-3">
              {(a.items ?? []).map((it, i) => {
                const ans = a.status === "signed" ? it.result ?? { ok: true, comment: "" } : answers[it.id] ?? { ok: true, comment: "" };
                const set = (v: Partial<{ ok: boolean; comment: string }>) => setAnswers((x) => ({ ...x, [it.id]: { ...ans, ...v } }));
                return (
                  <div key={it.id} className={cn("rounded-2xl border bg-card p-3", !ans.ok && "border-red-500/40")}>
                    <div className="flex gap-3">
                      <div className="flex shrink-0 gap-1.5">
                        {it.photos.slice(0, 2).map((p) => (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img key={p.thumb} src={p.thumb} alt="" onClick={() => setZoom(p.url)} className="size-16 rounded-xl border object-cover" />
                        ))}
                        {!it.photos.length && <div className="grid size-16 place-items-center rounded-xl bg-muted text-lg font-bold text-muted-foreground">{i + 1}</div>}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="font-semibold leading-snug">{(lang === "ru" && it.type_ru) || it.type}</div>
                        <div className="text-sm text-muted-foreground">{[it.brand, it.model].filter(Boolean).join(" ") || "—"}{it.quantity > 1 && ` · ×${it.quantity}`}</div>
                        <div className="mt-0.5 text-xs text-muted-foreground"><span className="font-mono">{it.inv_number}</span>{it.serial && ` · S/N ${it.serial}`} · {condLabel(it.condition, lang)}</div>
                      </div>
                    </div>
                    {a.status === "signed" ? (
                      <div className={cn("mt-2 text-sm font-semibold", ans.ok ? "text-emerald-600" : "text-red-600")}>
                        {ans.ok ? `✓ ${t("Menda bor")}` : `✕ ${t("Menda yo'q")}${ans.comment ? `: ${ans.comment}` : ""}`}
                      </div>
                    ) : (
                      <>
                        <div className="mt-3 grid grid-cols-2 gap-2">
                          <button onClick={() => set({ ok: true })} className={cn("h-11 rounded-xl border text-sm font-semibold",
                            ans.ok ? "border-emerald-600 bg-emerald-600 text-white" : "bg-card text-muted-foreground")}>✓ {t("Menda bor")}</button>
                          <button onClick={() => set({ ok: false })} className={cn("h-11 rounded-xl border text-sm font-semibold",
                            !ans.ok ? "border-red-600 bg-red-600 text-white" : "bg-card text-muted-foreground")}>✕ {t("Menda yo'q")}</button>
                        </div>
                        {!ans.ok && (
                          <input className={cn(inputCls, "mt-2")} value={ans.comment} onChange={(e) => set({ comment: e.target.value })}
                            placeholder={t("Sababi: kimda, qayerda yoki boshqa qurilma…")} />
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            </div>

            {a.status !== "signed" && (
              <div className="mt-5 space-y-4 rounded-2xl border bg-card p-4">
                <label className="block">
                  <span className="mb-1.5 block text-sm font-semibold">{t("Izoh (ixtiyoriy)")}</span>
                  <textarea className={cn(inputCls, "h-auto min-h-16 py-2.5")} value={comment} onChange={(e) => setComment(e.target.value)}
                    placeholder={t("Ro'yxatda yo'q, lekin sizdagi qurilma bo'lsa — shu yerga yozing")} />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-sm font-semibold">{t("Familiya va ismingiz")} *</span>
                  <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" placeholder={a.employee_name} />
                </label>
                <div>
                  <span className="mb-1.5 block text-sm font-semibold">{t("Imzo")} *</span>
                  <SignaturePad onChange={setSignature} />
                </div>
                <p className="text-xs text-muted-foreground">{t("«Tasdiqlayman» tugmasini bosib, yuqoridagi qurilmalar menda ekanini (yoki ko'rsatilgan e'tirozlarni) tasdiqlayman.")}</p>
                {error && <div className="rounded-xl bg-red-500/10 p-3 text-sm text-red-700">{error}</div>}
                <Btn size="lg" className="w-full" loading={busy} onClick={submit}><CheckCircle2 className="size-5" />{t("Tasdiqlayman va imzolayman")}</Btn>
              </div>
            )}
          </>
        )}
      </div>
      {zoom && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-3" onClick={() => setZoom(null)}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={zoom} alt="" className="max-h-full max-w-full rounded-lg object-contain" />
        </div>
      )}
    </div>
  );
}
