"use client";

import { useQuery } from "@tanstack/react-query";
import { MessageCircleQuestion, Workflow } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useDeferredValue, useEffect, useState } from "react";

import { MemberAvatar } from "@/components/common/member-avatar";
import { Highlight } from "@/components/common/highlight";
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator, CommandShortcut,
} from "@/components/ui/command";
import { useModel } from "@/hooks/use-org";
import { orgApi } from "@/lib/api/endpoints";
import { ALL_NAV } from "@/lib/nav";

/** Ctrl+K: sahifalarga o'tish va ko'p tilli qidiruv (xodim, jarayon, vazifa, "Savol kimga?"). */
export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const t = useTranslations();
  const router = useRouter();
  const model = useModel();
  const [query, setQuery] = useState("");
  const deferred = useDeferredValue(query.trim());

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  const search = useQuery({
    queryKey: ["search", deferred],
    queryFn: () => orgApi.search(deferred, 6),
    enabled: open && deferred.length >= 2,
    staleTime: 60_000,
  });

  const go = (href: string) => {
    onOpenChange(false);
    setQuery("");
    router.push(href);
  };
  const r = search.data;

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title={t("top.search")} description={t("top.searchPlaceholder")}>
      <CommandInput value={query} onValueChange={setQuery} placeholder={t("top.searchPlaceholder")} />
      <CommandList className="max-h-[60vh]">
        <CommandEmpty>{search.isFetching ? t("common.loading") : t("common.nothingFound")}</CommandEmpty>
        {r && r.people.length > 0 && (
          <CommandGroup heading={t("top.whoAnswers")}>
            {r.people.slice(0, 3).map((p) => {
              const m = model.member.get(p.member);
              if (!m) return null;
              return (
                <CommandItem key={`p${p.member}`} value={`person-${m.id}-${deferred}`} onSelect={() => go(`/employees/${m.id}`)}>
                  <MemberAvatar member={m} size={22} />
                  <span className="truncate">{m.name}</span>
                  <span className="truncate text-muted-foreground">· {m.role}</span>
                  <CommandShortcut>{p.confidence}%</CommandShortcut>
                </CommandItem>
              );
            })}
          </CommandGroup>
        )}
        {r && r.processes.length > 0 && (
          <CommandGroup heading={t("nav.processes")}>
            {r.processes.slice(0, 4).map((h) => {
              const p = model.process.get(h.id);
              if (!p) return null;
              return (
                <CommandItem key={`pr${p.id}`} value={`process-${p.id}-${deferred}`} onSelect={() => go(`/organization?focus=p:${p.id}`)}>
                  <Workflow className="size-4" />
                  <Highlight text={p.name} spans={h.hl} />
                  <CommandShortcut>{model.systemName(p)}</CommandShortcut>
                </CommandItem>
              );
            })}
          </CommandGroup>
        )}
        {r && r.tasks.length > 0 && (
          <CommandGroup heading={t("nav.responsibilities")}>
            {r.tasks.slice(0, 6).map((h) => {
              const task = model.task.get(h.id);
              if (!task) return null;
              const owner = task.owner ? model.member.get(task.owner) : undefined;
              return (
                <CommandItem key={`t${task.id}`} value={`task-${task.id}-${deferred}`} onSelect={() => go(task.process ? `/organization?focus=p:${task.process}` : "/responsibilities")}>
                  <span className="min-w-0 flex-1 truncate"><Highlight text={task.title} spans={h.hl} /></span>
                  <CommandShortcut>{owner?.name ?? t("common.unassigned")}</CommandShortcut>
                </CommandItem>
              );
            })}
          </CommandGroup>
        )}
        {deferred.length >= 2 && (
          <CommandGroup heading={t("nav.ask")}>
            <CommandItem value={`ask-${deferred}`} onSelect={() => go(`/ask?q=${encodeURIComponent(deferred)}`)}>
              <MessageCircleQuestion className="size-4" />
              {t("top.askAbout", { q: deferred })}
            </CommandItem>
          </CommandGroup>
        )}
        <CommandSeparator />
        <CommandGroup heading={t("top.pages")}>
          {ALL_NAV.map((item) => (
            <CommandItem key={item.href} value={`nav-${item.key} ${t(`nav.${item.key}`)}`} onSelect={() => go(item.href)}>
              <item.icon className="size-4" />
              {t(`nav.${item.key}`)}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
