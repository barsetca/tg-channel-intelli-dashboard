"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Home,
  Layers,
  Search,
  Sparkles,
} from "lucide-react";

const nav = [
  { href: "/", label: "Home", icon: Home },
  { href: "/search", label: "Search", icon: Search },
  { href: "/semantic-search", label: "Semantic", icon: Layers },
  { href: "/compare", label: "Compare", icon: BarChart3 },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(139,92,246,0.12),transparent)]" />
      <div className="relative flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-56 shrink-0 border-r border-zinc-200 bg-white/95 px-3 py-6 shadow-sm backdrop-blur md:flex md:flex-col">
          <Link href="/" className="flex items-center gap-2 px-2">
            <Sparkles className="size-6 text-violet-600" />
            <span className="font-semibold tracking-tight text-zinc-900">TG Intel</span>
          </Link>
          <nav className="mt-8 flex flex-col gap-1">
            {nav.map(({ href, label, icon: Icon }) => {
              const active = pathname === href || (href !== "/" && pathname.startsWith(href));
              return (
                <Link
                  key={href}
                  href={href}
                  className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition ${
                    active
                      ? "bg-violet-100 text-violet-900"
                      : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900"
                  }`}
                >
                  <Icon className="size-4 shrink-0" />
                  {label}
                </Link>
              );
            })}
          </nav>
          <div className="mt-auto border-t border-zinc-200 pt-4 text-xs text-zinc-500">
            Set <code className="rounded bg-zinc-100 px-1 text-zinc-700">NEXT_PUBLIC_API_BASE_URL</code> for API.
          </div>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-10 border-b border-zinc-200 bg-white/90 px-4 py-3 shadow-sm backdrop-blur md:hidden">
            <div className="flex items-center justify-between gap-2">
              <Link href="/" className="font-semibold text-zinc-900">
                TG Intel
              </Link>
              <div className="flex gap-2 text-xs">
                <Link href="/search" className="font-medium text-violet-700">
                  Search
                </Link>
                <Link href="/semantic-search" className="text-zinc-600">
                  Semantic
                </Link>
              </div>
            </div>
          </header>
          <main className="flex-1 px-4 py-8 md:px-10 lg:px-14">{children}</main>
        </div>
      </div>
    </div>
  );
}
