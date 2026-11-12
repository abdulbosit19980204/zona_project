"use client";

import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Recharts uchun umumiy uslub: tokenlardan ranglar, mavzuga mos tooltip. */
export const CHART = {
  primary: "var(--chart-1)",
  violet: "var(--chart-2)",
  cyan: "var(--chart-3)",
  success: "var(--chart-4)",
  warning: "var(--chart-5)",
  muted: "var(--edge-soft)",
  grid: "var(--border)",
  text: "var(--muted-foreground)",
};
export const SERIES = [CHART.primary, CHART.violet, CHART.cyan, CHART.success, CHART.warning, CHART.muted];

export const tooltipStyle = {
  contentStyle: {
    background: "var(--popover)",
    border: "1px solid var(--border)",
    borderRadius: 10,
    fontSize: 12,
    color: "var(--popover-foreground)",
  },
  itemStyle: { color: "var(--popover-foreground)" },
  labelStyle: { color: "var(--muted-foreground)" },
  cursor: { fill: "color-mix(in srgb, var(--primary) 8%, transparent)" },
};

export const axisProps = {
  stroke: CHART.text,
  fontSize: 11,
  tickLine: false,
  axisLine: false,
} as const;

export function ChartCard({ title, description, children, className, actions }: {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
}) {
  return (
    <Card className={cn("gap-3 p-5", className)}>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold">{title}</h3>
          {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </Card>
  );
}
