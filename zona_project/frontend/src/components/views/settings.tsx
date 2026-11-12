"use client";

import { BookA, Bot, UserRound, Users } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { Page, PageHeader } from "@/components/common/page";
import { AiTab } from "@/components/settings/ai-tab";
import { DictionaryTab } from "@/components/settings/dictionary-tab";
import { ProfileTab } from "@/components/settings/profile-tab";
import { UsersTab } from "@/components/settings/users-tab";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCan } from "@/hooks/use-org";

const TABS = ["profile", "users", "ai", "dictionary"] as const;
type Tab = (typeof TABS)[number];

/** Sozlamalar: profil hamma uchun; foydalanuvchilar va AI — faqat admin; lug'at — ko'rish hammaga, tahrir muharrirga. */
export function Settings() {
  const t = useTranslations();
  const can = useCan();
  const router = useRouter();
  const params = useSearchParams();
  const allowed: Tab[] = TABS.filter((x) => can.admin || (x !== "users" && x !== "ai"));
  const requested = params.get("tab") as Tab | null;
  const tab: Tab = requested && allowed.includes(requested) ? requested : "profile";
  const icons = { profile: UserRound, users: Users, ai: Bot, dictionary: BookA } as const;

  return (
    <Page>
      <PageHeader title={t("nav.settings")} description={t("settings.description")} />
      <Tabs value={tab} onValueChange={(v) => router.replace(`/settings?tab=${v}`, { scroll: false })}>
        <TabsList className="mb-4">
          {allowed.map((x) => {
            const Icon = icons[x];
            return <TabsTrigger key={x} value={x}><Icon className="size-4" />{t(`settings.tabs.${x}`)}</TabsTrigger>;
          })}
        </TabsList>
        <TabsContent value="profile"><ProfileTab /></TabsContent>
        {can.admin && <TabsContent value="users"><UsersTab /></TabsContent>}
        {can.admin && <TabsContent value="ai"><AiTab /></TabsContent>}
        <TabsContent value="dictionary"><DictionaryTab /></TabsContent>
      </Tabs>
    </Page>
  );
}
