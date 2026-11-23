"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { LockKeyhole } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { use, useEffect, useState } from "react";
import { browser } from "react-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Brand } from "@/components/layout/sidebar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { I18nProvider } from "@/i18n/provider";
import { errorMessage } from "@/lib/api/client";
import { authApi } from "@/lib/api/endpoints";
import { useAuth } from "@/stores/auth";

const schema = z.object({
  username: z.string().trim().min(1),
  password: z.string().min(1),
});
type Values = z.infer<typeof schema>;

/** Kirgandan keyin: faqat inventarizatsiya logini — o'z moduliga; ?next= bo'lsa — o'sha sahifaga. */
function home(role?: string) {
  if (role === "inventory") return "/inventory";
  const next = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("next") : null;
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

function LoginForm() {
  const t = useTranslations("login");
  const router = useRouter();
  const setSession = useAuth((s) => s.setSession);
  const access = useAuth((s) => s.access);
  const role = useAuth((s) => s.user?.role);
  const [error, setError] = useState("");
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { username: "", password: "" } });

  useEffect(() => {
    if (access) router.replace(home(role));
  }, [access, role, router]);

  const onSubmit = form.handleSubmit(async ({ username, password }) => {
    setError("");
    try {
      const r = await authApi.login(username, password);
      setSession(r, r.user);
      router.replace(home(r.user.role));
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  return (
    <div className="canvas-grid grid h-full place-items-center overflow-y-auto p-6">
      <Card className="glass w-full max-w-md gap-6 p-8 shadow-2xl">
        <Brand />
        <div>
          <h1 className="text-xl font-semibold">{t("title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        <form onSubmit={onSubmit} noValidate>
          <FieldGroup>
            <Field data-invalid={!!form.formState.errors.username}>
              <FieldLabel htmlFor="username">{t("username")}</FieldLabel>
              <Input id="username" autoComplete="username" autoFocus {...form.register("username")} />
            </Field>
            <Field data-invalid={!!form.formState.errors.password}>
              <FieldLabel htmlFor="password">{t("password")}</FieldLabel>
              <Input id="password" type="password" autoComplete="current-password" {...form.register("password")} />
            </Field>
            {error && <FieldError>{error}</FieldError>}
            <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
              <LockKeyhole className="size-4" />{form.formState.isSubmitting ? t("submitting") : t("submit")}
            </Button>
          </FieldGroup>
        </form>
        <p className="text-xs text-muted-foreground">{t("hint")}</p>
      </Card>
    </div>
  );
}

export function LoginScreen() {
  use(browser("Kirish holati localStorage'da"));
  return (
    <I18nProvider>
      <LoginForm />
    </I18nProvider>
  );
}
