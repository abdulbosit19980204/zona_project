"use client";

import { Check, ChevronDown, Star, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { MemberAvatar } from "@/components/common/member-avatar";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useModel, useOrgMutation } from "@/hooks/use-org";
import { orgApi } from "@/lib/api/endpoints";
import type { Task } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** Vazifa ijrochilari tartib bilan: birinchisi asosiy mas'ul, qolganlari navbatdagilar. */
export function executorsOf(task: Task): number[] {
  return [...(task.owner ? [task.owner] : []), ...(task.fallbacks ?? []).map((f) => f.member)];
}

/**
 * Jadvaldagi ko'p tanlovli "Ijrochilar" katagi: bir vazifaga bir nechta xodim.
 * Tanlash tartibi = navbat: 1-chi asosiy mas'ul, u qila olmasa 2-chi va h.k.
 */
export function ExecutorsPicker({ task, disabled }: { task: Task; disabled?: boolean }) {
  const t = useTranslations();
  const model = useModel();
  const [open, setOpen] = useState(false);
  const ids = executorsOf(task);

  const save = useOrgMutation((next: number[]) => {
    const conditions = new Map((task.fallbacks ?? []).map((f) => [f.member, f.condition]));
    const [owner = null, ...rest] = next;
    return orgApi.tasks.update(task.id, {
      owner,
      fallbacks: rest.map((member) => ({ member, condition: conditions.get(member) ?? "" })),
    });
  }, t("common.saved"));

  const toggle = (id: number) => save.mutate(ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]);
  const makeMain = (id: number) => save.mutate([id, ...ids.filter((x) => x !== id)]);

  const chips = ids.length ? (
    <span className="flex min-w-0 flex-1 flex-wrap items-center gap-1">
      {ids.map((id, i) => {
        const m = model.member.get(id);
        return (
          <span
            key={id}
            className={cn(
              "inline-flex max-w-full items-center gap-1 rounded-full border py-0.5 pl-0.5 pr-2 text-xs",
              i === 0 ? "border-primary/40 bg-primary/10 font-medium" : "bg-muted/50",
            )}
          >
            <MemberAvatar member={m} size={18} />
            <span className="truncate">{m?.name ?? "?"}</span>
            {ids.length > 1 && <span className="font-mono text-[10px] text-muted-foreground">{i + 1}</span>}
          </span>
        );
      })}
    </span>
  ) : (
    <span className="flex-1 text-left text-sm text-muted-foreground">{t("common.unassigned")}</span>
  );

  if (disabled) return <div className="flex min-h-8 items-center">{chips}</div>;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="flex min-h-8 w-full items-center gap-2 rounded-md border bg-transparent px-2 py-1 text-left shadow-xs hover:border-primary/40"
          aria-label={t("forms.task.executors")}
        >
          {chips}
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="end">
        {ids.length > 0 && (
          <div className="border-b p-2">
            <div className="px-1 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{t("forms.task.executorsOrder")}</div>
            {ids.map((id, i) => {
              const m = model.member.get(id);
              return (
                <div key={id} className="flex items-center gap-2 rounded-md px-1 py-1 text-sm">
                  <span className={cn("grid size-5 place-items-center rounded-full font-mono text-[10px] font-bold", i === 0 ? "bg-primary text-primary-foreground" : "bg-muted")}>{i + 1}</span>
                  <span className="min-w-0 flex-1 truncate">{m?.name ?? "?"}</span>
                  {i === 0 ? (
                    <span className="text-[11px] text-primary">{t("forms.task.main")}</span>
                  ) : (
                    <Button type="button" variant="ghost" size="icon" className="size-6" disabled={save.isPending} onClick={() => makeMain(id)} title={t("forms.task.makeMain")}>
                      <Star className="size-3.5" />
                    </Button>
                  )}
                  <Button type="button" variant="ghost" size="icon" className="size-6 text-muted-foreground hover:text-destructive" disabled={save.isPending} onClick={() => toggle(id)} aria-label={t("common.delete")}>
                    <X className="size-3.5" />
                  </Button>
                </div>
              );
            })}
          </div>
        )}
        <Command>
          <CommandInput placeholder={t("forms.task.findMember")} />
          <CommandList className="max-h-64">
            <CommandEmpty>—</CommandEmpty>
            <CommandGroup>
              {model.memberOrder.map((m) => {
                const pos = ids.indexOf(m.id);
                return (
                  <CommandItem key={m.id} value={`${m.name} ${m.role}`} disabled={save.isPending} onSelect={() => toggle(m.id)}>
                    <MemberAvatar member={m} size={20} />
                    <span className="min-w-0 flex-1 truncate">{m.name}<span className="ml-1.5 text-xs text-muted-foreground">{m.role}</span></span>
                    {pos >= 0 && <Check className="size-4 text-primary" />}
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
