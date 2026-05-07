import Link from "next/link";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import { fetchHealth } from "@/lib/api-client";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";

export const dynamic = "force-dynamic";

const ENVIRONMENT_LABELS: Record<string, string> = {
  development: "Разработка",
  staging: "Промежуточное окружение (staging)",
  production: "Продакшен",
};

function environmentDescription(env: string): string {
  if (env === "production") {
    return (
      "Сервер запущен в рабочем режиме. Метка окружения нужна для эксплуатации и диагностики; " +
      "отдельной «упрощённой» версии интерфейса при смене режима в приложении нет."
    );
  }
  if (env === "staging") {
    return "Промежуточное окружение между разработкой и продакшеном (часто для тестов перед выкладкой).";
  }
  return (
    "Режим разработки (например, локальный или тестовый сервер). " +
    "В коде включено подробнее логирование SQL‑запросов к базе — на ответ пользователю сценарии это напрямую не влияет."
  );
}

export default async function HealthPage() {
  let payload: Awaited<ReturnType<typeof fetchHealth>> | null = null;
  let error: string | null = null;
  try {
    payload = await fetchHealth();
  } catch (e) {
    error = e instanceof Error ? e.message : "Неизвестная ошибка";
  }

  const ok = payload?.status === "ok";
  const rawEnv = (payload?.environment ?? "").toLowerCase();
  const envLabel = ENVIRONMENT_LABELS[rawEnv] ?? (rawEnv.trim() ? rawEnv : "—");

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <Link href="/" className="text-sm text-zinc-600 transition hover:text-zinc-900">
        ← На главную
      </Link>

      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Состояние API</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Краткая проверка, что сервер приложения доступен и в каком режиме он запущен.
        </p>
      </div>

      {payload ? (
        <Card className={`border ${ok ? "border-emerald-200 bg-emerald-50/60" : "border-amber-200 bg-amber-50/50"}`}>
          <div className="flex gap-4">
            {ok ? (
              <CheckCircle2 className="size-12 shrink-0 text-emerald-600" aria-hidden />
            ) : (
              <AlertCircle className="size-12 shrink-0 text-amber-600" aria-hidden />
            )}
            <div className="min-w-0">
              <CardTitle className={ok ? "text-emerald-900" : "text-amber-900"}>
                {ok ? "Сервер доступен" : "Сервер отвечает со статусом, отличным от «ок»"}
              </CardTitle>
              <CardDescription className="mt-1 text-zinc-700">
                HTTP‑отчёт сервера: статус «{payload.status ?? "—"}».
              </CardDescription>
              <dl className="mt-4 space-y-3 text-sm text-zinc-800">
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">Режим окружения</dt>
                  <dd className="mt-1 font-medium text-zinc-900">{envLabel}</dd>
                  <dd className="mt-2 text-xs leading-relaxed text-zinc-600">{environmentDescription(rawEnv)}</dd>
                </div>
              </dl>
            </div>
          </div>
        </Card>
      ) : (
        <Card className="border border-red-200 bg-red-50/60">
          <div className="flex gap-4">
            <AlertCircle className="size-11 shrink-0 text-red-600" aria-hidden />
            <div>
              <CardTitle className="text-red-900">Нет связи с API</CardTitle>
              <CardDescription className="mt-1 text-red-900/90">
                {error ?? "Сервер не ответил. Проверьте сеть или запуск backend-сервиса."}
              </CardDescription>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
