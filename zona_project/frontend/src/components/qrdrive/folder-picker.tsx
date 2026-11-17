"use client";

import { ChevronRight, CornerLeftUp, Folder, FolderPlus, Loader2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useQr } from "@/hooks/use-qrdrive";
import { cn } from "@/lib/utils";

import { QrGuard } from "./common";
import { useQt } from "./i18n";

interface Entry { name: string; path: string; is_dir: boolean }

/** Saqlash joyidagi papkalarni ko'rib, birini tanlash (ko'chirish, yuklash uchun). */
export function FolderPicker({ storageId, root, current, value, onChange }: {
  storageId: number; root: string; current?: string; value: string; onChange: (path: string) => void;
}) {
  const t = useQt();
  const [path, setPath] = useState(root || value || "/");  // asosiy papkadan — barcha xodim papkalari ko'rinadi
  const [newName, setNewName] = useState("");
  const q = useQr<{ entries: Entry[] }>(["browse", storageId, path], "files/browse", { storage_id: storageId, path });
  const dirs = (q.data?.entries ?? []).filter((e) => e.is_dir);
  const crumbs = path.split("/").filter(Boolean);
  const canUp = crumbs.length > 0;
  const go = (p: string) => { setPath(p); onChange(p); setNewName(""); };
  const up = () => go("/" + crumbs.slice(0, -1).join("/"));

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-1 rounded-lg border bg-muted/40 px-2 py-1.5 text-xs">
        <button type="button" className="text-muted-foreground hover:text-foreground" onClick={() => go("/")}>/</button>
        {crumbs.map((c, i) => (
          <span key={i} className="flex items-center gap-1">
            <button type="button" className="hover:text-primary" onClick={() => go("/" + crumbs.slice(0, i + 1).join("/"))}>{c}</button>
            {i < crumbs.length - 1 && <ChevronRight className="size-3 text-muted-foreground" />}
          </span>
        ))}
      </div>
      <div className="max-h-56 overflow-y-auto rounded-lg border p-1">
        {canUp && (
          <button type="button" onClick={up} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-muted">
            <CornerLeftUp className="size-4" />{t("up")}
          </button>
        )}
        <QrGuard query={q} skeleton={<div className="flex items-center gap-2 p-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />{t("loading")}</div>}>
          {!dirs.length && <p className="px-2 py-1.5 text-sm text-muted-foreground">{t("noSubfolders")}</p>}
          {dirs.map((d) => (
            <button key={d.path} type="button" onClick={() => go(d.path)}
              className={cn("flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted", value === d.path && "bg-primary/10")}>
              <Folder className="size-4 shrink-0 text-primary" /><span className="truncate">{d.name}</span>
              {current === d.path && <span className="rounded-full bg-muted px-1.5 text-[10px] text-muted-foreground">{t("currentFolder")}</span>}
              <ChevronRight className="ml-auto size-3.5 text-muted-foreground" />
            </button>
          ))}
        </QrGuard>
      </div>
      <div className="flex gap-2">
        <Input value={newName} onChange={(e) => setNewName(e.target.value.replace(/[\\/]/g, ""))} placeholder={t("newSubfolder")} className="h-8" />
        <Button type="button" size="sm" variant="outline" disabled={!newName.trim()}
          onClick={() => { const p = `${path.replace(/\/+$/, "")}/${newName.trim()}`; onChange(p); setPath(path); }}>
          <FolderPlus className="size-4" />{t("add")}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t("targetFolder")}: <code className="break-all text-foreground">{value || path}</code></p>
    </div>
  );
}
