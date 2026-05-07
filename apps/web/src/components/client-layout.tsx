"use client";

import { AppShell } from "@/components/app-shell";

export function ClientLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
