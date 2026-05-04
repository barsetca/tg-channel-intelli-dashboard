"use client";

import { useId } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Point = { t: string; v: number };

export function TrendArea({ data, title }: { data: Point[]; title?: string }) {
  const gradId = `fillVioletLight-${useId().replace(/:/g, "")}`;
  return (
    <div className="h-56 w-full">
      {title ? <p className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">{title}</p> : null}
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
          <XAxis dataKey="t" tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#ffffff",
              border: "1px solid #e4e4e7",
              borderRadius: "12px",
              fontSize: "12px",
            }}
          />
          <Area type="monotone" dataKey="v" stroke="#7c3aed" fill={`url(#${gradId})`} strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
