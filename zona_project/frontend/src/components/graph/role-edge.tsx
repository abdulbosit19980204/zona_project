"use client";

import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from "@xyflow/react";
import { memo } from "react";

import { ROLE_DASH } from "@/lib/model";

import type { OrgEdge } from "./org-layout";

/**
 * Bog'lanish: rol chiziq uslubi bilan (egasi — qalin, tasdiqlovchi — shtrix, ...).
 * Tanlanganda ko'k rangga o'tadi, ustida zangori oqim yuradi va rol yorlig'i chiqadi.
 */
export const RoleEdge = memo(function RoleEdge(props: EdgeProps<OrgEdge>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data } = props;
  const [path, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, curvature: 0.4 });
  const role = data?.role ?? "struct";
  const struct = role === "struct";
  const stroke = data?.highlight ? "var(--primary)" : struct ? "var(--edge-struct)" : role === "owner" ? "var(--edge-strong)" : "var(--edge-soft)";
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke,
          strokeWidth: role === "owner" ? 1.9 : role === "contributor" ? 1.6 : 1.2,
          strokeDasharray: struct ? undefined : ROLE_DASH[role],
          strokeLinecap: role === "contributor" ? "round" : undefined,
          opacity: data?.dim ? 0.08 : 1,
          transition: "opacity .18s, stroke .18s",
        }}
      />
      {data?.highlight && (
        <>
          <path d={path} fill="none" stroke="var(--cyan)" strokeWidth={1.6} className="edge-flow" style={{ opacity: 0.9 }} />
          {data.label && (
            <EdgeLabelRenderer>
              <div
                className="pointer-events-none absolute rounded-md border border-primary/40 bg-background px-1.5 py-px text-[10.5px] text-primary"
                style={{ transform: `translate(-50%, -50%) translate(${labelX * 0.25 + targetX * 0.75}px, ${labelY * 0.25 + targetY * 0.75}px)` }}
              >
                {data.label}
              </div>
            </EdgeLabelRenderer>
          )}
        </>
      )}
    </>
  );
});

export const edgeTypes = { role: RoleEdge };
