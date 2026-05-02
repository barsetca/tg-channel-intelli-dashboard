import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-6">
      <p className="text-sm uppercase tracking-widest text-zinc-500">Telegram</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-100">
        Channel Intelligence Dashboard
      </h1>
      <p className="mt-4 text-zinc-400">
        Monorepo skeleton: FastAPI + Next.js. Connect the API and Telethon sync in{" "}
        <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-sm">backend/app</code>.
      </p>
      <div className="mt-8 flex gap-4">
        <Link
          className="rounded-lg bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900"
          href="/health"
        >
          Check setup
        </Link>
        <a
          className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300"
          href={process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}
          target="_blank"
          rel="noreferrer"
        >
          API root
        </a>
      </div>
    </main>
  );
}
