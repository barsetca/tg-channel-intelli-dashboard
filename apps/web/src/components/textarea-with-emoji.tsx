"use client";

import dynamic from "next/dynamic";
import { Smile } from "lucide-react";
import { useRef, useState, type TextareaHTMLAttributes } from "react";
import type { EmojiClickData } from "emoji-picker-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const EmojiPicker = dynamic(() => import("emoji-picker-react"), { ssr: false });

type TextareaWithEmojiProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "onChange"> & {
  value: string;
  onChange: (value: string) => void;
};

export function TextareaWithEmoji({ value, onChange, className = "", ...props }: TextareaWithEmojiProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [open, setOpen] = useState(false);

  const insertEmoji = (data: EmojiClickData) => {
    const ta = ref.current;
    const emoji = data.emoji;
    if (!ta) {
      onChange(value + emoji);
      setOpen(false);
      return;
    }
    const start = ta.selectionStart ?? value.length;
    const end = ta.selectionEnd ?? value.length;
    const next = value.slice(0, start) + emoji + value.slice(end);
    onChange(next);
    setOpen(false);
    requestAnimationFrame(() => {
      ta.focus();
      const pos = start + emoji.length;
      ta.setSelectionRange(pos, pos);
    });
  };

  return (
    <div className="relative">
      <Textarea
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={className}
        {...props}
      />
      <div className="mt-1 flex justify-end">
        <Button type="button" variant="ghost" className="text-sm" onClick={() => setOpen((o) => !o)}>
          <Smile className="mr-1.5 h-4 w-4" aria-hidden />
          Эмодзи
        </Button>
      </div>
      {open ? (
        <div className="absolute right-0 z-30 mt-1 shadow-lg">
          <EmojiPicker onEmojiClick={insertEmoji} lazyLoadEmojis searchPlaceHolder="Поиск…" />
        </div>
      ) : null}
    </div>
  );
}
