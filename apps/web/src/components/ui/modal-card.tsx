"use client";

import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";

type ModalCardProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: React.ReactNode;
  maxWidthClass?: string;
};

/** Всплывающее окно в стиле datasets / search (центр экрана, крестик). */
export function ModalCard({
  open,
  onClose,
  title,
  description,
  children,
  maxWidthClass = "max-w-md",
}: ModalCardProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-card-title"
    >
      <Card className={`w-full ${maxWidthClass} shadow-xl`}>
        <div className="mb-2 flex items-start justify-between gap-2">
          <CardTitle>
            <span id="modal-card-title">{title}</span>
          </CardTitle>
          <Button variant="ghost" onClick={onClose} aria-label="Закрыть">
            <X className="size-4" />
          </Button>
        </div>
        {description ? <CardDescription>{description}</CardDescription> : null}
        {children ? <div className={description ? "mt-4" : ""}>{children}</div> : null}
      </Card>
    </div>
  );
}

type LoadingOverlayProps = {
  open: boolean;
  message: string;
};

/** Полноэкранный индикатор ожидания (как на странице поиска). */
export function LoadingOverlay({ open, message }: LoadingOverlayProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-white/85 backdrop-blur-sm"
      aria-busy="true"
      aria-live="polite"
    >
      <div className="relative flex size-16 items-center justify-center">
        <span className="absolute size-14 animate-spin rounded-full border-4 border-violet-200 border-t-violet-600" />
        <span className="relative size-3 rounded-full bg-violet-600" aria-hidden />
      </div>
      <p className="max-w-sm px-6 text-center text-sm font-medium text-zinc-800">{message}</p>
    </div>
  );
}
