/** Kim so'raydi: bazada o'zbekcha nom saqlanadi, interfeysda tarjimasi ko'rsatiladi. */
export const ASKERS = ["Agent", "Supervayzer", "Operator", "Ofis xodimi", "Hamma"] as const;

const KEYS: Record<string, string> = {
  Agent: "agent", Supervayzer: "supervisor", Operator: "operator", "Ofis xodimi": "office", Hamma: "anyone",
};

export const askerKey = (asker: string) => KEYS[asker] ?? "other";
