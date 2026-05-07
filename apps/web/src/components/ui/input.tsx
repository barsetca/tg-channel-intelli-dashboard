import type { InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement>;

export function Input({ className = "", ...props }: Props) {
  return (
    <input
      className={`w-full rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 outline-none ring-violet-500/25 placeholder:text-zinc-400 focus:border-violet-500 focus:ring-2 ${className}`}
      {...props}
    />
  );
}
