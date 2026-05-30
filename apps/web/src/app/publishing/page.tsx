"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  generatePublishingPost,
  listPublishableChannels,
  publishGeneratedPost,
  publishManualPost,
  sendTelegramChatMessage,
} from "@/lib/api-client";
import type {
  GeneratedPostResponse,
  PublishableChannel,
  PublishingOutputMode,
  PublishResultResponse,
} from "@/lib/types/api";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";

const selectClass =
  "w-full rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-500/20";

type TabId = "ai" | "manual" | "chat";

function channelLabel(ch: PublishableChannel): string {
  const name = ch.title || ch.username || `id ${ch.telegram_channel_id}`;
  return ch.username ? `${name} (@${ch.username.replace(/^@/, "")})` : name;
}

function toChannelRef(ch: PublishableChannel): string {
  return ch.username ? `@${ch.username.replace(/^@/, "")}` : String(ch.telegram_channel_id);
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      const b64 = dataUrl.includes(",") ? dataUrl.split(",")[1] : dataUrl;
      resolve(b64 || "");
    };
    reader.onerror = () => reject(new Error("Не удалось прочитать файл"));
    reader.readAsDataURL(file);
  });
}

export default function PublishingPage() {
  const [tab, setTab] = useState<TabId>("ai");
  const [channels, setChannels] = useState<PublishableChannel[]>([]);
  const [channelsLoading, setChannelsLoading] = useState(true);
  const [channelsError, setChannelsError] = useState<string | null>(null);

  const [channelRef, setChannelRef] = useState("");
  const [topic, setTopic] = useState("");
  const [charCount, setCharCount] = useState(1200);
  const [extraInfo, setExtraInfo] = useState("");
  const [outputMode, setOutputMode] = useState<PublishingOutputMode>("post_with_image");

  /** Метаданные последней генерации (для предпросмотра). */
  const [previewMeta, setPreviewMeta] = useState<GeneratedPostResponse | null>(null);
  const [editPostText, setEditPostText] = useState("");
  const [editImageB64, setEditImageB64] = useState<string | null>(null);

  const [publishResult, setPublishResult] = useState<PublishResultResponse | null>(null);
  const [directPublishSummary, setDirectPublishSummary] = useState<{
    topic: string;
    output_mode: string;
    message_id: number;
    peer_ref: string;
  } | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [manualText, setManualText] = useState("");
  const [manualImageB64, setManualImageB64] = useState<string | null>(null);

  const [chatRef, setChatRef] = useState("");
  const [chatText, setChatText] = useState("");

  const imageSrc = useMemo(
    () => (editImageB64 ? `data:image/png;base64,${editImageB64}` : null),
    [editImageB64],
  );

  const showPreviewEditor = previewMeta !== null;

  useEffect(() => {
    void (async () => {
      setChannelsLoading(true);
      setChannelsError(null);
      try {
        const rows = await listPublishableChannels();
        setChannels(rows);
        if (rows.length) {
          setChannelRef((prev) => prev || toChannelRef(rows[0]));
        }
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : "Не удалось загрузить каналы";
        setChannelsError(
          `${msg}. Укажите @username канала вручную — нужны права администратора с публикацией постов.`,
        );
      } finally {
        setChannelsLoading(false);
      }
    })();
  }, []);

  const buildAiBody = () => ({
    topic: topic.trim(),
    char_count: charCount,
    extra_info: extraInfo.trim() || null,
    output_mode: outputMode,
  });

  const applyGeneratedToEditor = (res: GeneratedPostResponse) => {
    setPreviewMeta(res);
    setEditPostText(res.post_text ?? "");
    setEditImageB64(res.image_base64 || null);
    setDirectPublishSummary(null);
  };

  const clearPreviewEditor = () => {
    setPreviewMeta(null);
    setEditPostText("");
    setEditImageB64(null);
  };

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setPublishResult(null);
    try {
      const res = await generatePublishingPost(buildAiBody());
      applyGeneratedToEditor(res);
    } catch (e) {
      clearPreviewEditor();
      setError(e instanceof ApiError ? e.message : "Ошибка генерации");
    } finally {
      setLoading(false);
    }
  };

  const handlePublishGenerated = async () => {
    const ref = channelRef.trim();
    if (!ref) {
      setError("Укажите канал для публикации");
      return;
    }
    setLoading(true);
    setError(null);
    setPublishResult(null);
    clearPreviewEditor();
    try {
      const res = await publishGeneratedPost({
        ...buildAiBody(),
        channel_ref: ref,
      });
      setPublishResult(res.published);
      setDirectPublishSummary({
        topic: res.generated.topic,
        output_mode: res.generated.output_mode,
        message_id: res.published.telegram_message_id,
        peer_ref: res.published.peer_ref,
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ошибка публикации");
    } finally {
      setLoading(false);
    }
  };

  const handlePublishPreview = async () => {
    const ref = channelRef.trim();
    if (!previewMeta || !ref) {
      setError("Сначала сгенерируйте пост и выберите канал");
      return;
    }
    const publishText =
      outputMode === "infographic_only" ? null : editPostText.trim() || null;
    if (!publishText && !editImageB64) {
      setError("Добавьте текст или изображение перед публикацией");
      return;
    }
    if (outputMode === "infographic_only" && !editImageB64) {
      setError("Для режима «только инфографика» нужно изображение");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const pub = await publishManualPost({
        channel_ref: ref,
        text: publishText,
        image_base64: editImageB64,
      });
      setPublishResult(pub);
      clearPreviewEditor();
      setDirectPublishSummary(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ошибка публикации");
    } finally {
      setLoading(false);
    }
  };

  const onReplacePreviewImage = async (file: File | null) => {
    if (!file) return;
    try {
      const b64 = await fileToBase64(file);
      setEditImageB64(b64 || null);
    } catch {
      setError("Не удалось загрузить изображение");
    }
  };

  const handleManualPublish = async () => {
    const ref = channelRef.trim();
    if (!ref) {
      setError("Укажите канал");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const pub = await publishManualPost({
        channel_ref: ref,
        text: manualText.trim() || null,
        image_base64: manualImageB64,
      });
      setPublishResult(pub);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ошибка публикации");
    } finally {
      setLoading(false);
    }
  };

  const handleSendChat = async () => {
    setLoading(true);
    setError(null);
    try {
      const pub = await sendTelegramChatMessage({
        chat_ref: chatRef.trim(),
        text: chatText.trim(),
      });
      setPublishResult(pub);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Ошибка отправки");
    } finally {
      setLoading(false);
    }
  };

  const onManualFile = (file: File | null) => {
    if (!file) {
      setManualImageB64(null);
      return;
    }
    void fileToBase64(file).then(setManualImageB64).catch(() => setError("Не удалось прочитать файл"));
  };

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Публикация в Telegram</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Генерация постов в стиле автора (OpenAI) и публикация через вашу Telethon-сессию.
        </p>
      </div>

      {channelsError ? (
        <Alert variant="warning" title="Telegram">
          {channelsError}
        </Alert>
      ) : null}
      {error ? (
        <Alert variant="error" title="Ошибка">
          {error}
        </Alert>
      ) : null}
      {publishResult ? (
        <Alert variant="info" title="Опубликовано">
          Сообщение #{publishResult.telegram_message_id} в {publishResult.peer_ref},{" "}
          {new Date(publishResult.published_at_utc).toLocaleString()}
          {directPublishSummary ? (
            <span className="mt-2 block text-sm opacity-90">
              Тема: «{directPublishSummary.topic}» · режим:{" "}
              {directPublishSummary.output_mode === "infographic_only"
                ? "только инфографика"
                : "пост с картинкой"}
            </span>
          ) : null}
        </Alert>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["ai", "AI-пост в канал"],
            ["manual", "Ручная публикация"],
            ["chat", "Сообщение в чат"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`rounded-xl px-4 py-2 text-sm font-medium transition ${
              tab === id ? "bg-violet-600 text-white" : "bg-white text-zinc-700 ring-1 ring-zinc-200 hover:bg-zinc-50"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "ai" ? (
        <Card className="space-y-5 p-6">
          <div>
            <CardTitle>AI-пост с иллюстрацией</CardTitle>
            <CardDescription className="mt-1">
              «Предпросмотр» — правка текста и картинки, затем публикация. «Сгенерировать и опубликовать» — сразу
              в канал без редактора.
            </CardDescription>
          </div>

          <div className="space-y-2">
            <Label>Канал</Label>
            {channelsLoading ? (
              <Spinner />
            ) : channels.length > 0 ? (
              <select
                className={selectClass}
                value={channelRef}
                onChange={(e) => setChannelRef(e.target.value)}
              >
                {channels.map((ch) => (
                  <option key={ch.telegram_channel_id} value={toChannelRef(ch)}>
                    {channelLabel(ch)}
                  </option>
                ))}
              </select>
            ) : (
              <>
                <Input
                  placeholder="@my_channel или t.me/..."
                  value={channelRef}
                  onChange={(e) => setChannelRef(e.target.value)}
                />
                <p className="text-xs text-zinc-500">
                  Список каналов пуст — введите @username канала, где вы администратор.
                </p>
              </>
            )}
          </div>

          <div className="space-y-2">
            <Label>Тема поста</Label>
            <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Например: ИИ на рынке труда" />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Объём (символов)</Label>
              <Input
                type="number"
                min={200}
                max={4096}
                value={charCount}
                onChange={(e) => setCharCount(Number(e.target.value) || 1200)}
              />
            </div>
            <div className="space-y-2">
              <Label>Формат</Label>
              <select
                className={selectClass}
                value={outputMode}
                onChange={(e) => setOutputMode(e.target.value as PublishingOutputMode)}
              >
                <option value="post_with_image">Пост: картинка + текст</option>
                <option value="infographic_only">Только инфографика (без текста в канале)</option>
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Дополнительно (необязательно)</Label>
            <Textarea
              rows={3}
              value={extraInfo}
              onChange={(e) => setExtraInfo(e.target.value)}
              placeholder="Факты, тезисы, ссылки — что учесть в посте"
            />
          </div>

          <div className="flex flex-wrap gap-3">
            <Button type="button" disabled={loading || !topic.trim()} onClick={() => void handleGenerate()}>
              {loading ? <Spinner className="mr-2" /> : null}
              Предпросмотр
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={loading || !topic.trim() || !channelRef.trim()}
              onClick={() => void handlePublishGenerated()}
            >
              Сгенерировать и опубликовать
            </Button>
          </div>

          {showPreviewEditor && previewMeta ? (
            <div className="space-y-4 rounded-xl border border-violet-200 bg-violet-50/40 p-4">
              <p className="text-sm font-medium text-violet-900">Редактирование перед публикацией</p>

              {outputMode === "post_with_image" ? (
                <div className="space-y-2">
                  <Label>Текст поста ({editPostText.length} зн.)</Label>
                  <Textarea
                    rows={12}
                    value={editPostText}
                    onChange={(e) => setEditPostText(e.target.value)}
                    className="font-sans text-sm"
                  />
                </div>
              ) : (
                <div className="space-y-2">
                  <Label>Черновик смысла (в канал не уходит, {editPostText.length} зн.)</Label>
                  <Textarea
                    rows={6}
                    value={editPostText}
                    onChange={(e) => setEditPostText(e.target.value)}
                    className="font-sans text-sm text-zinc-600"
                  />
                </div>
              )}

              <div className="space-y-2">
                <Label>Изображение</Label>
                {imageSrc ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={imageSrc} alt="Предпросмотр" className="max-h-96 w-full rounded-lg object-contain bg-white" />
                ) : (
                  <p className="rounded-lg border border-dashed border-zinc-300 bg-white px-4 py-8 text-center text-sm text-zinc-500">
                    Изображение удалено — можно загрузить другое или опубликовать только текст
                  </p>
                )}
                <div className="flex flex-wrap gap-2">
                  <label className="cursor-pointer">
                    <span className="inline-flex rounded-xl bg-white px-3 py-2 text-sm font-medium text-violet-700 ring-1 ring-violet-200 hover:bg-violet-50">
                      Заменить картинку
                    </span>
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => void onReplacePreviewImage(e.target.files?.[0] ?? null)}
                    />
                  </label>
                  {editImageB64 ? (
                    <Button type="button" variant="ghost" onClick={() => setEditImageB64(null)}>
                      Удалить картинку
                    </Button>
                  ) : null}
                </div>
              </div>

              <p className="text-xs text-zinc-500">Промпт генерации: {previewMeta.image_prompt_used}</p>

              <div className="flex flex-wrap gap-3 border-t border-violet-100 pt-4">
                <Button
                  type="button"
                  disabled={loading || !channelRef.trim()}
                  onClick={() => void handlePublishPreview()}
                >
                  {loading ? <Spinner className="mr-2" /> : null}
                  Опубликовать предпросмотр
                </Button>
                <Button type="button" variant="ghost" disabled={loading} onClick={clearPreviewEditor}>
                  Отменить
                </Button>
              </div>
            </div>
          ) : null}
        </Card>
      ) : null}

      {tab === "manual" ? (
        <Card className="space-y-5 p-6">
          <div>
            <CardTitle>Ручная публикация в канал</CardTitle>
            <CardDescription className="mt-1">Готовый текст и/или изображение без AI</CardDescription>
          </div>
          <div className="space-y-2">
            <Label>Канал</Label>
            <Input value={channelRef} onChange={(e) => setChannelRef(e.target.value)} placeholder="@channel" />
          </div>
          <div className="space-y-2">
            <Label>Текст</Label>
            <Textarea rows={8} value={manualText} onChange={(e) => setManualText(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Изображение</Label>
            <Input type="file" accept="image/*" onChange={(e) => onManualFile(e.target.files?.[0] ?? null)} />
          </div>
          <Button type="button" disabled={loading} onClick={() => void handleManualPublish()}>
            Опубликовать
          </Button>
        </Card>
      ) : null}

      {tab === "chat" ? (
        <Card className="space-y-5 p-6">
          <div>
            <CardTitle>Сообщение в чат</CardTitle>
            <CardDescription className="mt-1">Отправка от имени вашей Telegram-сессии</CardDescription>
          </div>
          <div className="space-y-2">
            <Label>Чат</Label>
            <Input
              value={chatRef}
              onChange={(e) => setChatRef(e.target.value)}
              placeholder="@username, id или ссылка"
            />
          </div>
          <div className="space-y-2">
            <Label>Текст</Label>
            <Textarea rows={4} value={chatText} onChange={(e) => setChatText(e.target.value)} />
          </div>
          <Button type="button" disabled={loading || !chatRef.trim() || !chatText.trim()} onClick={() => void handleSendChat()}>
            Отправить
          </Button>
        </Card>
      ) : null}

      <p className="text-xs text-zinc-500">
        Стиль постов: context/post_style.txt · OPENAI_CHAT_MODEL · OPENAI_IMAGE_MODEL
      </p>
    </div>
  );
}
