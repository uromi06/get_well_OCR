"""Dose history of one medication across the pages it was found on.

Used by the 💊 Medikation tab ("Dosisverlauf je Wirkstoff"): for a drug from the reconciliation
table, take the pages in its "Quelle (Seiten)" column, list what each page says about the drug
(strength, dosing, status), sort by document date and mark what changed from one mention to the next.

Works on a saved case_result.json, no new OCR needed.
"""
import re

from .parse import DOSING, STRENGTH

STATUSES = ("active", "new", "paused", "stopped")
FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75}


def page_numbers(sources) -> list[int]:
    """'2, 3, 9' or [2, 3, 9] -> [2, 3, 9]"""
    if isinstance(sources, (list, tuple)):
        return [int(s) for s in sources]
    return [int(s) for s in re.findall(r"\d+", str(sources or ""))]


def parse_mention(label: str, name: str) -> dict:
    """A medication fact label from a page ('Apixaban 2,5 mg 1-0-1-0 new') -> its parts."""
    rest = label[len(name):].strip() if label.lower().startswith(name.lower()) else label
    status = None
    if rest.split() and rest.split()[-1] in STATUSES:
        status = rest.split()[-1]
        rest = rest.rsplit(" ", 1)[0] if " " in rest else ""
    s, d = STRENGTH.search(rest), DOSING.search(rest)
    dosing = re.sub(r"\s+", "", d.group(0)) if d else ("bei Bedarf" if "bei Bedarf" in rest else None)
    return {"strength": f"{s.group(1)} {s.group(2)}" if s else None, "dosing": dosing, "status": status}


def _number(x: str) -> float:
    return FRACTIONS.get(x) or float(x.replace(",", "."))


def daily_dose(strength: str | None, dosing: str | None) -> tuple[float, str] | None:
    """'2,5 mg' x '1-0-1-0' -> (5.0, 'mg'). None if it can't be worked out (e.g. 'bei Bedarf')."""
    if not strength or not dosing or not DOSING.fullmatch(dosing):
        return None
    s = STRENGTH.search(strength)
    if not s:
        return None
    unit = s.group(2).replace("ug", "µg").replace("mcg", "µg")
    return round(float(s.group(1).replace(",", ".")) * sum(_number(x) for x in dosing.split("-")), 3), unit


def _scheme_with_unit(text: str, dosing: str | None) -> tuple[float, str] | None:
    """'... Prograf 3-0-3 mg ...' -> (6.0, 'mg') when that scheme is the mention's dosing."""
    if not dosing or not DOSING.fullmatch(dosing):
        return None
    for m in DOSING.finditer(text):
        unit = re.match(r"\s*(mg|µg|g)\b", text[m.end():])
        if unit and re.sub(r"\s+", "", m.group(0)) == dosing:
            return round(sum(_number(x) for x in dosing.split("-")), 3), unit.group(1)
    return None


def _fmt(amount: float) -> str:
    return f"{amount:g}".replace(".", ",")


def dose_history(result: dict, name: str, pages: list[int] | None = None) -> list[dict]:
    """Every mention of `name` on the given pages (all pages if None), oldest document first.

    Each row: page, document, date, strength, dosing, daily dose, status, change vs. the previous
    concrete mention, and the text on the page it was read from.
    """
    docs = {d["doc_id"]: d for d in result.get("documents", [])}
    wanted = set(pages) if pages else None
    rows = []
    for p in result["pages"]:
        if wanted is not None and p["page"] not in wanted:
            continue
        doc = docs.get(p.get("doc_id"), {})
        for f in p.get("facts", []):
            if f.get("kind") != "meds" or not f.get("label", "").lower().startswith(name.lower()):
                continue
            m = parse_mention(f["label"], name)
            dd = daily_dose(m["strength"], m["dosing"])
            amounts = _scheme_with_unit(f.get("source_text") or "", m["dosing"])
            if amounts:                       # "Prograf 3-0-3 mg": the scheme itself is in mg, not tablets
                dd, m["strength"] = amounts, None
            rows.append({"page": p["page"], "document": doc.get("title") or p.get("doc_type") or "",
                         "date": doc.get("date"), **m,
                         "daily": dd, "daily_text": f"{_fmt(dd[0])} {dd[1]}/Tag" if dd else "",
                         "source_text": f.get("source_text") or ""})
    # oldest first; undated notes last (the merge treats them as newest information)
    rows.sort(key=lambda r: (r["date"] or "9999", r["page"]))

    previous = None
    for r in rows:
        if r["status"] in ("stopped", "paused"):
            r["change"] = "abgesetzt" if r["status"] == "stopped" else "pausiert"
            continue
        if not (r["strength"] or r["dosing"]):
            r["change"] = "nur erwähnt"
            continue
        if previous is None:
            r["change"] = "erste Angabe"
        elif r["daily"] and previous["daily"] and r["daily"][1] == previous["daily"][1]:
            a, b = previous["daily"][0], r["daily"][0]
            r["change"] = ("↑ erhöht" if b > a else "↓ reduziert" if b < a else "= unverändert") + \
                          (f" ({_fmt(a)} → {_fmt(b)} {r['daily'][1]}/Tag)" if a != b else "")
        else:   # compare only what both mentions state (a page with just the strength is no change)
            both = [k for k in ("strength", "dosing") if r[k] and previous[k]]
            norm = lambda v: re.sub(r"\s+", "", v).replace(".", ",").lower()
            diff = [k for k in both if norm(r[k]) != norm(previous[k])]
            label = {"strength": "Stärke", "dosing": "Dosierung"}
            r["change"] = ("geändert (" + ", ".join(f"{label[k]} {previous[k]} → {r[k]}" for k in diff) + ")"
                           if diff else "= unverändert")
        previous = r
    return rows
