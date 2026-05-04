export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block size-4 animate-spin rounded-full border-2 border-zinc-300 border-t-violet-600 ${className}`}
      aria-hidden
    />
  );
}
