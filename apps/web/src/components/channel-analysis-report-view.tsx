"use client";

import type { ChannelAnalysisReport } from "@/lib/types/api";

export function StrategyField({ label, value }: { label: string; value: string }) {
  if (!value?.trim()) return null;
  return (
    <div className="rounded-lg border border-zinc-100 bg-zinc-50/80 p-3">
      <p className="text-xs font-medium text-zinc-500">{label}</p>
      <p className="mt-1 whitespace-pre-wrap text-sm text-zinc-800">{value}</p>
    </div>
  );
}

export function AnalysisReportView({ report }: { report: ChannelAnalysisReport }) {
  const cs = report.content_strategy;
  const tv = report.tone_of_voice;
  return (
    <div className="mt-4 space-y-6">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-zinc-200 p-3">
          <p className="text-xs text-zinc-500">Описание канала</p>
          <p className="mt-1 text-sm text-zinc-800">{report.channel_description}</p>
        </div>
        <div className="rounded-xl border border-zinc-200 p-3">
          <p className="text-xs text-zinc-500">Тематика</p>
          <p className="mt-1 text-sm text-zinc-800">{report.topic}</p>
        </div>
        <div className="rounded-xl border border-zinc-200 p-3">
          <p className="text-xs text-zinc-500">Подписчиков</p>
          <p className="mt-1 text-sm text-zinc-800">
            {report.subscribers_count != null ? report.subscribers_count.toLocaleString() : "—"}
          </p>
        </div>
        <div className="rounded-xl border border-zinc-200 p-3">
          <p className="text-xs text-zinc-500">Дата отчёта</p>
          <p className="mt-1 text-sm text-zinc-800">
            {report.report_created_at
              ? new Date(report.report_created_at).toLocaleString(undefined, {
                  dateStyle: "medium",
                  timeStyle: "short",
                })
              : "—"}
          </p>
        </div>
        <div className="rounded-xl border border-zinc-200 p-3">
          <p className="text-xs text-zinc-500">Частота публикаций (метрика)</p>
          <p className="mt-1 text-sm text-zinc-800">{report.publication_frequency}</p>
        </div>
        <div className="rounded-xl border border-zinc-200 p-3">
          <p className="text-xs text-zinc-500">Средняя длина постов</p>
          <p className="mt-1 text-sm text-zinc-800">{report.avg_post_length ?? "—"} симв.</p>
        </div>
      </div>

      <div className="rounded-xl border border-zinc-200 p-4">
        <p className="text-sm font-semibold text-zinc-900">Краткое содержание постов</p>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-zinc-700">{report.posts_summary}</p>
      </div>

      <div className="rounded-xl border border-violet-200 bg-violet-50/40 p-4">
        <p className="text-sm font-semibold text-violet-950">Контент-стратегия и позиционирование</p>
        <p className="mt-1 text-xs text-violet-900/80">
          Цели, темы, форматы, рубрикатор, ЦА, SEO и вовлечённость — выводы по каналу, не пересказ текстов.
        </p>
        <div className="mt-4 grid gap-2 md:grid-cols-2">
          <StrategyField label="Цели канала" value={cs.goals} />
          <StrategyField label="Основные темы" value={cs.main_topics} />
          <StrategyField label="Форматы" value={cs.formats} />
          <StrategyField label="Частота и ритм (редакция)" value={cs.cadence} />
          <StrategyField label="Рубрикатор" value={cs.rubricator} />
          <StrategyField label="Целевая аудитория" value={cs.target_audience} />
          <StrategyField label="SEO и ключевые акценты" value={cs.seo_focus} />
          <StrategyField label="Вовлечённость аудитории" value={cs.engagement} />
        </div>
      </div>

      <div className="rounded-xl border border-cyan-200 bg-cyan-50/40 p-4">
        <p className="text-sm font-semibold text-cyan-950">Tone of voice</p>
        <p className="mt-1 text-xs text-cyan-900/80">Стиль подачи и согласованность с позиционированием.</p>
        <div className="mt-4 grid gap-2 md:grid-cols-2">
          <StrategyField label="Стиль" value={tv.style} />
          <StrategyField label="Лексика" value={tv.lexicon} />
          <StrategyField label="Эмоции" value={tv.emotions} />
          <StrategyField label="Обращение (ты / вы)" value={tv.distance} />
          <StrategyField label="Единообразие" value={tv.consistency} />
          <StrategyField label="Согласованность с позиционированием и ЦА" value={tv.vs_positioning} />
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-zinc-200 p-3">
          <p className="text-xs font-medium text-zinc-600">SWOT: сильные стороны канала</p>
          <ul className="mt-2 list-inside list-disc text-sm text-zinc-800">
            {report.strengths.length ? report.strengths.map((x) => <li key={x}>{x}</li>) : <li>—</li>}
          </ul>
        </div>
        <div className="rounded-xl border border-zinc-200 p-3">
          <p className="text-xs font-medium text-zinc-600">SWOT: риски канала</p>
          <ul className="mt-2 list-inside list-disc text-sm text-zinc-800">
            {report.risks.length ? report.risks.map((x) => <li key={x}>{x}</li>) : <li>—</li>}
          </ul>
        </div>
      </div>

      <div className="rounded-xl border border-zinc-200 p-4">
        <p className="text-sm font-semibold text-zinc-900">Рекомендации</p>
        <ul className="mt-2 list-inside list-disc text-sm text-zinc-800">
          {report.recommendations.length ? report.recommendations.map((x) => <li key={x}>{x}</li>) : <li>—</li>}
        </ul>
      </div>
    </div>
  );
}
