import type { Member } from "@/lib/api/types";
import { initials } from "@/lib/model";
import { cn } from "@/lib/utils";

/** Bosh harfli avatar: bir rangli, jamoa uchun yumaloq kvadrat. */
export function MemberAvatar({ member, name, size = 32, className }: { member?: Member | null; name?: string; size?: number; className?: string }) {
  const label = member?.name ?? name;
  return (
    <span
      title={label}
      style={{ width: size, height: size, fontSize: size * 0.36 }}
      className={cn(
        "inline-grid shrink-0 place-items-center border border-border bg-gradient-to-br from-elevated to-card font-semibold tracking-wide text-foreground",
        member?.is_team ? "rounded-[30%]" : "rounded-full",
        !label && "border-dashed bg-none text-muted-foreground",
        className,
      )}
    >
      {label ? initials(label) : "?"}
    </span>
  );
}
