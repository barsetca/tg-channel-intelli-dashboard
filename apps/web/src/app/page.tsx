import Link from "next/link";
import { BarChart3, HeartPulse, Layers, Search, Sparkles } from "lucide-react";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";

const tiles = [
  {
    href: "/search",
    title: "Channel search",
    desc: "Scenario 1 — saved catalog vs Telegram, manual review, export.",
    icon: Search,
  },
  {
    href: "/semantic-search",
    title: "Semantic search",
    desc: "Scenario 4 — ask the corpus, inspect hits.",
    icon: Layers,
  },
  {
    href: "/compare",
    title: "Compare",
    desc: "Scenario 5 — 2–5 channels, chart + table.",
    icon: BarChart3,
  },
  {
    href: "/health",
    title: "API health",
    desc: "Verify FastAPI connectivity and environment.",
    icon: HeartPulse,
  },
];

export default function Home() {
  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <div className="flex flex-wrap items-start gap-4">
        <div className="rounded-2xl border border-violet-200 bg-violet-50 p-3">
          <Sparkles className="size-10 text-violet-600" />
        </div>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">Telegram Channel Intelligence</h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-zinc-600">
            Operational dashboard for the scenarios in the product brief: discovery, deep analysis, summaries, semantic
            retrieval, pairwise comparison, similar channels, export, and validation gates.
          </p>
          <p className="mt-3 text-xs text-zinc-500">
            Point the app at your API with <code className="rounded bg-zinc-100 px-1 text-zinc-700">NEXT_PUBLIC_API_BASE_URL</code>{" "}
            (browser) and optionally <code className="rounded bg-zinc-100 px-1 text-zinc-700">API_URL</code> for server-side
            fetches.
          </p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {tiles.map(({ href, title, desc, icon: Icon }) => (
          <Link key={href} href={href} className="group block">
            <Card className="h-full transition group-hover:border-violet-300 group-hover:bg-violet-50/40">
              <div className="flex items-start gap-3">
                <Icon className="mt-0.5 size-5 shrink-0 text-violet-600" />
                <div>
                  <CardTitle className="text-base group-hover:text-violet-800">{title}</CardTitle>
                  <CardDescription className="mt-1">{desc}</CardDescription>
                </div>
              </div>
            </Card>
          </Link>
        ))}
      </div>

      <Card>
        <CardTitle>Open a channel by id</CardTitle>
        <CardDescription>
          After search returns rows, use <span className="font-mono text-zinc-600">/channels/&lt;id&gt;</span> for the
          profile, <span className="font-mono text-zinc-600">/analytics</span> for Scenario 2, and{" "}
          <span className="font-mono text-zinc-600">/recommendations</span> for Scenario 6.
        </CardDescription>
      </Card>
    </div>
  );
}
