"use client";

import { NextIntlClientProvider } from "next-intl";
import { useEffect, type ReactNode } from "react";

import { useUI, type Locale } from "@/stores/ui";

import en from "./messages/en.json";
import ru from "./messages/ru.json";
import uz from "./messages/uz.json";

export const MESSAGES = { uz, ru, en } as const;
export const LOCALES: { code: Locale; label: string }[] = [
  { code: "uz", label: "O'zbekcha" },
  { code: "ru", label: "Русский" },
  { code: "en", label: "English" },
];

/** Til mijoz tomonida tanlanadi (yuqori paneldagi til tanlagich) va localStorage'da saqlanadi. */
export function I18nProvider({ children }: { children: ReactNode }) {
  const locale = useUI((s) => s.locale);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return (
    <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]} timeZone="Asia/Tashkent">
      {children}
    </NextIntlClientProvider>
  );
}
