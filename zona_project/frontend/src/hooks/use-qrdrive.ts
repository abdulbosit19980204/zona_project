"use client";

import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";

import { isQrDown, qrApi, qrError, type NotifResponse } from "@/lib/api/qrdrive";

/** QR Drive GET so'rovi (react-query). Servis ishlamasa, qayta-qayta urinmaydi. */
export function useQr<T>(key: QueryKey, path: string, params?: Record<string, unknown>, opts?: { refetchInterval?: number; enabled?: boolean }) {
  return useQuery({
    queryKey: ["qr", ...key, params ?? {}],
    queryFn: async () => (await qrApi.get<T>(path, { params })).data,
    retry: (count, error) => !isQrDown(error) && count < 1,
    refetchInterval: opts?.refetchInterval,
    enabled: opts?.enabled,
  });
}

/** O'zgartiruvchi amal: muvaffaqiyatda xabar va QR Drive keshlarini yangilash, xatoda tushunarli matn. */
export function useQrAction<V = void, R = unknown>(fn: (v: V) => Promise<R>, success?: string | ((r: R) => string | undefined)) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      const msg = typeof success === "function" ? success(r) : success;
      if (msg) toast.success(msg);
      qc.invalidateQueries({ queryKey: ["qr"] });
    },
    onError: (e) => toast.error(qrError(e)),
  });
}

/** Menyu nishonlari va qo'ng'iroqcha: kutilayotgan so'rovlar, xatolar, o'qilmagan bildirishnomalar. */
export function useQrNotifications() {
  return useQr<NotifResponse>(["notifications"], "notifications", undefined, { refetchInterval: 30_000 });
}
