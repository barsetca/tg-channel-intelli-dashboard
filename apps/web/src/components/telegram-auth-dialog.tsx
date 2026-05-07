"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { ApiError, telegramAuthCode, telegramAuthPassword, telegramAuthStart } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Alert } from "@/components/ui/alert";

type Step = "phone" | "code" | "password";

type TelegramAuthDialogProps = {
  open: boolean;
  onClose: () => void;
  /** После успешной авторизации (сессия поднята на сервере). */
  onSuccess: () => void;
};

export function TelegramAuthDialog({ open, onClose, onSuccess }: TelegramAuthDialogProps) {
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [flowId, setFlowId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setStep("phone");
      setCode("");
      setPassword("");
      setFlowId(null);
      setError(null);
      setBusy(false);
    }
  }, [open]);

  if (!open) return null;

  async function onSendPhone(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await telegramAuthStart(phone.trim());
      setFlowId(res.flow_id);
      setStep("code");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отправить код");
    } finally {
      setBusy(false);
    }
  }

  async function onSubmitCode(e: React.FormEvent) {
    e.preventDefault();
    if (!flowId) return;
    setError(null);
    setBusy(true);
    try {
      const res = await telegramAuthCode(flowId, code.trim());
      if (res.status === "needs_password") {
        setFlowId(res.flow_id);
        setStep("password");
        return;
      }
      onSuccess();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Неверный код или ошибка сервера");
    } finally {
      setBusy(false);
    }
  }

  async function onSubmitPassword(e: React.FormEvent) {
    e.preventDefault();
    if (!flowId) return;
    setError(null);
    setBusy(true);
    try {
      await telegramAuthPassword(flowId, password);
      onSuccess();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ошибка входа");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-900/50 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tg-auth-title"
    >
      <div className="relative w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-6 shadow-xl">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 rounded-lg p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800"
          aria-label="Закрыть"
        >
          <X className="size-5" />
        </button>
        <h2 id="tg-auth-title" className="pr-10 text-lg font-semibold text-zinc-900">
          Вход в Telegram
        </h2>
        <p className="mt-1 text-sm text-zinc-600">
          Нужна авторизация для поиска каналов в реальном времени. Данные аккаунта не сохраняются в браузере — сессия
          остаётся на сервере API.
        </p>

        {error ? (
          <div className="mt-4">
            <Alert variant="error" title="Ошибка">
              {error}
            </Alert>
          </div>
        ) : null}

        {step === "phone" ? (
          <form onSubmit={onSendPhone} className="mt-6 space-y-4">
            <div>
              <Label htmlFor="tg-phone">Телефон</Label>
              <Input
                id="tg-phone"
                type="tel"
                autoComplete="tel"
                placeholder="+79991234567"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                required
                className="mt-1.5"
              />
              <p className="mt-1 text-xs text-zinc-500">Международный формат с «+».</p>
            </div>
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? <Spinner /> : null}
              Получить код
            </Button>
          </form>
        ) : null}

        {step === "code" ? (
          <form onSubmit={onSubmitCode} className="mt-6 space-y-4">
            <p className="text-sm text-zinc-600">Код отправлен на {phone}. Введите его ниже.</p>
            <div>
              <Label htmlFor="tg-code">Код из SMS или Telegram</Label>
              <Input
                id="tg-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
                className="mt-1.5"
              />
            </div>
            <div className="flex gap-2">
              <Button type="button" variant="secondary" onClick={() => setStep("phone")} disabled={busy}>
                Назад
              </Button>
              <Button type="submit" disabled={busy} className="flex-1">
                {busy ? <Spinner /> : null}
                Войти
              </Button>
            </div>
          </form>
        ) : null}

        {step === "password" ? (
          <form onSubmit={onSubmitPassword} className="mt-6 space-y-4">
            <p className="text-sm text-zinc-600">У аккаунта включена двухфакторная аутентификация. Введите пароль облака.</p>
            <div>
              <Label htmlFor="tg-pwd">Пароль 2FA</Label>
              <Input
                id="tg-pwd"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="mt-1.5"
              />
            </div>
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? <Spinner /> : null}
              Подтвердить
            </Button>
          </form>
        ) : null}
      </div>
    </div>
  );
}
