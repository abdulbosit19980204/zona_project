import type { ReactNode } from "react";

/** AI javoblari uchun kichik, xavfsiz markdown: sarlavha, ro'yxat, **qalin**. HTML qabul qilinmaydi. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <b key={i} className="text-foreground">{part.slice(2, -2)}</b> : part,
  );
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: ReactNode[] = [];
  const flush = () => {
    if (list.length) blocks.push(<ul key={`ul${blocks.length}`} className="my-1.5 list-disc space-y-1 pl-5">{list}</ul>);
    list = [];
  };
  text.replace(/\r/g, "").split("\n").forEach((raw, i) => {
    const line = raw.trim();
    if (!line) return flush();
    const heading = line.match(/^#{1,4}\s+(.*)$/);
    const item = line.match(/^(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (heading) { flush(); blocks.push(<h4 key={i} className="mb-1 mt-3 text-[13.5px] font-semibold text-foreground">{inline(heading[1])}</h4>); }
    else if (item) list.push(<li key={i}>{inline(item[1])}</li>);
    else { flush(); blocks.push(<p key={i} className="my-1.5">{inline(line)}</p>); }
  });
  flush();
  return <div className="text-[13px] leading-relaxed text-muted-foreground">{blocks}</div>;
}
