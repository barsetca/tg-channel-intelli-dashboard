"use client";

import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

export type AttachedMedia = {
  base64: string;
  filename: string;
};

type MediaAttachFieldProps = {
  label?: string;
  value: AttachedMedia | null;
  onChange: (value: AttachedMedia | null) => void;
  accept?: string;
};

function fileToAttached(file: File): Promise<AttachedMedia> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      const b64 = dataUrl.includes(",") ? dataUrl.split(",")[1] : dataUrl;
      if (!b64) {
        reject(new Error("Пустой файл"));
        return;
      }
      resolve({ base64: b64, filename: file.name });
    };
    reader.onerror = () => reject(new Error("Не удалось прочитать файл"));
    reader.readAsDataURL(file);
  });
}

export function mediaFieldsForApi(
  media: AttachedMedia | null,
  legacyImageB64?: string | null,
): { media_base64?: string; media_filename?: string; image_base64?: string } {
  if (media) {
    return { media_base64: media.base64, media_filename: media.filename };
  }
  if (legacyImageB64) {
    return { image_base64: legacyImageB64 };
  }
  return {};
}

export function MediaAttachField({
  label = "Медиафайл (необязательно)",
  value,
  onChange,
  accept = "image/*,video/*,audio/*",
}: MediaAttachFieldProps) {
  const hint = useMemo(() => {
    if (!value) return null;
    const lower = value.filename.toLowerCase();
    if (/\.(mp4|mov|webm|mkv|m4v)$/.test(lower)) return "Видео";
    if (/\.(mp3|ogg|wav|m4a|opus|flac)$/.test(lower)) return "Аудио";
    if (/\.(jpe?g|png|gif|webp)$/.test(lower)) return "Изображение";
    return "Файл";
  }, [value]);

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex flex-wrap items-center gap-2">
        <label className="cursor-pointer">
          <span className="inline-flex rounded-xl bg-white px-3 py-2 text-sm font-medium text-violet-700 ring-1 ring-violet-200 hover:bg-violet-50">
            Выбрать файл
          </span>
          <input
            type="file"
            accept={accept}
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              void fileToAttached(file)
                .then(onChange)
                .catch(() => onChange(null));
              e.target.value = "";
            }}
          />
        </label>
        {value ? (
          <>
            <span className="text-sm text-zinc-600">
              {hint}: {value.filename}
            </span>
            <Button type="button" variant="ghost" onClick={() => onChange(null)}>
              Убрать
            </Button>
          </>
        ) : (
          <span className="text-xs text-zinc-500">Одно изображение, видео или аудио</span>
        )}
      </div>
    </div>
  );
}
