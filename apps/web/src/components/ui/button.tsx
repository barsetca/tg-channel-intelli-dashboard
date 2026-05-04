import type { ButtonHTMLAttributes } from "react";

const variants = {
  primary:
    "bg-violet-600 text-white hover:bg-violet-500 shadow-md shadow-violet-600/20 disabled:opacity-50",
  secondary:
    "border border-zinc-300 bg-white text-zinc-800 hover:border-zinc-400 hover:bg-zinc-50",
  ghost: "text-zinc-600 hover:bg-zinc-100",
} as const;

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof variants;
};

export function Button({ variant = "primary", className = "", ...props }: Props) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition ${variants[variant]} ${className}`}
      {...props}
    />
  );
}
