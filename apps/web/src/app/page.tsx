import Link from "next/link";
import { BarChart3, HeartPulse, Layers, LineChart, Search, Sparkles } from "lucide-react";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";

const tiles = [
  {
    href: "/search",
    title: "Поиск каналов",
    desc: "Сценарий 1: поиск по сохраненному каталогу и Telegram с фильтрами.",
    icon: Search,
  },
  {
    href: "/channel-analysis",
    title: "Анализ канала",
    desc: "Сценарий 2 и 3: полный анализ канала и резюмирование последних постов.",
    icon: LineChart,
  },
  {
    href: "/semantic-search",
    title: "Семантический поиск",
    desc: "Сценарий 4: поиск по накопленным данным и ответы с источниками.",
    icon: Layers,
  },
  {
    href: "/compare",
    title: "Сравнение каналов",
    desc: "Сценарий 5: сравнение нескольких каналов по ключевым метрикам.",
    icon: BarChart3,
  },
  {
    href: "/health",
    title: "Состояние API",
    desc: "Проверка доступности сервера и режима работы.",
    icon: HeartPulse,
  },
];

export default function Home() {
  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <div className="flex flex-wrap items-start gap-4">
        <div className="rounded-2xl border border-violet-200 bg-violet-50 p-3">
          <Sparkles className="size-10 text-violet-600" />
        </div>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">Telegram Channel Intelligence</h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-zinc-600">
            Операционная панель для поиска каналов, анализа контента, сводок постов, семантического поиска и сравнения.
          </p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {tiles.map(({ href, title, desc, icon: Icon }) => (
          <Link key={href} href={href} className="group block">
            <Card className="h-full transition group-hover:border-violet-300 group-hover:bg-violet-50/40">
              <div className="flex items-start gap-3">
                <Icon className="mt-0.5 size-5 shrink-0 text-violet-600" />
                <div>
                  <CardTitle className="text-base group-hover:text-violet-800">{title}</CardTitle>
                  <CardDescription className="mt-1">{desc}</CardDescription>
                </div>
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
