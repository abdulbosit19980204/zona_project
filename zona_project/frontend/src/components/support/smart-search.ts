/**
 * Smart qidiruv: kirill/lotin farqi, apostroflar (oʻ, gʻ, ' ’ `), katta-kichik harf va so'z tartibi ahamiyatsiz;
 * har bir so'z boshidan yoki o'rtasidan topiladi, 5+ harfli so'zda bitta harf xatosi kechiriladi.
 */
const CYR: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", ғ: "g", д: "d", е: "e", ё: "yo", ж: "j", з: "z", и: "i", й: "y", к: "k", қ: "q",
  л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ў: "o", ф: "f", х: "x", ҳ: "h", ц: "s",
  ч: "ch", ш: "sh", щ: "sh", ъ: "", ы: "i", ь: "", э: "e", ю: "yu", я: "ya",
};
const LAT: Record<string, string> = { ş: "sh", ç: "ch", ğ: "g", ḡ: "g", ō: "o", ö: "o", ü: "u", ı: "i", ñ: "ng" };

export function normalize(s: string): string {
  let out = "";
  for (const ch of (s || "").toLowerCase()) out += CYR[ch] ?? LAT[ch] ?? ch;
  return out.replace(/[ʻʼ’‘'`´]/g, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}

function nearlyEqual(a: string, b: string) {
  // bitta harf qo'shilgan / tushgan / almashgan
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0, j = 0, diff = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; continue; }
    if (++diff > 1) return false;
    if (a.length > b.length) i++;
    else if (b.length > a.length) j++;
    else { i++; j++; }
  }
  return diff + (a.length - i) + (b.length - j) <= 1;
}

/** 0 — mos emas; kattaroq — yaxshiroq mos. `haystack` oldindan normalize() qilingan bo'lishi mumkin. */
export function smartScore(haystack: string, query: string, pre = false): number {
  const q = normalize(query);
  if (!q) return 1;
  const h = pre ? haystack : normalize(haystack);
  const tokens = h.split(" ");
  let score = 0;
  for (const w of q.split(" ")) {
    if (tokens.some((t) => t.startsWith(w))) score += 3;
    else if (h.includes(w)) score += 2;
    else if (w.length >= 5 && tokens.some((t) => nearlyEqual(t.slice(0, w.length + 1), w) || nearlyEqual(t.slice(0, w.length), w))) score += 1;
    else return 0;
  }
  if (h.startsWith(q)) score += 3;
  return score;
}

/** Ro'yxatni so'rov bo'yicha saralab filtrlash (eng mos birinchi). */
export function smartFilter<T>(items: T[], query: string, text: (x: T) => string): T[] {
  if (!normalize(query)) return items;
  return items.map((x) => [x, smartScore(text(x), query)] as const).filter(([, s]) => s > 0)
    .sort((a, b) => b[1] - a[1]).map(([x]) => x);
}
