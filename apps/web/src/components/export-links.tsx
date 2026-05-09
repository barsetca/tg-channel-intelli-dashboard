"use client";

import { Download } from "lucide-react";
import { exportChannelsUrl } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";

export function ExportLinks() {
  return (
    <Card>
      <CardTitle>Экспорт каталога каналов</CardTitle>
      <CardDescription>
        Скачайте данные сохранённого каталога для внешних инструментов и отчётности (сценарий 7).
      </CardDescription>
      <div className="mt-4 flex flex-wrap gap-3">
        <a href={exportChannelsUrl("json")} download target="_blank" rel="noreferrer">
          <Button variant="secondary" className="w-full sm:w-auto">
            <Download className="size-4" />
            JSON
          </Button>
        </a>
        <a href={exportChannelsUrl("csv")} download target="_blank" rel="noreferrer">
          <Button variant="secondary" className="w-full sm:w-auto">
            <Download className="size-4" />
            CSV
          </Button>
        </a>
      </div>
    </Card>
  );
}
