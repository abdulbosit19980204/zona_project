// Inventarizatsiya moduli: t("...") / tr("...") matnlarining ruscha tarjimasi borligini tekshiradi.
// Ishga tushirish: node scripts/inv-i18n-check.mjs   (yo'q tarjimalar ro'yxati chiqadi, bo'lsa — kod 1)
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const dir = fileURLToPath(new URL("../src/components/inventory/", import.meta.url));
const ruSrc = readFileSync(join(dir, "i18n-ru.ts"), "utf8");
const unq = (s) => JSON.parse(`"${s}"`);
const keys = new Set();
for (const m of ruSrc.matchAll(/^\s*"((?:[^"\\]|\\.)*)":/gm)) keys.add(unq(m[1]));

const used = new Map();
for (const f of readdirSync(dir).filter((x) => x.endsWith(".tsx") || x.endsWith(".ts"))) {
  if (f.startsWith("i18n")) continue;
  const src = readFileSync(join(dir, f), "utf8");
  for (const m of src.matchAll(/\b(?:t|tr)\(\s*"((?:[^"\\]|\\.)*)"/g)) used.set(unq(m[1]), f);
  // xaritalardagi matnlar (sarlavhalar, tavsiflar, holat nomlari)
  for (const m of src.matchAll(/\b(?:label|title|description): "((?:[^"\\]|\\.)*)"/g)) used.set(unq(m[1]), f);
  for (const block of src.matchAll(/const (?:[A-Z_]+_LABEL|LEVEL_HINT|TABS)\b[^=]*=\s*([[{][\s\S]*?[\]}]);/g)) {
    for (const m of block[1].matchAll(/"((?:[^"\\]|\\.)*)"/g)) {
      if (/[A-Za-z]/.test(m[1]) && m[1].length > 2 && !/^[a-z_]+$/.test(m[1])) used.set(unq(m[1]), f);
    }
  }
}
const missing = [...used].filter(([k]) => !keys.has(k) && /[A-Za-z]/.test(k));
if (missing.length) {
  console.log(`Tarjimasi yo'q: ${missing.length}`);
  for (const [k, f] of missing) console.log(`  ${JSON.stringify(k)}: "",  // ${f}`);
  process.exit(1);
}
console.log(`OK: ${used.size} ta matn, hammasi tarjima qilingan`);
