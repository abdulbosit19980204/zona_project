"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/lib/api/client";
import { approvalsApi, orgApi } from "@/lib/api/endpoints";
import type { ChangeStatus, Member, Me } from "@/lib/api/types";
import { localizeState } from "@/lib/localize";
import { buildModel, type Model } from "@/lib/model";
import { useUI } from "@/stores/ui";

export const queryKeys = {
  state: ["state"] as const,
  events: (limit: number) => ["events", limit] as const,
  approvals: (status: ChangeStatus | "all", mine: boolean) => ["approvals", status, mine] as const,
};

/** Butun tuzilma (bitta so'rov) va undan hisoblangan model. */
export function useOrg() {
  const query = useQuery({ queryKey: queryKeys.state, queryFn: orgApi.state });
  const locale = useUI((s) => s.locale);
  // matnlar tanlangan tilda (AI tarjimalari); tarjima bo'lmasa asl matn
  const model = useMemo<Model | null>(() => (query.data ? buildModel(localizeState(query.data, locale)) : null), [query.data, locale]);
  return { ...query, model };
}

/** useOrg + model mavjudligini kafolatlaydi (AppShell yuklanish holatini o'zi ko'rsatadi). */
export function useModel(): Model {
  const { model } = useOrg();
  if (!model) throw new Error("useModel: holat hali yuklanmagan");
  return model;
}

export function useMe(): Me | null {
  const model = useModel();
  const me = model.state.me;
  return me.anonymous ? null : me;
}

export function useCan() {
  return useModel().state.me.can;
}

/** Tanlangan bo'lim doirasi (yuqori paneldagi kompaniya tanlagich). */
export function useScope() {
  const model = useModel();
  const scope = useUI((s) => s.scope);
  const active = scope && model.dept.has(scope) ? scope : null;
  return {
    scope: active,
    inScope: (m: Member) => !active || model.deptOf(m) === active,
    processInScope: (pid: number) =>
      !active || (model.linksOfProcess.get(pid) ?? []).some((l) => {
        const m = model.member.get(l.memberId);
        return m ? model.deptOf(m) === active : false;
      }),
  };
}

export function useEvents(limit = 100) {
  return useQuery({ queryKey: queryKeys.events(limit), queryFn: () => orgApi.events(limit) });
}

export function useApprovals(status: ChangeStatus | "all" = "all", mine = false) {
  return useQuery({
    queryKey: queryKeys.approvals(status, mine),
    queryFn: () => approvalsApi.list({ status: status === "all" ? undefined : status, mine }),
  });
}

/** O'zgartirish: muvaffaqiyatda xabar va tuzilma/tarixni qayta yuklash, xatoda xabar. */
export function useOrgMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>, success?: string | ((r: TResult) => string)) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (result) => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: queryKeys.state }),
        qc.invalidateQueries({ queryKey: ["events"] }),
        qc.invalidateQueries({ queryKey: ["approvals"] }),
      ]);
      if (success) toast.success(typeof success === "function" ? success(result) : success);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
}
