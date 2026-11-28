"""AI'siz semantik qidiruv (KOORDINATSIYA 0j): savol -> bilim bazasidagi eng yaqin yozuv, kichik ko'p tilli embedding
model bilan, serverning o'zida (GPU'siz, internet/AI limitiga bog'liq emas).

Model: Xenova/multilingual-e5-small (XLM-R asosli, 100+ til — o'zbek lotin/kirill, rus aralash matn), kvantlangan
ONNX (~118 MB), onnxruntime CPU + tokenizers; 2 ta oqim (bio-lab bilan bir server). Javob — tayyor yozuv matni
(generativ AI shart emas). Indeks: tasdiqlangan yozuvlarning sarlavhasi, savol ko'rinishlari va agent «hal bo'ldi»
degan bot javoblarining savollari; vektorlar diskda keshlanadi (o'zgargan matnlargina qayta hisoblanadi).

Kutubxona yoki model fayli bo'lmasa — `available()` False, bot avvalgidek ishlaydi. Testlarda `set_embedder()` bilan
soxta model beriladi (numpy'siz ham ishlaydi).
"""
import hashlib
import logging
import os
import re
import threading
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

REPO = "Xenova/multilingual-e5-small"
FILES = {"model.onnx": "onnx/model_quantized.onnx", "tokenizer.json": "tokenizer.json"}
MAX_LEN = 128
THREADS = 2
PREFIX = "query: "  # e5: ikkala tomon ham «query:» — simmetrik o'xshashlik
# 1-o'rindagi yozuv 2-o'rindagidan kamida shuncha yuqori bo'lsin (e5 o'xshashliklari zich: aloqasiz matnlar ham 0.90+;
# ikki yozuv orasida ikkilanilsa — javob berilmaydi). Prod sozlashi (2026-11-28, 374 ibora): 0.94 + 0.02 -> aniqlik 99%,
# standarti yo'q savolga xato javob 3%.
MARGIN = 0.02

_lock = threading.Lock()
_force = threading.local()


class forced:
    """Sozlash/baholashda: semantik bosqich sozlamada yoqilmagan bo'lsa ham shu chegara (%) va farq bilan ishlaydi
    (shu oqimda). Bunda savolning o'z matni indeksda bo'lsa hisobga olinmaydi (holdout — o'zi bilan solishtirmaslik)."""

    def __init__(self, threshold, margin=None):
        self.th, self.margin = threshold, margin

    def __enter__(self):
        _force.th, _force.margin = self.th, self.margin
        return self

    def __exit__(self, *exc):
        _force.th = _force.margin = None
        return False


def forced_threshold():
    return getattr(_force, "th", None)


def forced_margin():
    m = getattr(_force, "margin", None)
    return MARGIN if m is None else m
_state = {"model": None, "override": None, "key": None, "rows": [], "mat": None, "vec_cache": {}}


def model_dir():
    base = os.environ.get("SUPPORT_SEMANTIC_DIR")
    if base:
        return Path(base)
    from .runner import media_dir
    return media_dir().parent / "models" / "multilingual-e5-small"


def set_embedder(fn):
    """Testlar uchun: fn(list[str]) -> list[list[float]] (normallashtirilgan). None — haqiqiy model."""
    with _lock:
        _state.update(override=fn, key=None, rows=[], mat=None, vec_cache={})


def _deps():
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
        return True
    except ImportError:
        return False


def available():
    if _state["override"] is not None:
        return True
    d = model_dir()
    return _deps() and all((d / f).exists() for f in FILES)


