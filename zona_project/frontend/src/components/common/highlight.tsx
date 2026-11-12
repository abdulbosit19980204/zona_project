import type { Span } from "@/lib/api/types";

/** Qidiruv natijasida mos kelgan so'zlarni ajratib ko'rsatadi (backend [start, end] oraliqlari). */
export function Highlight({ text, spans }: { text: string; spans?: Span[] }) {
  if (!spans?.length) return <>{text}</>;
  const parts: React.ReactNode[] = [];
  let pos = 0;
  spans.forEach(([s, e], i) => {
    if (s < pos) return;
    parts.push(text.slice(pos, s));
    parts.push(<mark key={i} className="rounded bg-primary/20 px-0.5 text-inherit">{text.slice(s, e)}</mark>);
    pos = e;
  });
  parts.push(text.slice(pos));
  return <>{parts}</>;
}
