import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-lg py-20 text-center">
      <p className="text-sm font-medium text-violet-600">404</p>
      <h1 className="mt-2 text-xl font-semibold text-zinc-900">Page or channel not found</h1>
      <p className="mt-2 text-sm text-zinc-600">Check the id or return to search.</p>
      <Link href="/search" className="mt-6 inline-block text-sm font-medium text-violet-700 hover:text-violet-600">
        Go to search →
      </Link>
    </div>
  );
}
