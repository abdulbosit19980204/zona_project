"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Maximize2, Minus, Plus, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import { createPortal } from "react-dom";

import { api } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/** Qo'llanma rasmi: kirish talab qiladi — token bilan blob sifatida yuklanadi (kesh: shu rasm bir marta). */
export function useDocImage(src: string) {
  const q = useQuery({
    queryKey: ["docs", "img", src], staleTime: Infinity,
    queryFn: async () => (await api.get<Blob>(`docs/${src.replace(/^\.?\//, "")}`, { responseType: "blob" })).data,
  });
  const url = useMemo(() => (q.data ? URL.createObjectURL(q.data) : ""), [q.data]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  return { url, error: q.isError };
}

export interface ViewerImage { src: string; alt: string }

const MIN = 0.2;
const MAX = 6;
const clamp = (v: number) => Math.min(MAX, Math.max(MIN, v));

/** Rasm ko'rish oynasi (modal): kattalashtirish / kichraytirish (tugma, g'ildirak, +/−, ikki marta bosish), sichqoncha
 * bilan siljitish, ← → bobdagi boshqa rasmlar, Esc / ✕ / fon — yopish. */
export function ImageViewer({ images, index, onIndex, onClose }: {
  images: ViewerImage[]; index: number; onIndex: (i: number) => void; onClose: () => void;
}) {
  const img = images[index];
  const { url, error } = useDocImage(img.src);
  const box = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const natural = useRef({ w: 0, h: 0 });
  const drag = useRef<{ x: number; y: number; ox: number; oy: number; moved: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);

  /** Ekranga sig'adigan o'lcham (100% dan katta qilinmaydi). */
  const fit = useCallback(() => {
    const el = box.current;
    const { w, h } = natural.current;
    if (!el || !w) return 1;
    return Math.min(1, (el.clientWidth - 48) / w, (el.clientHeight - 48) / h);
  }, []);
  const reset = useCallback(() => setView({ scale: fit(), x: 0, y: 0 }), [fit]);

  const zoomAt = useCallback((factor: number, cx = 0, cy = 0) => {
    setView((v) => {
      const scale = clamp(v.scale * factor);
      const k = scale / v.scale;
      return { scale, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k };
    });
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "+" || e.key === "=") zoomAt(1.25);
      else if (e.key === "-") zoomAt(0.8);
      else if (e.key === "0") reset();
      else if (e.key === "ArrowRight" && index < images.length - 1) onIndex(index + 1);
      else if (e.key === "ArrowLeft" && index > 0) onIndex(index - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, zoomAt, reset, index, images.length, onIndex]);

  const center = (e: { clientX: number; clientY: number }) => {
    const r = box.current!.getBoundingClientRect();
    return [e.clientX - r.left - r.width / 2, e.clientY - r.top - r.height / 2] as const;
  };
  const onWheel = (e: WheelEvent) => {
    const [cx, cy] = center(e);
    zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, cx, cy);
  };
  const onDown = (e: PointerEvent) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, ox: view.x, oy: view.y, moved: false };
    setDragging(true);
  };
  const onMove = (e: PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
    setView((v) => ({ ...v, x: d.ox + dx, y: d.oy + dy }));
  };
  const onUp = (e: PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    setDragging(false);
    if (d && !d.moved && e.target === box.current) onClose();  // fonni bosish — yopish
  };
  const onDouble = (e: { clientX: number; clientY: number }) => {
    const [cx, cy] = center(e);
    if (view.scale < 1.5) zoomAt(2 / view.scale, cx, cy);
    else reset();
  };

  const btn = "grid size-9 place-items-center rounded-lg text-white/90 transition-colors hover:bg-white/15 disabled:opacity-30";
  return createPortal(
    <div className="fixed inset-0 z-[100] flex flex-col bg-black/85 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={img.alt}>
      <div className="flex shrink-0 items-center gap-1 px-3 py-2 text-white">
        <div className="min-w-0 flex-1 truncate px-2 text-sm">
          {img.alt}
          {images.length > 1 && <span className="ml-2 text-white/50">{index + 1} / {images.length}</span>}
        </div>
        <button type="button" className={btn} onClick={() => zoomAt(0.8)} title="Kichraytirish (−)"><Minus className="size-4" /></button>
        <button type="button" className="h-9 min-w-16 rounded-lg px-2 font-mono text-xs text-white/90 hover:bg-white/15" onClick={reset} title="Ekranga moslash (0)">
          {Math.round(view.scale * 100)}%
        </button>
        <button type="button" className={btn} onClick={() => zoomAt(1.25)} title="Kattalashtirish (+)"><Plus className="size-4" /></button>
        <button type="button" className={btn} onClick={() => setView({ scale: 1, x: 0, y: 0 })} title="Asl o'lcham (100%)"><Maximize2 className="size-4" /></button>
        <span className="mx-1 h-5 w-px bg-white/20" />
        <button type="button" className={btn} onClick={onClose} title="Yopish (Esc)"><X className="size-5" /></button>
      </div>
      <div ref={box} className={cn("relative min-h-0 flex-1 touch-none select-none overflow-hidden", dragging ? "cursor-grabbing" : "cursor-grab")}
        onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onDoubleClick={onDouble}>
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob URL (token bilan yuklangan)
          <img src={url} alt={img.alt} draggable={false}
            onLoad={(e) => { natural.current = { w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight }; reset(); }}
            className="pointer-events-none absolute left-1/2 top-1/2 max-w-none rounded-md shadow-2xl"
            style={{ transform: `translate(calc(-50% + ${view.x}px), calc(-50% + ${view.y}px)) scale(${view.scale})`, transformOrigin: "center" }} />
        ) : (
          <div className="grid h-full place-items-center text-sm text-white/70">{error ? "Rasm yuklanmadi" : "Yuklanmoqda…"}</div>
        )}
        {index > 0 && (
          <button type="button" className="absolute left-3 top-1/2 grid size-11 -translate-y-1/2 place-items-center rounded-full bg-black/50 text-white hover:bg-black/70"
            onPointerDown={(e) => e.stopPropagation()} onClick={() => onIndex(index - 1)} title="Oldingi (←)"><ChevronLeft className="size-6" /></button>
        )}
        {index < images.length - 1 && (
          <button type="button" className="absolute right-3 top-1/2 grid size-11 -translate-y-1/2 place-items-center rounded-full bg-black/50 text-white hover:bg-black/70"
            onPointerDown={(e) => e.stopPropagation()} onClick={() => onIndex(index + 1)} title="Keyingi (→)"><ChevronRight className="size-6" /></button>
        )}
      </div>
      <div className="shrink-0 pb-2 text-center text-[11px] text-white/45">
        G&apos;ildirak — kattalashtirish · sudrash — siljitish · ikki marta bosish — 200% / moslash · ← → — boshqa rasmlar · Esc — yopish
      </div>
    </div>
  , document.body);
}
