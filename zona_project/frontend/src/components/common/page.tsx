import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Sahifa konteyneri: aylantiriladigan, bir xil chekinishlar. */
export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("h-full overflow-y-auto px-6 py-6 lg:px-8", className)}>{children}</div>;
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end gap-3">
      <div className="min-w-0 flex-1">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function SectionTitle({ children, actions }: { children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-3 mt-8 flex items-center gap-3">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{children}</h2>
      {actions && <div className="ml-auto">{actions}</div>}
    </div>
  );
}

export function StatCard({ label, value, hint, icon: Icon, progress, tone = "default" }: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: LucideIcon;
  progress?: number;
  tone?: "default" | "warning" | "danger" | "success";
}) {
  return (
    <Card className="relative gap-0 overflow-hidden px-5 py-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {Icon && <Icon className="size-3.5" />}
        {label}
      </div>
      <div
        className={cn(
          "mt-2 font-mono text-2xl font-semibold tracking-tight",
          tone === "warning" && "text-warning",
          tone === "danger" && "text-destructive",
          tone === "success" && "text-success",
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>}
      {progress !== undefined && (
        <div className="mt-3 h-1 overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-full bg-gradient-to-r from-primary to-violet" style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
      )}
    </Card>
  );
}

export function EmptyState({ icon: Icon, title, hint, action }: { icon?: LucideIcon; title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-6 py-12 text-center">
      {Icon && <Icon className="size-8 text-muted-foreground" />}
      <div className="font-medium">{title}</div>
      {hint && <p className="max-w-md text-sm text-muted-foreground">{hint}</p>}
      {action}
    </div>
  );
}
