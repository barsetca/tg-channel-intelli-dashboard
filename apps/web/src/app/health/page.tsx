import { fetchHealth } from "@/lib/api-client";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function HealthPage() {
  let payload: Awaited<ReturnType<typeof fetchHealth>> | null = null;
  let error: string | null = null;
  try {
    payload = await fetchHealth();
  } catch (e) {
    error = e instanceof Error ? e.message : "Unknown error";
  }

  return (
    <main className="mx-auto max-w-xl px-6 py-16">
      <Link href="/" className="text-sm text-zinc-600 hover:text-zinc-900">
        ← Back
      </Link>
      <h1 className="mt-4 text-xl font-semibold text-zinc-900">API health</h1>
      {payload ? (
        <pre className="mt-6 overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-700">
          {JSON.stringify(payload, null, 2)}
        </pre>
      ) : (
        <p className="mt-6 text-sm text-red-600">
          {error ?? "No data"}
          <span className="mt-2 block text-zinc-600">
            Set{" "}
            <code className="rounded bg-zinc-100 px-1 text-zinc-800">NEXT_PUBLIC_API_BASE_URL</code> and run the
            API.
          </span>
        </p>
      )}
    </main>
  );
}
