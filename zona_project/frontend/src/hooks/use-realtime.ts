"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import type { RealtimeMessage } from "@/lib/api/types";
import { useAuth } from "@/stores/auth";

import { queryKeys } from "./use-org";

/** WebSocket manzili: NEXT_PUBLIC_WS_URL yoki shu xost, 8000-port (Django/Daphne). */
function socketUrl(token: string) {
  const base = process.env.NEXT_PUBLIC_WS_URL
    ?? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8000/ws/events/`;
  return `${base}?token=${encodeURIComponent(token)}`;
}

/**
 * Jonli yangilanishlar: boshqa foydalanuvchi o'zgartirsa, ma'lumot avtomatik qayta yuklanadi.
 * Uzilsa, ortib boruvchi kutish bilan qayta ulanadi. Holat: "live" | "connecting" | "offline".
 */
export function useRealtime(currentUser: string | undefined) {
  const qc = useQueryClient();
  const access = useAuth((s) => s.access);
  const [status, setStatus] = useState<"live" | "connecting" | "offline">("connecting");
  const userRef = useRef(currentUser);
  useEffect(() => {
    userRef.current = currentUser;
  }, [currentUser]);

  useEffect(() => {
    if (!access) return;
    let socket: WebSocket | null = null;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let ping: ReturnType<typeof setInterval> | undefined;
    let closed = false;

    const connect = () => {
      setStatus("connecting");
      socket = new WebSocket(socketUrl(useAuth.getState().access ?? access));
      socket.onopen = () => {
        retry = 0;
        setStatus("live");
        ping = setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send(JSON.stringify({ type: "ping" })), 25_000);
      };
      socket.onmessage = (msg) => {
        let data: RealtimeMessage;
        try {
          data = JSON.parse(String(msg.data)) as RealtimeMessage;
        } catch {
          return;
        }
        if (data.type === "event") {
          void qc.invalidateQueries({ queryKey: queryKeys.state });
          void qc.invalidateQueries({ queryKey: ["events"] });
          if (data.data.actor && data.data.actor !== userRef.current) {
            toast(data.data.subject || data.data.to_name || data.data.from_name, {
              description: `${data.data.actor}: ${data.data.text || data.data.kind}`,
            });
          }
        } else if (data.type === "state") {
          // AI tarjimani tugatdi: matnlar tanlangan tilda yangilanadi
          void qc.invalidateQueries({ queryKey: queryKeys.state });
        } else if (data.type === "approval") {
          void qc.invalidateQueries({ queryKey: ["approvals"] });
          void qc.invalidateQueries({ queryKey: queryKeys.state });
        }
      };
      socket.onclose = (event) => {
        clearInterval(ping);
        if (closed) return;
        setStatus("offline");
        if (event.code === 4401) return; // token yaroqsiz: keyingi so'rov refresh qiladi va effekt qayta ishga tushadi
        retry = Math.min(retry + 1, 6);
        timer = setTimeout(connect, 1000 * 2 ** retry);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      clearInterval(ping);
      socket?.close();
    };
  }, [access, qc]);

  return status;
}
