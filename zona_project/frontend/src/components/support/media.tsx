"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText, Film, ImageOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

import { supportApi, type MediaInfo } from "./api";

/** Serverdagi faylni (tizimga kirgan holda) ko'rsatish: rasm — kichik ko'rinish, bosilsa katta; video — pleyer. */
export function MediaThumb({ m, className }: { m: MediaInfo; className?: string }) {
  const [open, setOpen] = useState(false);
  const q = useQuery({ queryKey: ["support", "media", m.id], queryFn: () => supportApi.mediaBlob(m.id), enabled: m.available,
    staleTime: Infinity, gcTime: 10 * 60_000 });
  const url = useMemo(() => (q.data ? URL.createObjectURL(q.data) : null), [q.data]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  const box = cn("relative grid size-20 shrink-0 place-items-center overflow-hidden rounded-lg border bg-muted text-muted-foreground", className);
  if (!m.available) return <div className={box} title={m.name}><ImageOff className="size-5" /></div>;
  if (m.kind === "photo") {
    return (
      <>
        <button type="button" className={box} onClick={() => setOpen(true)} title={m.label_title || m.name}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {url && <img src={url} alt={m.name || "rasm"} className={cn("size-full", m.width > m.height * 1.1 ? "object-contain" : "object-cover object-top")} />}
          {m.label && <span className="absolute bottom-0 left-0 right-0 truncate bg-black/60 px-1 text-[9px] text-white">{m.label_title}</span>}
        </button>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent className="max-w-3xl">
            <DialogTitle className="truncate text-sm">{m.label_title || m.name || "Rasm"}</DialogTitle>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {url && <img src={url} alt={m.name || "rasm"} className="max-h-[75vh] w-full object-contain" />}
            {m.ocr && <p className="line-clamp-4 text-xs text-muted-foreground">{m.ocr}</p>}
          </DialogContent>
        </Dialog>
      </>
    );
  }
  if (m.kind === "document") {
    return <a className={box} href={url ?? undefined} download={m.name} title={m.name}><FileText className="size-6" /></a>;
  }
  return url ? <video src={url} controls className={cn("h-20 w-32 rounded-lg border bg-black object-contain", className)} />
    : <div className={box}><Film className="size-5" /></div>;
}

export function MediaRow({ items }: { items: MediaInfo[] }) {
  if (!items?.length) return null;
  return <div className="flex flex-wrap gap-2">{items.map((m) => <MediaThumb key={m.id} m={m} />)}</div>;
}
