"use client";

import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown, Search } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { Segmented } from "./common";
import type { ST } from "./i18n";
import { smartFilter } from "./smart-search";

export type Column<T> = {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** saralash qiymati — bo'lsa sarlavha bosilganda saralanadi */
  sort?: (row: T) => string | number | null | undefined;
  align?: "right";
  className?: string;
};

export type Filter<T> = { value: string; label: ReactNode; test: (row: T) => boolean };

const SIZES = [25, 50, 100, 250];

/** Katta ro'yxatlar uchun jadval: aqlli qidiruv, filtrlar (sanoq bilan), ustun bo'yicha saralash, sahifalash,
 * uzun ro'yxatda qotib turadigan sarlavha. Hammasi brauzerda — minglab qatorlarda ham tez. */
export function DataTable<T>({ rows, columns, rowKey, t, search, filters, initialSort, pageSize = 50, loading, empty,
  toolbar, maxHeight = "70vh", rowClassName }: {
  rows: T[] | undefined;
  columns: Column<T>[];
  rowKey: (row: T) => string | number;
  t: ST;
  /** qidiruv matni (ism, username, ...) — berilmasa qidiruv maydoni ko'rinmaydi */
  search?: (row: T) => string;
  filters?: Filter<T>[];
  initialSort?: { key: string; dir: "asc" | "desc" };
  pageSize?: number;
  loading?: boolean;
  empty?: ReactNode;
  toolbar?: ReactNode;
  maxHeight?: string;
  rowClassName?: (row: T) => string | undefined;
}) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState(filters?.[0]?.value ?? "");
  const [sort, setSort] = useState(initialSort);
  const [size, setSize] = useState(pageSize);
  const [page, setPage] = useState(0);
  const all = useMemo(() => rows ?? [], [rows]);

  const counts = useMemo(() => Object.fromEntries((filters ?? []).map((f) => [f.value, all.filter(f.test).length])), [all, filters]);
  const view = useMemo(() => {
    const f = filters?.find((x) => x.value === filter);
    let out = f ? all.filter(f.test) : all;
    if (search && q.trim()) out = smartFilter(out, q, search);  // qidiruvda eng mos qatorlar yuqorida
    else if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      if (col?.sort) {
        const k = col.sort;
        out = [...out].sort((a, b) => {
          const x = k(a), y = k(b);
          if (x == null && y == null) return 0;
          if (x == null) return 1;
          if (y == null) return -1;
          const r = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
          return sort.dir === "asc" ? r : -r;
        });
      }
    }
    return out;
  }, [all, filters, filter, search, q, sort, columns]);

  const pages = Math.max(1, Math.ceil(view.length / size));
  const cur = Math.min(page, pages - 1);
  const shown = view.slice(cur * size, cur * size + size);

  const toggleSort = (c: Column<T>) => {
    if (!c.sort) return;
    setPage(0);
    setSort((s) => (s?.key === c.key ? { key: c.key, dir: s.dir === "asc" ? "desc" : "asc" } : { key: c.key, dir: c.align === "right" ? "desc" : "asc" }));
  };

  return (
    <div className="grid gap-2">
      {(search || filters || toolbar) && (
        <div className="flex flex-wrap items-center gap-2">
          {search && (
            <div className="relative w-full sm:w-72">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder={t("dtSearch")} className="h-9 pl-8" />
            </div>
          )}
          {filters && filters.length > 1 && (
            <Segmented size="sm" value={filter} onChange={(v) => { setFilter(v); setPage(0); }}
              options={filters.map((f) => ({ value: f.value, label: f.label, count: counts[f.value] }))} />
          )}
          {toolbar}
          <span className="ml-auto text-xs tabular-nums text-muted-foreground">{t("dtShown", { n: view.length, total: all.length })}</span>
        </div>
      )}
      <div className="overflow-auto rounded-xl border bg-card" style={{ maxHeight }}>
        <table className="w-full caption-bottom text-sm">
          <thead className="sticky top-0 z-10 bg-muted/95 backdrop-blur supports-[backdrop-filter]:bg-muted/80">
            <tr className="border-b">
              {columns.map((c, i) => {
                const on = sort?.key === c.key && !(search && q.trim());
                const Icon = !c.sort ? null : on ? (sort!.dir === "asc" ? ArrowUp : ArrowDown) : ChevronsUpDown;
                return (
                  <th key={c.key} scope="col" aria-sort={on ? (sort!.dir === "asc" ? "ascending" : "descending") : undefined}
                    className={cn("h-10 whitespace-nowrap px-3 text-left align-middle text-xs font-medium text-muted-foreground",
                      c.align === "right" && "text-right", i === 0 && "pl-4", i === columns.length - 1 && "pr-4", c.className)}>
                    {c.sort ? (
                      <button type="button" onClick={() => toggleSort(c)}
                        className={cn("inline-flex items-center gap-1 hover:text-foreground", on && "text-foreground")}>
                        {c.header}{Icon && <Icon className="size-3.5 opacity-70" />}
                      </button>
                    ) : c.header}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="[&_tr:last-child]:border-0">
            {loading && Array.from({ length: 4 }, (_, i) => (
              <tr key={`sk${i}`} className="border-b"><td colSpan={columns.length} className="px-4 py-3"><Skeleton className="h-6 w-full" /></td></tr>
            ))}
            {!loading && shown.length === 0 && (
              <tr><td colSpan={columns.length} className="px-4 py-6 text-center text-sm text-muted-foreground">{empty ?? t("empty")}</td></tr>
            )}
            {!loading && shown.map((r) => (
              <tr key={rowKey(r)} className={cn("border-b transition-colors hover:bg-muted/40", rowClassName?.(r))}>
                {columns.map((c, i) => (
                  <td key={c.key} className={cn("px-3 py-2.5 align-middle", c.align === "right" && "text-right",
                    i === 0 && "pl-4", i === columns.length - 1 && "pr-4", c.className)}>{c.cell(r)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {view.length > SIZES[0] && (
        <div className="flex flex-wrap items-center justify-end gap-2 text-xs text-muted-foreground">
          <label className="flex items-center gap-1.5">{t("dtPerPage")}
            <select value={size} onChange={(e) => { setSize(Number(e.target.value)); setPage(0); }}
              className="h-8 rounded-md border bg-background px-2 text-xs text-foreground">
              {SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <Button size="icon" variant="outline" className="size-8" disabled={cur === 0} onClick={() => setPage(cur - 1)} aria-label="prev">
            <ChevronLeft className="size-4" />
          </Button>
          <span className="tabular-nums">{t("dtPage", { p: cur + 1, pages })}</span>
          <Button size="icon" variant="outline" className="size-8" disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)} aria-label="next">
            <ChevronRight className="size-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
