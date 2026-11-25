"use client";

import Link from "next/link";
import { Fragment, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Qo'llanma uchun kichik Markdown renderer (tashqi kutubxonasiz): sarlavhalar, paragraflar, ro'yxatlar, jadvallar,
 * kod bloklari, iqtiboslar (> — eslatma), **qalin**, *kursiv*, `kod`, [havola](url). HTML qabul qilinmaydi (xavfsiz). */

export function slugify(s: string) {
  return s.toLowerCase().replace(/[`*_[\]()]/g, "").replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "");
}

function inline(text: string, key = 0): ReactNode[] {
  const out: ReactNode[] = [];
  const rx = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\*[^*\s][^*]*\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = rx.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    const k = `${key}-${i++}`;
    if (tok.startsWith("**")) out.push(<strong key={k} className="font-semibold text-foreground">{inline(tok.slice(2, -2), i)}</strong>);
    else if (tok.startsWith("`")) out.push(<code key={k} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em]">{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("[")) {
      const mm = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok)!;
      const href = mm[2];
      const internal = href.startsWith("/");
      out.push(internal
        ? <Link key={k} href={href} className="text-primary underline-offset-2 hover:underline">{mm[1]}</Link>
        : <a key={k} href={href} target="_blank" rel="noreferrer" className="text-primary underline-offset-2 hover:underline">{mm[1]}</a>);
    } else out.push(<em key={k}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** Jadval qatori: "\|" — katak ichidagi oddiy "|" belgisi (ajratuvchi emas). */
const cells = (line: string) => line.trim().replace(/^\||(?<!\\)\|$/g, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));

export function Markdown({ text, className }: { text: string; className?: string }) {
  const lines = text.replace(/\r/g, "").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let n = 0;
  while (i < lines.length) {
    const line = lines[i];
    const k = n++;
    if (!line.trim()) { i++; continue; }
    if (line.startsWith("```")) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) body.push(lines[i++]);
      i++;
      blocks.push(<pre key={k} className="my-3 overflow-x-auto rounded-lg border bg-muted/50 p-3 font-mono text-xs leading-relaxed">{body.join("\n")}</pre>);
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const id = slugify(h[2]);
      const cls = ["", "text-2xl font-bold tracking-tight", "mt-8 border-b pb-2 text-xl font-semibold", "mt-6 text-base font-semibold", "mt-4 text-sm font-semibold"][level];
      const Tag = (["h1", "h1", "h2", "h3", "h4"] as const)[level];
      blocks.push(<Tag key={k} id={id} className={cn("scroll-mt-20", cls)}>{inline(h[2], k)}</Tag>);
      i++;
      continue;
    }
    if (line.startsWith(">")) {
      const body: string[] = [];
      while (i < lines.length && lines[i].startsWith(">")) body.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push(<div key={k} className="my-3 rounded-lg border-l-4 border-primary/50 bg-primary/5 px-4 py-2.5 text-sm">{inline(body.join(" "), k)}</div>);
      continue;
    }
    if (line.trim().startsWith("|") && i + 1 < lines.length && /^\s*\|?[\s:-]+\|/.test(lines[i + 1])) {
      const head = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(cells(lines[i++]));
      blocks.push(
        <div key={k} className="my-3 overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50"><tr>{head.map((c, j) => <th key={j} className="px-3 py-2 text-left font-semibold">{inline(c, j)}</th>)}</tr></thead>
            <tbody className="divide-y">{rows.map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j} className="px-3 py-2 align-top">{inline(c, j)}</td>)}</tr>)}</tbody>
          </table>
        </div>);
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items: { depth: number; text: string }[] = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        const mm = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(lines[i])!;
        items.push({ depth: Math.min(2, Math.floor(mm[1].length / 2)), text: mm[3] });
        i++;
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
          items[items.length - 1].text += " " + lines[i].trim();
          i++;
        }
      }
      const Tag = ordered ? "ol" : "ul";
      blocks.push(
        <Tag key={k} className={cn("my-2 space-y-1 pl-5 text-sm leading-relaxed", ordered ? "list-decimal" : "list-disc")}>
          {items.map((it, j) => <li key={j} style={{ marginLeft: it.depth * 18 }}>{inline(it.text, j)}</li>)}
        </Tag>);
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|>|\s*([-*]|\d+\.)\s+|\s*\|)/.test(lines[i])) para.push(lines[i++].trim());
    if (!para.length) { para.push(line); i++; }
    blocks.push(<p key={k} className="my-2 text-sm leading-relaxed text-foreground/90">{inline(para.join(" "), k)}</p>);
  }
  return <div className={className}>{blocks.map((b, j) => <Fragment key={j}>{b}</Fragment>)}</div>;
}

/** Bobdagi ## va ### sarlavhalar — o'ng tomondagi mundarija uchun. */
export function headings(text: string) {
  return text.split("\n").map((l) => /^(#{2,3})\s+(.*)$/.exec(l)).filter(Boolean)
    .map((m) => ({ level: m![1].length, title: m![2].replace(/[`*]/g, ""), id: slugify(m![2]) }));
}
