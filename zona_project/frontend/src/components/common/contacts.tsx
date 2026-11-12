import { Mail, MapPin, Phone, Send } from "lucide-react";

import type { Member } from "@/lib/api/types";

type Contact = Pick<Member, "phone" | "telegram" | "email"> & { location?: string };

/** Telefon, Telegram, email — bosilsa qo'ng'iroq / chat / xat ochiladi. */
export function ContactLinks({ contact, empty }: { contact: Contact; empty?: string }) {
  const tg = contact.telegram.replace(/^@/, "");
  const chip = "inline-flex h-7 items-center gap-1.5 rounded-full border bg-muted/60 px-2.5 text-xs hover:border-primary/50";
  const items = [
    contact.phone && (
      <a key="p" className={chip} href={`tel:${contact.phone.replace(/[^\d+]/g, "")}`}><Phone className="size-3" />{contact.phone}</a>
    ),
    tg && (
      <a key="t" className={chip} href={`https://t.me/${tg}`} target="_blank" rel="noopener noreferrer"><Send className="size-3" />@{tg}</a>
    ),
    contact.email && <a key="e" className={chip} href={`mailto:${contact.email}`}><Mail className="size-3" />{contact.email}</a>,
    contact.location && <span key="l" className={chip}><MapPin className="size-3" />{contact.location}</span>,
  ].filter(Boolean);
  if (!items.length) return empty ? <span className="text-sm text-muted-foreground">{empty}</span> : null;
  return <div className="flex flex-wrap gap-1.5">{items}</div>;
}
