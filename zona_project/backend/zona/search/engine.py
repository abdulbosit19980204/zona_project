"""Ko'p tilli, xatoga chidamli qidiruv va "kimga yo'naltirish" reytingi.

Hujjatlar: vazifalar, jarayonlar, xodimlar (lavozim, savol turi, nima qiladi), aralash holatlar, bo'limlar.
Har bir so'rov so'zi lug'atdagi so'zlar bilan solishtiriladi: aniq (1.0), prefiks (0.85),
k/q, x/h farqi (0.95), trigram o'xshashligi (imlo xatolari). Natija IDF bilan og'irlanadi va
mas'ul xodimlar bo'yicha yig'iladi.
"""
import math
import threading
from collections import defaultdict

from django.db.models import Count, Max

from .. import translation
from ..models import Department, EdgeCase, Member, Process, ProcessRole, Synonym, Task, TaskFallback
from .normalize import tokens, trigrams, word_spans
from .synonyms import BUILTIN

_lock = threading.Lock()
_cache = {"version": None, "index": None}


def _loose(w):
    return w.replace("q", "k").replace("x", "h").replace("w", "v")


class Index:
    def __init__(self):
        self.members = {m.id: m for m in Member.objects.all()}
        self.processes = {p.id: p for p in Process.objects.select_related("system")}
        self.tasks = list(Task.objects.select_related("process__system").prefetch_related("fallbacks"))
        self.edges = list(EdgeCase.objects.all())
        self.departments = list(Department.objects.all())
        self.roles = defaultdict(list)  # process -> [(member, role)]
        for r in ProcessRole.objects.all():
            self.roles[r.process_id].append((r.member_id, r.role))
        self.docs = []
        add = self._add
        v = translation.variants  # asl matn + AI tarjimalari: istalgan tilda qidirish mumkin
        for t in self.tasks:
            p = t.process
            add("task", t.id, [(v(t, "title"), 1.0), (v(p, "name") if p else "", 0.5),
                                (p.system.name if p and p.system else "", 0.35), (v(t, "note"), 0.4)])
        for p in self.processes.values():
            add("process", p.id, [(v(p, "name"), 1.0), (v(p, "description"), 0.5), (p.system.name if p.system else "", 0.4)])
        for m in self.members.values():
            add("member", m.id, [(v(m, "name"), 1.0), (v(m, "role"), 0.75), (v(m, "trigger"), 0.8), (v(m, "does"), 0.55)])
        for e in self.edges:
            add("edge", e.id, [(v(e, "situation"), 1.0), (v(e, "then_text"), 0.3)])
        for d in self.departments:
            add("department", d.id, [(v(d, "name"), 1.0), (v(d, "description"), 0.4)])

        self.df = defaultdict(int)
        for doc in self.docs:
            for stem in set().union(*[f for f, _ in doc["fields"]]):
                self.df[stem] += 1
        self.vocab = {s: (trigrams(s), _loose(s)) for s in self.df}
        self.groups = [self._phrases(g) for g in BUILTIN + list(Synonym.objects.values_list("words", flat=True))]

    def _add(self, kind, pk, fields):
        parsed = [(set(tokens(text)), w) for text, w in fields if text]
        if any(f for f, _ in parsed):
            self.docs.append({"kind": kind, "id": pk, "fields": parsed})

    @staticmethod
    def _phrases(group):
        out = []
        for phrase in group.split(","):
            stems = tuple(tokens(phrase))
            if stems:
                out.append(stems)
        return out

    # ---------------------------------------------------------- moslashtirish
    def sim(self, a, b, tri_a=None):
        if a == b:
            return 1.0
        short = min(len(a), len(b))
        if short >= 4 and (a.startswith(b) or b.startswith(a)):
            return 0.85
        tb, lb = self.vocab[b]
        if _loose(a) == lb:
            return 0.95
        if abs(len(a) - len(b)) > 3 or short < 3:
            return 0.0
        ta = tri_a or trigrams(a)
        j = len(ta & tb) / len(ta | tb)
        return round(j * 0.9, 3) if j >= 0.45 else 0.0

    def matches(self, term):
        tri = trigrams(term)
        found = {}
        for v in self.vocab:
            s = self.sim(term, v, tri)
            if s >= 0.5:
                found[v] = s
        return found

    def expand(self, stems):
        """Lug'at guruhlari: so'rovda guruhdagi ibora bo'lsa, guruhning qolgan so'zlarini qo'shadi."""
        have = set(stems)
        extra = {}
        for group in self.groups:
            hit = any(all(any(s == h or (len(s) >= 4 and (h.startswith(s) or s.startswith(h))) for h in have)
                          for s in phrase) for phrase in group)
            if not hit:
                continue
            for phrase in group:
                for s in phrase:
                    if s not in have and len(s) >= 2:
                        extra[s] = 0.75
        return extra

    # ---------------------------------------------------------- qidiruv
    def search(self, query, limit=12, lang=None):
        base = list(dict.fromkeys(tokens(query)))
        if not base:
            return None
        expanded = self.expand(base)
        terms = [(t, 1.0) for t in base] + [(t, w) for t, w in expanded.items() if t in self.vocab or len(t) >= 4]
        n = max(len(self.docs), 1)
        prepared, mass = [], 0.0
        for t, w in terms:
            m = self.matches(t)
            if not m:
                if w == 1.0:
                    mass += math.log(1 + n)  # topilmagan asl so'z qamrovni pasaytiradi
                continue
            dfm = min(n, sum(self.df[v] * s for v, s in m.items()))
            idf = math.log(1 + n / (1 + dfm))
            prepared.append((t, w, idf, m))
            if w == 1.0:
                mass += idf
        mass = mass or 1.0
        base_set = set(base)

        results = []
        for doc in self.docs:
            score, matched = 0.0, set()
            for t, w, idf, m in prepared:
                best = 0.0
                for field, fw in doc["fields"]:
                    if len(m) < len(field):
                        local = max((s for v, s in m.items() if v in field), default=0.0)
                    else:
                        local = max((m.get(s, 0.0) for s in field), default=0.0)
                    best = max(best, local * fw)
                if best:
                    score += w * idf * best
                    matched.add(t)
            if score:
                # asl so'zlarning ko'pini qamragan hujjat ustun: "Yangi klient qo'shish" > "Yangi aksiya ... qo'shish"
                frac = len(matched & base_set) / len(base_set)
                score *= 0.35 + 0.65 * frac
                results.append((score, score / mass, doc, matched))
        results.sort(key=lambda r: -r[0])
        return self._shape(query, base, expanded, results, prepared, limit, lang)

    def _shape(self, query, base, expanded, results, prepared, limit, lang=None):
        by_kind = defaultdict(list)
        for score, cov, doc, _ in results:
            if cov >= 0.18 or len(by_kind[doc["kind"]]) < 3:
                by_kind[doc["kind"]].append((score, cov, doc["id"]))

        people = defaultdict(list)  # member -> [(ball, manba)]
        tasks_of = defaultdict(list)
        task_map = {t.id: t for t in self.tasks}
        for score, cov, tid in by_kind["task"][:40]:
            t = task_map[tid]
            if t.owner_id:
                people[t.owner_id].append((score, "task"))
                tasks_of[t.owner_id].append(tid)
            # navbatdagi mas'ullar: asosiy mas'uldan keyin, pastroq ball bilan
            for n, f in enumerate(t.fallbacks.all()):
                people[f.member_id].append((score * (0.45 if n == 0 else 0.3), "fallback"))
                tasks_of[f.member_id].append(tid)
        for score, cov, pid in by_kind["process"][:15]:
            for mid, role in self.roles.get(pid, []):
                people[mid].append((score * (0.8 if role == "owner" else 0.35), "process"))
        for score, cov, mid in by_kind["member"][:10]:
            people[mid].append((score, "member"))
        edge_map = {e.id: e for e in self.edges}
        for score, cov, eid in by_kind["edge"][:6]:
            e = edge_map[eid]
            if e.first_owner_id:
                people[e.first_owner_id].append((score * 1.1, "edge"))

        ranked = []
        for mid, parts in people.items():
            if mid not in self.members:
                continue
            vals = sorted((p for p, _ in parts), reverse=True)
            total = vals[0] + 0.25 * sum(vals[1:2]) + 0.1 * sum(vals[2:3])
            ranked.append((total, mid, sorted({src for _, src in parts})))
        ranked.sort(key=lambda r: -r[0])
        best_cov = max((cov for _, cov, _, _ in results[:5]), default=0)
        out_people = []
        for i, (total, mid, via) in enumerate(ranked[:6]):
            nxt = ranked[i + 1][0] if i + 1 < len(ranked) else 0
            share = total / (total + nxt) if total else 0
            conf = (0.55 * share + 0.45 * min(1.0, best_cov)) if i == 0 else 0.6 * total / (ranked[0][0] or 1) * min(1.0, best_cov)
            out_people.append({"member": mid, "score": round(total, 3), "confidence": round(100 * conf),
                               "tasks": tasks_of[mid][:5], "via": via})

        def hl(text):
            terms = {t for t, *_ in prepared}
            spans = []
            for s, e, st in word_spans(text):
                if st in self.vocab and any(self.sim(t, st) >= 0.6 for t in terms):
                    spans.append([s, e])
            return spans

        return {
            "query": query,
            "terms": base,
            "expanded": sorted(expanded),
            "people": out_people,
            # belgilash foydalanuvchi ko'radigan (tanlangan tildagi) matn bo'yicha
            "tasks": [{"id": tid, "score": round(s, 3), "hl": hl(translation.current(task_map[tid], "title", lang))}
                      for s, _, tid in by_kind["task"][:limit]],
            "processes": [{"id": i, "score": round(s, 3), "hl": hl(translation.current(self.processes[i], "name", lang))}
                          for s, _, i in by_kind["process"][:6]],
            "members": [{"id": i, "score": round(s, 3)} for s, _, i in by_kind["member"][:5]],
            "edge_cases": [{"id": i, "score": round(s, 3)} for s, _, i in by_kind["edge"][:4]],
            "departments": [{"id": i, "score": round(s, 3)} for s, _, i in by_kind["department"][:3]],
        }


def _version():
    parts = []
    for model, field in ((Task, "updated_at"), (Member, "updated_at"), (Process, "updated_at"),
                         (EdgeCase, "id"), (Synonym, "updated_at"), (Department, "id"), (ProcessRole, "id"),
                         (TaskFallback, "id")):
        agg = model.objects.aggregate(c=Count("id"), m=Max(field))
        parts.append((agg["c"], str(agg["m"])))
    parts.append(translation.version())  # fonda tarjima qo'shilsa, indeks yangilanadi
    return tuple(parts)


def get_index():
    version = _version()
    with _lock:
        if _cache["version"] != version:
            _cache["index"] = Index()
            _cache["version"] = version
        return _cache["index"]


def search(query, limit=12, lang=None):
    return get_index().search(query, limit, lang) or {
        "query": query, "terms": [], "expanded": [], "people": [], "tasks": [], "processes": [],
        "members": [], "edge_cases": [], "departments": []}


def debug(query):
    idx = get_index()
    base = list(dict.fromkeys(tokens(query)))
    return {"query": query, "terms": base, "expanded": sorted(idx.expand(base)),
            "matches": {t: sorted(idx.matches(t).items(), key=lambda kv: -kv[1])[:8] for t in base}}
