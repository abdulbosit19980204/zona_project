"use client";

import { BookOpen, KeyRound, Plus, Send, ShieldOff, Webhook } from "lucide-react";
import { useState } from "react";

import { EmptyState, Page, PageHeader, SectionTitle } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useQr, useQrAction } from "@/hooks/use-qrdrive";
import { QR_BASE, qrApi, type ApiKeyRow } from "@/lib/api/qrdrive";

import { ConfirmDialog, CopyButton, FormRow, QrGuard, fmtDate } from "./common";
import { useQt } from "./i18n";

interface Delivery { id: number; event: string; file_id: number | null; status: string; status_code: number | null; attempts: number; error: string; created_at: string }

function examples(origin: string) {
  const api = `${origin}${QR_BASE}/api/v1`;
  return {
    curl: `curl -X POST "${api}/files" \\
  -H "Authorization: Bearer qd_live_..." \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -F "file=@hujjat.pdf" \\
  -F "telegram_id=123456789"

# javob: {"id": 42, "status": "delivered", "url": "...", "qr_base64": "...", ...}
curl -H "Authorization: Bearer qd_live_..." "${api}/files/42/qr.png" -o qr.png`,
    python: `import httpx

API = "${api}"
KEY = "qd_live_..."

with open("hujjat.pdf", "rb") as f:
    r = httpx.post(f"{API}/files", headers={"Authorization": f"Bearer {KEY}"},
                   files={"file": f}, data={"telegram_id": 123456789}, timeout=120)
data = r.json()
print(data["status"], data["url"])          # delivered https://...
open("qr.png", "wb").write(__import__("base64").b64decode(data["qr_base64"]))`,
    aiogram: `# Boshqa aiogram 3 botga QR Drive funksiyasini qo'shish (5 qator)
import base64, httpx
from aiogram import F, Router
from aiogram.types import BufferedInputFile, Message

router = Router()

@router.message(F.document | F.photo)
async def to_qr(msg: Message):
    f = msg.document or msg.photo[-1]
    data = await msg.bot.download(f)
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post("${api}/files", headers={"Authorization": "Bearer qd_live_..."},
                         files={"file": (getattr(f, "file_name", None) or "rasm.jpg", data)},
                         data={"external_user": msg.from_user.username or str(msg.from_user.id)})
    res = r.json()
    if res["status"] == "delivered":
        await msg.answer_photo(BufferedInputFile(base64.b64decode(res["qr_base64"]), "qr.png"), caption=res["url"])
    else:
        await msg.answer("Fayl navbatda, birozdan keyin tayyor bo'ladi.")

# dp.include_router(router)`,
    webhook: `# Webhook imzosini tekshirish (Python)
import hashlib, hmac

def verify(body: bytes, header: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)   # header = X-QRDrive-Signature

# Hodisalar: file.completed, file.failed, link.revoked`,
  };
}

