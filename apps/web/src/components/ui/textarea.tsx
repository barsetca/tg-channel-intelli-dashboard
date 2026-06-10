import { forwardRef, type TextareaHTMLAttributes } from "react";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className = "", ...props }, ref) {
    return (
      <textarea
        ref={ref}
        className={`min-h-[100px] w-full resize-y rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 outline-none ring-violet-500/25 placeholder:text-zinc-400 focus:border-violet-500 focus:ring-2 ${className}`}
        {...props}
      />
    );
  },
);