def download(progress=print):
    """Model fayllarini Hugging Face'dan yuklab oladi (bir marta). Qaytaradi: papka."""
    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name, path in FILES.items():
        dst = d / name
        if dst.exists() and dst.stat().st_size > 0:
            continue
        url = f"https://huggingface.co/{REPO}/resolve/main/{path}"
        tmp = dst.with_suffix(".part")
        req = urllib.request.Request(url, headers={"User-Agent": "foydali-support/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:  # noqa: S310 — aniq HTTPS manzil
            while chunk := r.read(1 << 20):
                f.write(chunk)
        tmp.replace(dst)
        progress(f"{name}: {dst.stat().st_size // 1024} KB")
    return d


class _Model:
    def __init__(self, d):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        self.tok.enable_truncation(MAX_LEN)
        self.tok.enable_padding()
        so = ort.SessionOptions()
        so.intra_op_num_threads = THREADS
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(str(d / "model.onnx"), so, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}

    def embed(self, texts):
        import numpy as np
        out = []
        for i in range(0, len(texts), 32):
            enc = self.tok.encode_batch([PREFIX + t for t in texts[i:i + 32]])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            hidden = self.sess.run(None, feed)[0]  # (n, len, dim)
            m = mask[..., None].astype(np.float32)
            v = (hidden * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
            v /= np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-9, None)
            out.extend(v.astype(np.float32))
        return out


def _embed(texts):
    if not texts:
        return []
    if _state["override"] is not None:
        return [list(map(float, v)) for v in _state["override"](texts)]
    if _state["model"] is None:
        _state["model"] = _Model(model_dir())
    return _state["model"].embed(texts)


_NOISE = re.compile(r"📍[^\n]*|https?://\S+|@\w+")


def clean(text):
    """Savol matni: salomlashuv, @murojaat, havola va lokatsiya qatorisiz (mijoz kodi va nomi qoladi — model o'zi
    e'tiborsiz qoldiradi, olib tashlash ma'noni buzishi mumkin)."""
    from .tasks import strip_greeting
    t = _NOISE.sub(" ", text or "")
    t = strip_greeting(" ".join(t.split()))
    return t[:300]


def _key():
    from django.db.models import Count, Max

    from .models import Entry, Message
    a = Entry.objects.filter(status=Entry.APPROVED).aggregate(n=Count("id"), u=Max("updated_at"))
    b = Message.objects.filter(kind=Message.QUESTION, entry__isnull=False, resolution=Message.YES).aggregate(n=Count("id"))
    return (a["n"], str(a["u"]), b["n"])


def _rows():
    """[(yozuv id, matn)] — tasdiqlangan yozuvlar va agent tasdiqlagan bot javoblarining savollari."""
    from .engine import learnable_question
    from .models import Entry, Message
    rows, seen = [], set()

    def add(eid, text):
        t = clean(text)
        k = (eid, t.lower())
        if t and k not in seen and (len(t) >= 6):
            seen.add(k)
            rows.append((eid, t))
    for e in Entry.objects.filter(status=Entry.APPROVED).only("id", "title", "questions", "kind"):
        add(e.pk, e.title)
        for q in (e.questions or [])[:80]:
            add(e.pk, q)
    for eid, text in (Message.objects.filter(kind=Message.QUESTION, entry__status=Entry.APPROVED, resolution=Message.YES)
                      .exclude(review__in=["wrong", "check"]).order_by("-id").values_list("entry_id", "text")[:3000]):
        if learnable_question(text or ""):
            add(eid, text)
    return rows


def _vec_cache_path():
    return model_dir() / "vectors.npz"


def refresh_async():
    """Jonli botda: indeksni fonda yangilash (javob kutib qolmasin). Bir vaqtda bitta."""
    if _state.get("building"):
        return
    _state["building"] = True

    def run():
        from django.db import close_old_connections
        close_old_connections()
        try:
            ensure_index()
        except Exception:  # noqa: BLE001
            log.exception("semantic: indeks qurilmadi")
        finally:
            _state["building"] = False
            close_old_connections()
    threading.Thread(target=run, name="semantic-index", daemon=True).start()


def ensure_index():
    """Indeks yangi bo'lsa — hech narsa; yozuvlar o'zgargan bo'lsa — faqat yangi matnlar hisoblanadi."""
    key = _key()
    if _state["key"] == key and _state["rows"]:
        return _state["rows"]
    with _lock:
        if _state["key"] == key and _state["rows"]:
            return _state["rows"]
        rows = _rows()
        cache = _state["vec_cache"]
        real = _state["override"] is None
        if real and not cache and _vec_cache_path().exists():
            try:
                import numpy as np
                z = np.load(_vec_cache_path(), allow_pickle=False)
                cache.update(zip(z["h"].tolist(), z["v"]))
            except Exception:  # noqa: BLE001 — kesh buzilgan bo'lsa qayta hisoblanadi
                cache.clear()
        h = [hashlib.sha1(t.encode()).hexdigest() for _e, t in rows]
        need = [(hh, t) for hh, (_e, t) in zip(h, rows) if hh not in cache]
        if need:
            for (hh, _t), v in zip(need, _embed([t for _h, t in need])):
                cache[hh] = v
            if real:
                try:
                    import numpy as np
                    keys = [x for x in h if x in cache]
                    np.savez(_vec_cache_path(), h=np.array(keys), v=np.array([cache[x] for x in keys], dtype=np.float32))
                except Exception:  # noqa: BLE001
                    log.exception("semantic: vektor keshi saqlanmadi")
        vecs = [cache[x] for x in h]
        try:
            import numpy as np
            mat = np.array(vecs, dtype=np.float32) if vecs else None
        except ImportError:
            mat = vecs
        _state.update(key=key, rows=rows, mat=mat)
        return rows


def _scores(q):
    mat = _state["mat"]
    if mat is None:
        return []
    try:
        import numpy as np
        return (np.asarray(mat) @ np.asarray(q, dtype=np.float32)).tolist()
    except ImportError:
        return [sum(a * b for a, b in zip(row, q)) for row in mat]


def search(text, k=3, exclude=None, block=True, exclude_entries=None):
    """-> [(yozuv id, o'xshashlik 0..1)] eng yaqinlari (har yozuvdan eng yuqori qatori). exclude — shu matnli
    qatorlar hisobga olinmaydi (sozlashda: sinov iborasi indeksda bo'lsa, o'zi bilan solishtirmaslik uchun);
    exclude_entries — shu yozuvlar umuman yo'qdek (sozlashda: «standarti yo'q savol»ni sinash).
    block=False (jonli bot): indeks tayyor bo'lmasa yoki eskirgan bo'lsa — fonda yangilanadi, hozircha bor indeks
    bilan (yo'q bo'lsa — bo'sh natija)."""
    t = clean(text)
    if not t:
        return []
    if block:
        rows = ensure_index()
    else:
        if _state["key"] != _key():
            refresh_async()
        rows = _state["rows"]
    if not rows:
        return []
    q = _embed([t])[0]
    best = {}
    ex = {x.lower() for x in (exclude or ())}
    skip = set(exclude_entries or ())
    for (eid, rt), s in zip(rows, _scores(q)):
        if (ex and rt.lower() in ex) or eid in skip:
            continue
        if s > best.get(eid, -1):
            best[eid] = s
    return sorted(best.items(), key=lambda x: -x[1])[:k]


# --------------------------------------------------------------- sozlash (chegara tanlash)
def labeled(limit=400):
    """Belgilangan to'plam: (ibora, to'g'ri yozuv id) — Claude standartga qo'shgan savollar (manbalari) va agent
    «hal bo'ldi» degan bot javoblari."""
    from .engine import learnable_question
    from .models import Entry, Message
    out, seen = [], set()
    for a in Entry.objects.filter(status=Entry.ARCHIVED, claude_target__status=Entry.APPROVED).only("sources",
                                                                                                    "claude_target_id"):
        for t in Message.objects.filter(pk__in=a.sources or [], kind=Message.QUESTION).values_list("text", flat=True):
            if learnable_question(t or "") and (t, a.claude_target_id) not in seen:
                seen.add((t, a.claude_target_id))
                out.append((t, a.claude_target_id))
    for t, eid in (Message.objects.filter(kind=Message.QUESTION, entry__status=Entry.APPROVED, resolution=Message.YES)
                   .exclude(review__in=["wrong", "check"]).order_by("-id").values_list("text", "entry_id")[:limit]):
        if learnable_question(t or "") and (t, eid) not in seen:
            seen.add((t, eid))
            out.append((t, eid))
    return out[:limit]


def decide_top(top, threshold, margin):
    """search(k=2) natijasidan: javob beriladigan yozuv (id, o'xshashlik, farq) yoki None. threshold — 0..1."""
    if not top or top[0][1] < threshold:
        return None
    gap = top[0][1] - (top[1][1] if len(top) > 1 else 0.0)
    if gap < margin:
        return None
    return top[0][0], top[0][1], gap


def tune(pairs=None, thresholds=None, margins=None):
    """Har (chegara, farq) uchun ikki sinov:
    - javobi bor savol: ibora o'z matnisiz (holdout) qidiriladi — qamrov (javob berildi / hammasi) va aniqlik
      (to'g'ri yozuv / javob berildi);
    - standarti yo'q savol: o'sha ibora uning to'g'ri yozuvi umuman yo'qdek qidiriladi — javob berilsa, bu xato
      (false_pos, %). mixed — ikkalasi teng aralashganda javoblarning to'g'ri ulushi (asosiy mezon, ≥90% kerak)."""
    pairs = pairs if pairs is not None else labeled()
    pos, neg = [], []
    for text, eid in pairs:
        ct = clean(text)
        pos.append((search(text, k=2, exclude=[ct]), eid))
        neg.append(search(text, k=2, exclude=[ct], exclude_entries=[eid]))
    rows = []
    for th in thresholds or [x / 100 for x in range(88, 98)]:
        for m in (margins if margins is not None else (0.0, 0.01, 0.02, 0.03)):
            ans = [d[0] == eid for d, eid in ((decide_top(t, th, m), eid) for t, eid in pos) if d is not None]
            fp = sum(1 for t in neg if decide_top(t, th, m) is not None)
            n = len(pairs)
            rows.append({"th": th, "margin": m, "answered": len(ans), "correct": sum(ans), "total": n,
                         "precision": round(100 * sum(ans) / len(ans)) if ans else None,
                         "coverage": round(100 * len(ans) / n) if n else 0,
                         "false_pos": round(100 * fp / n) if n else 0,
                         "mixed": round(100 * sum(ans) / (len(ans) + fp)) if (ans or fp) else None})
    return rows


def best(rows, min_mixed=90):
    """Aralash aniqlik ≥ min_mixed bo'lgan eng katta qamrovli (chegara, farq) — yoki None."""
    ok = [r for r in rows if (r["mixed"] or 0) >= min_mixed and r["answered"]]
    return max(ok, key=lambda r: (r["coverage"], r["mixed"], -r["th"])) if ok else None