/** API kalitlar (faqat bir marta ko'rsatiladi), webhooklar, kod misollari va Swagger havolasi. */
export function QrApi() {
  const t = useQt();
  const keys = useQr<ApiKeyRow[]>(["api-keys"], "api-keys");
  const scopes = useQr<Record<string, string>>(["scopes"], "api-keys/scopes");
  const [form, setForm] = useState<null | { name: string; scopes: string[]; rate_limit: string; allowed_ips: string; expires_days: string; webhook_url: string }>(null);
  const [created, setCreated] = useState<ApiKeyRow | null>(null);
  const [revoke, setRevoke] = useState<ApiKeyRow | null>(null);
  const [hooks, setHooks] = useState<ApiKeyRow | null>(null);
  const create = useQrAction(async () => (await qrApi.post<ApiKeyRow>("api-keys", {
    name: form!.name, scopes: form!.scopes, rate_limit: Number(form!.rate_limit || 0),
    allowed_ips: form!.allowed_ips.split(",").map((s) => s.trim()).filter(Boolean),
    expires_days: Number(form!.expires_days || 0), webhook_url: form!.webhook_url,
  })).data);
  const doRevoke = useQrAction(async (id: number) => qrApi.delete(`api-keys/${id}`), t("revoked"));
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const ex = examples(origin);

  return (
    <Page>
      <PageHeader title={t("apiTitle")} description={t("apiDesc")} actions={
        <>
          <Button variant="outline" asChild><a href={`${QR_BASE}/api/docs`} target="_blank" rel="noreferrer"><BookOpen className="size-4" />{t("docs")}</a></Button>
          <Button onClick={() => setForm({ name: "", scopes: ["files:write", "files:read", "qr:generate"], rate_limit: "60", allowed_ips: "", expires_days: "0", webhook_url: "" })}>
            <Plus className="size-4" />{t("newKey")}
          </Button>
        </>
      } />
      <QrGuard query={keys}>
        {!keys.data?.length ? <EmptyState icon={KeyRound} title={t("noKeys")} /> : (
          <Card className="gap-0 overflow-hidden p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("keyName")}</TableHead>
                  <TableHead>{t("scopes")}</TableHead>
                  <TableHead>{t("lastUsed")}</TableHead>
                  <TableHead className="text-right">{t("uses")}</TableHead>
                  <TableHead className="w-48" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.data.map((k) => (
                  <TableRow key={k.id} className={k.revoked ? "opacity-50" : ""}>
                    <TableCell><div className="font-medium">{k.name}</div><div className="font-mono text-xs text-muted-foreground">{k.prefix}…</div>
                      {k.webhook_url && <div className="flex items-center gap-1 truncate text-xs text-muted-foreground"><Webhook className="size-3" />{k.webhook_url}</div>}</TableCell>
                    <TableCell><div className="flex flex-wrap gap-1">{k.scopes.map((s) => <Badge key={s} variant="outline" className="font-mono text-[10px]">{s}</Badge>)}</div></TableCell>
                    <TableCell className="text-xs text-muted-foreground">{fmtDate(k.last_used_at)}{k.expires_at && <div>{t("expires")}: {fmtDate(k.expires_at, false)}</div>}</TableCell>
                    <TableCell className="text-right font-mono text-sm">{k.uses}</TableCell>
                    <TableCell className="text-right">
                      {k.revoked ? <Badge variant="outline">{t("revoked")}</Badge> : (
                        <div className="flex justify-end gap-1">
                          {k.webhook_url && <Button size="sm" variant="ghost" onClick={() => setHooks(k)}><Webhook className="size-4" /></Button>}
                          <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setRevoke(k)}><ShieldOff className="size-4" />{t("revoke")}</Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </QrGuard>

      <SectionTitle>{t("examples")}</SectionTitle>
      <Tabs defaultValue="curl">
        <TabsList><TabsTrigger value="curl">curl</TabsTrigger><TabsTrigger value="python">Python</TabsTrigger>
          <TabsTrigger value="aiogram">aiogram plugin</TabsTrigger><TabsTrigger value="webhook">Webhook</TabsTrigger></TabsList>
        {(Object.keys(ex) as (keyof typeof ex)[]).map((k) => (
          <TabsContent key={k} value={k}>
            <Card className="relative gap-0 p-0">
              <div className="absolute right-2 top-2"><CopyButton text={ex[k]} /></div>
              <pre className="overflow-x-auto p-4 pr-28 font-mono text-xs leading-relaxed">{ex[k]}</pre>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
      <p className="mt-2 text-xs text-muted-foreground">
        <a className="text-primary hover:underline" href={`${QR_BASE}/api/docs`} target="_blank" rel="noreferrer">Swagger</a> ·{" "}
        <a className="text-primary hover:underline" href={`${QR_BASE}/api/redoc`} target="_blank" rel="noreferrer">{t("redoc")}</a> · SDK: <code>services/qrdrive/sdk/python</code>
      </p>

      <Dialog open={!!form} onOpenChange={(v) => !v && setForm(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>{t("newKey")}</DialogTitle></DialogHeader>
          {form && (
            <div className="grid gap-3">
              <FormRow label={t("keyName")}><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="HR bot" autoFocus /></FormRow>
              <FormRow label={t("scopes")}>
                <div className="grid gap-1.5">
                  {Object.entries(scopes.data ?? {}).map(([s, desc]) => (
                    <Label key={s} className="flex items-start gap-2 text-sm font-normal">
                      <Checkbox checked={form.scopes.includes(s)} onCheckedChange={(v) => setForm({ ...form, scopes: v ? [...form.scopes, s] : form.scopes.filter((x) => x !== s) })} />
                      <span><span className="font-mono text-xs">{s}</span><span className="block text-xs text-muted-foreground">{desc}</span></span>
                    </Label>
                  ))}
                </div>
              </FormRow>
              <div className="grid gap-3 sm:grid-cols-2">
                <FormRow label={t("rateLimit")}><Input type="number" min={0} value={form.rate_limit} onChange={(e) => setForm({ ...form, rate_limit: e.target.value })} /></FormRow>
                <FormRow label={t("expiresDays")}><Input type="number" min={0} value={form.expires_days} onChange={(e) => setForm({ ...form, expires_days: e.target.value })} /></FormRow>
              </div>
              <FormRow label={t("allowedIps")} hint={t("allowedIpsHint")}><Input value={form.allowed_ips} onChange={(e) => setForm({ ...form, allowed_ips: e.target.value })} /></FormRow>
              <FormRow label={t("webhookUrl")}><Input value={form.webhook_url} onChange={(e) => setForm({ ...form, webhook_url: e.target.value })} placeholder="https://…" /></FormRow>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setForm(null)}>{t("cancel")}</Button>
            <Button disabled={!form?.name.trim() || create.isPending} onClick={() => create.mutate(undefined, { onSuccess: (k) => { setForm(null); setCreated(k); } })}>{t("save")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!created} onOpenChange={(v) => !v && setCreated(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{created?.name}</DialogTitle>
            <DialogDescription className="text-warning">{t("keyOnce")}</DialogDescription>
          </DialogHeader>
          {created?.key && (
            <div className="flex items-center gap-2"><code className="flex-1 break-all rounded-lg bg-muted px-3 py-2 text-xs">{created.key}</code><CopyButton text={created.key} size="icon" /></div>
          )}
          {created?.webhook_secret && (
            <FormRow label={t("webhookSecret")}>
              <div className="flex items-center gap-2"><code className="flex-1 break-all rounded-lg bg-muted px-3 py-2 text-xs">{created.webhook_secret}</code><CopyButton text={created.webhook_secret} size="icon" /></div>
            </FormRow>
          )}
          <DialogFooter><Button onClick={() => setCreated(null)}>{t("done")}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog open={!!revoke} onOpenChange={(v) => !v && setRevoke(null)} title={`${t("revoke")}: ${revoke?.name}`} description={t("areYouSure")}
        destructive onConfirm={() => revoke && doRevoke.mutate(revoke.id, { onSuccess: () => setRevoke(null) })} />
      <Deliveries apiKey={hooks} onClose={() => setHooks(null)} />
    </Page>
  );
}

function Deliveries({ apiKey, onClose }: { apiKey: ApiKeyRow | null; onClose: () => void }) {
  const t = useQt();
  const q = useQr<Delivery[]>(["deliveries", apiKey?.id], `api-keys/${apiKey?.id}/deliveries`, undefined, { enabled: !!apiKey, refetchInterval: 5000 });
  const test = useQrAction(async () => qrApi.post(`api-keys/${apiKey!.id}/test-webhook`), t("testSent"));
  return (
    <Dialog open={!!apiKey} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("deliveries")}</DialogTitle>
          <DialogDescription className="break-all">{apiKey?.webhook_url}</DialogDescription>
        </DialogHeader>
        <div className="max-h-80 overflow-y-auto text-sm">
          {(q.data ?? []).map((d) => (
            <div key={d.id} className="flex items-center gap-3 border-b py-1.5">
              <span className="font-mono text-xs">{d.event}</span>
              <span className="text-xs text-muted-foreground">{fmtDate(d.created_at)}</span>
              <span className="ml-auto text-xs">{d.status_code ?? "—"} · {d.attempts}×</span>
              <Badge variant="outline" className={d.status === "ok" ? "text-success" : d.status === "failed" ? "text-destructive" : ""}>{d.status}</Badge>
            </div>
          ))}
          {!q.data?.length && <p className="py-4 text-center text-muted-foreground">{t("emptyHint")}</p>}
        </div>
        <DialogFooter><Button variant="outline" onClick={() => test.mutate()}><Send className="size-4" />{t("testWebhook")}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
