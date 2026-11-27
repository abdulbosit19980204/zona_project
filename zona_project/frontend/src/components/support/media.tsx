"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileText, Film, ImageOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

import { supportApi, type MediaInfo } from "./api";
import { useSt } from "./i18n";

/** Element ekranga yaqinlashganda true (bir marta) — ro'yxatdagi rasmlar faqat ko'ringanda yuklanadi. */
function useInView() {
  const [el, setEl] = useState<Element | null>(null);
  const [seen, setSeen] = useState(() => typeof IntersectionObserver === "undefined");
  useEffect(() => {
    if (seen || !el) return;
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { setSeen(true); io.disconnect(); } },
      { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, [el, seen]);
  return [setEl, seen] as const;
}

function useBlobUrl(blob: Blob | undefined) {
  const url = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  return url;
}

/** Serverdagi faylni (tizimga kirgan holda) ko'rsatish: rasm — kichik ko'rinish, bosilsa katta; video — pleyer.
 *  Asl nusxasi serverda saqlanmaydigan rasm (eskiz) bosilganda asli bot orqali Telegram'dan olinadi; bo'lmasa — havola. */
export function MediaThumb({ m, className }: { m: MediaInfo; className?: string }) {
  const t = useSt();
  const [open, setOpen] = useState(false);
  const [ref, inView] = useInView();
  const wrap = className?.includes("w-full") ? "block w-full" : "inline-flex";  // kuzatish uchun haqiqiy quti
  const photo = m.kind === "photo";
  // ro'yxatda — faqat ko'ringanda va eskiz (rasm); asl nusxa faqat bosilganda. Kesh: qayta yuklashda so'rov ketmaydi
  const q = useQuery({ queryKey: ["support", "media", m.id, photo ? "thumb" : "file"],
    queryFn: () => supportApi.mediaBlob(m.id, photo), enabled: m.available && inView,
    staleTime: Infinity, gcTime: 30 * 60_000 });
  const orig = useQuery({ queryKey: ["support", "media", m.id, "file"], queryFn: () => supportApi.mediaBlob(m.id),
    enabled: open && photo && !m.slim && m.available, staleTime: Infinity, gcTime: 5 * 60_000 });
  const full = useQuery({ queryKey: ["support", "media-full", m.id], queryFn: () => supportApi.mediaFull(m.id),
    enabled: open && !!m.slim && photo, staleTime: Infinity, gcTime: 5 * 60_000, retry: false });
  const url = useBlobUrl(q.data);
  const fullUrl = useBlobUrl(full.data ?? orig.data);
  const box = cn("relative grid size-20 shrink-0 place-items-center overflow-hidden rounded-lg border bg-muted text-muted-foreground", className);
  if (!m.available) {
    return m.link ? (
      <a className={cn(box, "hover:text-primary")} href={m.link} target="_blank" rel="noreferrer" title={t("mediaInTelegram")}>
        <span className="grid place-items-center gap-1 text-[10px]"><ImageOff className="size-5" />Telegram</span>
      </a>
    ) : <div className={box} title={m.name}><ImageOff className="size-5" /></div>;
  }
  if (photo) {
    const big = fullUrl ?? url;
    return (
      <span ref={ref} className={wrap}>
        <button type="button" className={box} onClick={() => setOpen(true)} title={m.label_title || m.name}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {url && <img src={url} alt={m.name || "rasm"} className={cn("size-full", m.width > m.height * 1.1 ? "object-contain" : "object-cover object-top")} />}
          {m.label && <span className="absolute bottom-0 left-0 right-0 truncate bg-black/60 px-1 text-[9px] text-white">{m.label_title}</span>}
        </button>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent className="max-w-3xl">
            <DialogTitle className="truncate text-sm">{m.label_title || m.name || "Rasm"}</DialogTitle>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {big && <img src={big} alt={m.name || "rasm"} className="max-h-[75vh] w-full object-contain" />}
            {m.slim && !fullUrl && (
              <p className="text-xs text-muted-foreground">{full.isFetching ? t("mediaLoadingFull") : t("mediaThumbOnly")}</p>
            )}
            {m.link && (
              <a href={m.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
                {t("mediaInTelegram")}<ExternalLink className="size-3" />
              </a>
            )}
            {m.ocr && <p className="line-clamp-4 text-xs text-muted-foreground">{m.ocr}</p>}
          </DialogContent>
        </Dialog>
      </span>
    );
  }
  if (m.kind === "document") {
    return <span ref={ref} className={wrap}><a className={box} href={url ?? undefined} download={m.name} title={m.name}><FileText className="size-6" /></a></span>;
  }
  return <span ref={ref} className={wrap}>{url ? <video src={url} controls className={cn("h-20 w-32 rounded-lg border bg-black object-contain", className)} />
    : <div className={box}><Film className="size-5" /></div>}</span>;
}

export function MediaRow({ items }: { items: MediaInfo[] }) {
  if (!items?.length) return null;
  return <div className="flex flex-wrap gap-2">{items.map((m) => <MediaThumb key={m.id} m={m} />)}</div>;
}
