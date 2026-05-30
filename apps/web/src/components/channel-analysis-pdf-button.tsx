"use client";

import { useState } from "react";
import { FileText } from "lucide-react";
import { channelAnalysisPdfUrl } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

type Props = {
  analysisId: number;
  className?: string;
  /** Не всплывать клик (для строк списка с общим onClick). */
  stopPropagation?: boolean;
};

function openWaitingTab(): Window | null {
  const popup = window.open("about:blank", "_blank");
  if (!popup) return null;
  try {
    popup.document.open();
    popup.document.write(`<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Формирование PDF…</title>
  <style>
    body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
      font-family: system-ui, sans-serif; background: #fafafa; color: #3f3f46; }
    p { font-size: 15px; }
  </style>
</head>
<body><p>Формирование PDF-отчёта…</p></body>
</html>`);
    popup.document.close();
  } catch {
    /* ignore */
  }
  return popup;
}

export function ChannelAnalysisPdfButton({ analysisId, className, stopPropagation }: Props) {
  const [loading, setLoading] = useState(false);

  if (analysisId <= 0) return null;

  async function openPdf(e?: React.MouseEvent) {
    if (stopPropagation) {
      e?.preventDefault();
      e?.stopPropagation();
    }
    if (loading) return;

    const popup = openWaitingTab();
    if (!popup) {
      window.alert("Браузер заблокировал новую вкладку. Разрешите всплывающие окна для этого сайта и повторите.");
      return;
    }

    setLoading(true);
    try {
      // Прямой URL — браузер берёт имя из Content-Disposition (username_номер.pdf).
      // blob: URL даёт случайный UUID вроде 5d6de1da-….pdf.
      popup.location.replace(channelAnalysisPdfUrl(analysisId));
    } catch (err) {
      try {
        popup.close();
      } catch {
        /* already closed */
      }
      const msg = err instanceof Error ? err.message : "Не удалось открыть PDF";
      window.alert(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      className={className ?? "shrink-0 p-2"}
      aria-label={loading ? "Формирование PDF…" : "Открыть PDF отчёт"}
      title={loading ? "Формирование PDF…" : "Открыть PDF в браузере"}
      disabled={loading}
      onClick={openPdf}
    >
      {loading ? <Spinner className="size-4 text-violet-600" /> : <FileText className="size-4 text-violet-600" />}
    </Button>
  );
}
