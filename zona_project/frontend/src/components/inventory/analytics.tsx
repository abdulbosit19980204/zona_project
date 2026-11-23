"use client";
/* eslint-disable react/no-unescaped-entities -- o'zbekcha matnlardagi apostrof (o'z, ma'lumot) */

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowDownUp, Building2, Download, RefreshCw, Trophy, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { toast } from "sonner";

import { axisProps, tooltipStyle } from "@/components/charts/chart-kit";
import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { download, inv, type BranchStat } from "./api";
import { Btn, COND_COLOR, Card, Empty, FlagBadge, Kpi, Progress, SectionTitle, Spinner, StatusBadge, ago } from "./ui";

/* Kunlik faollik: tasdiqlangan kategorik palitraning 1–3 o'rinlari (ko'k, to'q sariq, yashil-moviy) */
const S1 = "#2a78d6";
const S2 = "#eb6834";
const S3 = "#1baf7a";

type SortKey = "name" | "qty" | "today" | "week" | "coverage" | "photo_pct" | "last_at" | "problems";

export function AnalyticsView({ onOpenBranch }: { onOpenBranch: (branchId: number, extra?: Record<string, boolean | string>) => void }) {
  const [days, setDays] = useState(30);
  const [sort, setSort] = useState<SortKey>("week");
  const [asc, setAsc] = useState(false);
  const stats = useQuery({ queryKey: ["inv", "stats", days], queryFn: () => inv.stats({ days }), refetchInterval: 60_000 });
  const s = stats.data;

  const branches = useMemo(() => {
    if (!s) return [];
    const val = (b: BranchStat): number | string => {
      if (sort === "name") return b.name;
      if (sort === "last_at") return b.last_at ? new Date(b.last_at).getTime() : 0;
      if (sort === "problems") return b.no_serial + b.no_employee + b.broken;
      return (b[sort] as number | null) ?? -1;
    };
    return [...s.branches].sort((a, b) => {
      const x = val(a), y = val(b);
      const r = typeof x === "string" ? x.localeCompare(String(y)) : (x as number) - (y as number);
      return asc ? r : -r;
    });
  }, [s, sort, asc]);

  if (stats.isLoading) return <Spinner />;
  if (!s) return <Empty icon={<AlertTriangle className="size-6" />} title="Statistika yuklanmadi" hint={errorMessage(stats.error)} />;
  const t = s.totals;
  const donePct = t.branches ? Math.round((100 * t.done) / t.branches) : 0;
  const photoPct = t.rows ? Math.round((100 * t.with_photo) / t.rows) : 0;
  const lagging = s.branches.filter((b) => b.flag === "slow" || b.flag === "idle" || b.flag === "slowing");
  const daily = s.daily.map((d) => ({ ...d, label: d.date.slice(5).split("-").reverse().join(".") }));
  const branchBars = [...s.branches].sort((a, b) => b.qty - a.qty).map((b) => ({ name: b.name, qty: b.qty, id: b.id }));
  const conds = s.by_condition.filter((c) => c.qty > 0);
  const th = (key: SortKey, label: string, cls = "") => (
    <th className={cn("cursor-pointer select-none whitespace-nowrap px-2 py-2 font-semibold hover:text-foreground", cls)}
      onClick={() => (sort === key ? setAsc(!asc) : (setSort(key), setAsc(key === "name")))}>
      {label}{sort === key && <ArrowDownUp className="ml-1 inline size-3" />}
    </th>
  );

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 p-3 pb-28 sm:p-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="mr-auto">
          <h2 className="text-lg font-bold">Inventarizatsiya natijalari</h2>
          <p className="text-xs text-muted-foreground">Yangilandi: {ago(s.generated_at)} · har daqiqada o'zi yangilanadi</p>
        </div>
        <div className="flex rounded-xl border bg-card p-0.5">
          {[7, 30, 90].map((d) => (
            <button key={d} onClick={() => setDays(d)} className={cn("h-8 rounded-lg px-3 text-xs font-semibold", days === d ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>{d} kun</button>
          ))}
        </div>
        <Btn variant="outline" size="sm" onClick={() => stats.refetch()}><RefreshCw className={cn("size-4", stats.isFetching && "animate-spin")} /></Btn>
        <Btn size="sm" onClick={() => download("stats/export/").catch((e) => toast.error(errorMessage(e)))}><Download className="size-4" />Hisobot (Excel)</Btn>
      </div>

      {/* umumiy jarayon */}
      <Card>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <div className="text-sm font-semibold">Filiallar: <span className="text-emerald-600">{t.done} yakunlandi</span> · <span className="text-blue-600">{t.active} jarayonda</span> · <span className="text-muted-foreground">{t.planned} rejada</span></div>
          <div className="text-2xl font-bold tabular-nums">{donePct}%</div>
        </div>
        <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-l-full bg-emerald-500" style={{ width: `${(100 * t.done) / Math.max(1, t.branches)}%` }} />
          <div className="h-full bg-blue-500" style={{ width: `${(100 * t.active) / Math.max(1, t.branches)}%` }} />
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Qurilmalar (dona)" value={t.qty} hint={`${t.rows} qator`} />
        <Kpi label="Bugun kiritildi" value={t.today} tone="green" hint={`7 kunda: ${t.week}`} />
        <Kpi label="Sust filiallar" value={t.slow} tone={t.slow ? "red" : "slate"} hint="48 soatdan beri faolsiz" />
        <Kpi label="Ishlamaydi / ta'mir" value={t.broken} tone="amber" hint={`topilmadi: ${t.missing}`} />
        <Kpi label="Rasmli qatorlar" value={`${photoPct}%`} tone="violet" hint={`${t.with_photo} / ${t.rows}`} />
        <Kpi label="Filial loginlari" value={`${t.collectors_logged_in}/${t.collectors}`} tone="slate" hint="kamida bir marta kirgan" />
      </div>

      {/* sust filiallar */}
      {!!lagging.length && (
        <Card className="border-red-500/25 bg-red-500/[0.03]">
          <SectionTitle icon={<AlertTriangle className="size-4 text-red-500" />}>E'tibor talab qiladi — sust filiallar ({lagging.length})</SectionTitle>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {lagging.map((b) => (
              <button key={b.id} onClick={() => onOpenBranch(b.id)} className="flex items-center gap-3 rounded-xl border bg-card p-3 text-left hover:border-primary/40">
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{b.name}</div>
                  <div className="text-xs text-muted-foreground">{b.rows} qator · oxirgi: {ago(b.last_at)}{!b.collectors && " · login yo'q"}</div>
                </div>
                <FlagBadge value={b.flag} />
              </button>
            ))}
          </div>
        </Card>
      )}

      {/* filiallar reytingi */}
      <Card className="p-0">
        <div className="p-4 pb-2"><SectionTitle icon={<Building2 className="size-4" />}>Filiallar bo'yicha (bosing — qurilmalari ochiladi)</SectionTitle></div>
        <div className="hidden overflow-x-auto md:block">
          <table className="w-full text-sm">
            <thead className="border-y bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>
                {th("name", "Filial", "pl-4")}
                <th className="px-2 py-2 font-semibold">Holat</th>
                {th("qty", "Qurilmalar", "text-right")}
                {th("today", "Bugun", "text-right")}
                {th("week", "7 kun", "text-right")}
                {th("coverage", "Xodim qamrovi")}
                {th("photo_pct", "Rasm")}
                {th("problems", "Muammolar")}
                {th("last_at", "Oxirgi faollik", "pr-4")}
              </tr>
            </thead>
            <tbody>
              {branches.map((b) => (
                <tr key={b.id} onClick={() => onOpenBranch(b.id)} className="cursor-pointer border-b last:border-0 hover:bg-muted/40">
                  <td className="py-2.5 pl-4 pr-2"><div className="font-semibold">{b.name}</div><div className="text-xs text-muted-foreground">{b.conductor || b.region}</div></td>
                  <td className="px-2"><div className="flex flex-col items-start gap-1"><StatusBadge value={b.status} label={b.status_label} /><FlagBadge value={b.flag} /></div></td>
                  <td className="px-2 text-right font-bold tabular-nums">{b.qty}<div className="text-[11px] font-normal text-muted-foreground">{b.rows} qator</div></td>
                  <td className="px-2 text-right tabular-nums">{b.today || "—"}</td>
                  <td className="px-2 text-right tabular-nums">{b.week || "—"}</td>
                  <td className="w-36 px-2">{b.coverage === null ? <span className="text-xs text-muted-foreground">xodim yo'q</span> : (
                    <div><Progress value={b.coverage} /><div className="mt-0.5 text-[11px] text-muted-foreground">{b.employees_with_devices}/{b.employees} · {b.coverage}%</div></div>)}</td>
                  <td className="w-24 px-2">{b.photo_pct === null ? "—" : <div><Progress value={b.photo_pct} tone="bg-violet-500" /><div className="mt-0.5 text-[11px] text-muted-foreground">{b.photo_pct}%</div></div>}</td>
                  <td className="px-2 text-xs">
                    {b.no_serial > 0 && <button className="mr-2 text-amber-600 hover:underline" onClick={(e) => { e.stopPropagation(); onOpenBranch(b.id, { no_serial: true }); }}>S/N yo'q: {b.no_serial}</button>}
                    {b.no_employee > 0 && <button className="mr-2 text-amber-600 hover:underline" onClick={(e) => { e.stopPropagation(); onOpenBranch(b.id, { no_employee: true }); }}>xodimsiz: {b.no_employee}</button>}
                    {b.broken > 0 && <span className="text-red-600">ishlamaydi: {b.broken}</span>}
                    {!b.no_serial && !b.no_employee && !b.broken && <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="pr-4 text-xs text-muted-foreground">{ago(b.last_at)}<div>{b.collectors} login</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="space-y-2 p-3 md:hidden">
          {branches.map((b) => (
            <button key={b.id} onClick={() => onOpenBranch(b.id)} className="w-full rounded-xl border p-3 text-left">
              <div className="flex items-center gap-2">
                <span className="flex-1 font-semibold">{b.name}</span><FlagBadge value={b.flag} />
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-center text-xs">
                <div><div className="text-lg font-bold tabular-nums">{b.qty}</div>dona</div>
                <div><div className="text-lg font-bold tabular-nums">{b.today}</div>bugun</div>
                <div><div className="text-lg font-bold tabular-nums">{b.week}</div>7 kun</div>
              </div>
              {b.coverage !== null && <div className="mt-2"><Progress value={b.coverage} /><div className="mt-0.5 text-[11px] text-muted-foreground">Xodim qamrovi {b.coverage}%</div></div>}
              <div className="mt-1 text-[11px] text-muted-foreground">Oxirgi faollik: {ago(b.last_at)} · {b.status_label}</div>
            </button>
          ))}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <SectionTitle icon={<TrendingUp className="size-4" />}>Kunlik faollik</SectionTitle>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={daily} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={18} />
                <YAxis {...axisProps} allowDecimals={false} />
                <Tooltip {...tooltipStyle} cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "3 3" }} />
                <Legend wrapperStyle={{ fontSize: 12, color: "var(--muted-foreground)" }} />
                <Line type="monotone" dataKey="create" name="Qo'shildi" stroke={S1} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                <Line type="monotone" dataKey="update" name="O'zgartirildi" stroke={S2} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                <Line type="monotone" dataKey="delete" name="O'chirildi" stroke={S3} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <SectionTitle>Qurilmalar holati (dona)</SectionTitle>
          {conds.length ? (
            <div className="flex flex-col items-center gap-4 sm:flex-row">
              <div className="h-52 w-52 shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={conds} dataKey="qty" nameKey="label" innerRadius="58%" outerRadius="95%" paddingAngle={1} stroke="var(--card)" strokeWidth={2}>
                      {conds.map((c) => <Cell key={c.value} fill={COND_COLOR[c.value]} />)}
                    </Pie>
                    <Tooltip {...tooltipStyle} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="w-full space-y-2">
                {s.by_condition.map((c) => (
                  <div key={c.value} className="flex items-center gap-2 text-sm">
                    <span className="size-3 shrink-0 rounded-sm" style={{ background: COND_COLOR[c.value] }} />
                    <span className="flex-1">{c.label}</span>
                    <b className="tabular-nums">{c.qty}</b>
                    <span className="w-10 text-right text-xs text-muted-foreground">{t.qty ? Math.round((100 * c.qty) / t.qty) : 0}%</span>
                  </div>
                ))}
              </div>
            </div>
          ) : <Empty title="Hali ma'lumot yo'q" />}
        </Card>

        <Card>
          <SectionTitle>Filiallar bo'yicha qurilmalar (dona)</SectionTitle>
          <div style={{ height: Math.max(180, branchBars.length * 30) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={branchBars} layout="vertical" margin={{ top: 0, right: 28, left: 8, bottom: 0 }} barCategoryGap={4}>
                <XAxis type="number" hide allowDecimals={false} />
                <YAxis type="category" dataKey="name" {...axisProps} width={84} />
                <Tooltip {...tooltipStyle} formatter={(v) => [`${v} dona`, "Qurilmalar"]} />
                <Bar dataKey="qty" fill={S1} radius={[0, 4, 4, 0]} label={{ position: "right", fontSize: 11, fill: "var(--muted-foreground)" }}
                  onClick={(d) => { const id = (d as unknown as { id?: number }).id; if (id) onOpenBranch(id); }} cursor="pointer" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <SectionTitle>Qurilma guruhlari (dona)</SectionTitle>
          {s.by_group.length ? (
            <div style={{ height: Math.max(180, s.by_group.length * 30) }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={s.by_group} layout="vertical" margin={{ top: 0, right: 28, left: 8, bottom: 0 }} barCategoryGap={4}>
                  <XAxis type="number" hide allowDecimals={false} />
                  <YAxis type="category" dataKey="name" {...axisProps} width={84} />
                  <Tooltip {...tooltipStyle} formatter={(v) => [`${v} dona`, "Qurilmalar"]} />
                  <Bar dataKey="qty" fill={S1} radius={[0, 4, 4, 0]} label={{ position: "right", fontSize: 11, fill: "var(--muted-foreground)" }} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : <Empty title="Hali ma'lumot yo'q" />}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <SectionTitle icon={<Trophy className="size-4 text-amber-500" />}>Kim qancha ish qildi</SectionTitle>
          {s.leaderboard.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr><th className="py-1.5">#</th><th>Foydalanuvchi</th><th className="text-right">Qo'shdi</th><th className="text-right">7 kunda</th><th className="text-right">O'zgartirdi</th><th className="text-right">O'chirdi</th><th className="pl-3">Oxirgi</th></tr>
                </thead>
                <tbody>
                  {s.leaderboard.map((u, i) => (
                    <tr key={u.user_id} className="border-t">
                      <td className="py-2 text-muted-foreground">{i + 1}</td>
                      <td><div className="font-medium">{u.name}</div><div className="text-[11px] text-muted-foreground">{u.branches.join(", ") || u.username}</div></td>
                      <td className="text-right font-bold tabular-nums">{u.create}</td>
                      <td className="text-right tabular-nums">{u.week}</td>
                      <td className="text-right tabular-nums">{u.update}</td>
                      <td className="text-right tabular-nums">{u.delete}</td>
                      <td className="whitespace-nowrap pl-3 text-xs text-muted-foreground">{ago(u.last_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <Empty title="Hali hech kim kiritmagan" />}
        </Card>
        <Card>
          <SectionTitle>Eng ko'p qurilma turlari</SectionTitle>
          <div className="space-y-2">
            {s.by_type.slice(0, 12).map((r) => (
              <div key={r.name}>
                <div className="flex justify-between gap-2 text-sm"><span className="truncate">{r.name}</span><b className="tabular-nums">{r.qty}</b></div>
                <Progress value={(100 * r.qty) / Math.max(1, s.by_type[0]?.qty ?? 1)} className="mt-1 h-1.5" />
              </div>
            ))}
            {!s.by_type.length && <Empty title="Hali ma'lumot yo'q" />}
          </div>
          {!!s.by_org.length && (
            <>
              <div className="mb-2 mt-5 text-xs font-bold uppercase tracking-wider text-muted-foreground">Tashkilotlar</div>
              {s.by_org.map((o) => (
                <div key={o.name} className="flex justify-between py-0.5 text-sm"><span className="truncate">{o.name}</span><b className="tabular-nums">{o.qty}</b></div>
              ))}
            </>
          )}
        </Card>
      </div>

      <Card>
        <SectionTitle>Ma'lumot sifati</SectionTitle>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Kpi label="Seriya raqamsiz" value={t.no_serial} tone="amber" />
          <Kpi label="Xodim biriktirilmagan" value={t.no_employee} tone="amber" />
          <Kpi label="Qurilmasi bor xodimlar" value={`${t.employees_with_devices}/${t.employees_total}`} tone="green" />
          <Kpi label="O'chirilgan qatorlar" value={t.deleted} tone="slate" />
        </div>
      </Card>
    </div>
  );
}
