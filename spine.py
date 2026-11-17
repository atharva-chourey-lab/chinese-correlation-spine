#!/usr/bin/env python3
"""Chinese Correlation Spine — CLI.

Uses precisely dated Chinese records (translation colophons, catalogues,
pilgrim itineraries, dynastic annals) to constrain and correct Indian
historical chronology.

Method in one line: the Chinese event is exact; the Indian original is
that event minus a MEASURED lag — never zero. See README.md.

Commands:
  lookup <entity>                          anchors + derived constraints
  correct <entity> --traditional S E       intersect a traditional Indian
                                           date range with the Chinese
                                           constraints; report conflicts
  lag                                      empirical lag statistics
  panel [--out PATH]                       benchmark-ready anchor table
  add <file.json>                          append schema-validated anchors
  eras <era_name> [year_n]                 reign-era -> CE conversion

Stdlib only. Data: data/anchors.json, data/eras.json (edit via
data/build_data.py for the seed, or `add` for new records).
"""
import argparse
import csv
import json
import os
import statistics
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
ANCHORS_PATH = os.path.join(DATA_DIR, "anchors.json")
ERAS_PATH = os.path.join(DATA_DIR, "eras.json")
DEFAULT_PANEL_OUT = os.path.join(HERE, "exports", "panel.csv")

CONSTRAINT_TYPES = {"TAQ", "TPQ", "floruit", "synchronism"}
SOURCE_TYPES = {"colophon", "catalogue", "pilgrim", "annals", "inscription"}
ENTITY_TYPES = {"text", "author", "person", "event"}
FIRMNESS_LEVELS = {"firm", "probable", "contested"}
REQUIRED_FIELDS = {
    "id": str, "indian_entity": str, "entity_type": str,
    "chinese_source": str, "source_type": str, "event": str,
    "date_raw": str, "date_ce": list, "constraint_type": str,
    "lag": (list, type(None)), "firmness": str, "notes": str,
    "references": list,
}
LAG_MIN_SOLID = 5       # below this many solid cases, no distribution
LAG_PROVISIONAL_N = 8   # below this, a computed distribution is provisional


# --------------------------------------------------------------------- util
def fold(s):
    """Lowercase + strip diacritics, so 'bhartrihari' matches 'Bhartrihari'
    with diacritics (Bhartrhari) and 'nagarjuna' matches 'Nagarjuna'."""
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def fmt_year(y):
    return f"{-y} BCE" if y < 0 else f"{y} CE"


def fmt_range(r):
    return f"[{fmt_year(r[0])} .. {fmt_year(r[1])}]"


def load_anchors(path=ANCHORS_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["anchors"]


def load_eras(path=ERAS_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["eras"]


def find_anchors(query, anchors=None):
    """Anchors whose entity name, aliases or id contain the query
    (diacritic-insensitive substring match)."""
    if anchors is None:
        anchors = load_anchors()
    q = fold(query).strip()
    hits = []
    for r in anchors:
        fields = [r["indian_entity"], r["id"]] + list(r.get("aliases", []))
        if any(q in fold(f) for f in fields):
            hits.append(r)
    return hits


# ------------------------------------------------------------- era converter
def convert_era(era_name, year_n=None, eras=None):
    """All (dynasty, era) matches for era_name. If year_n is given, each
    match carries the converted CE year and an in-range flag. An era name
    borne by several dynasties returns several matches — ambiguity is
    surfaced, never silently resolved."""
    if eras is None:
        eras = load_eras()
    q = fold(era_name).strip()
    matches = [e for e in eras if fold(e["era"]) == q]
    out = []
    for e in matches:
        item = {"era": e["era"], "dynasty": e["dynasty"],
                "start": e["start"], "end": e["end"]}
        if year_n is not None:
            item["year_n"] = year_n
            item["ce"] = e["start"] + year_n - 1
            item["in_range"] = e["start"] <= item["ce"] <= e["end"]
        out.append(item)
    return out


# ---------------------------------------------------------------- lag model
def lag_cases(anchors=None):
    """(solid, excluded) lag-bearing records. Solid = lag present AND
    lag_solid flag set (composition window independently anchored)."""
    if anchors is None:
        anchors = load_anchors()
    solid, excluded = [], []
    for r in anchors:
        if r.get("lag"):
            (solid if r.get("lag_solid") else excluded).append(r)
    return solid, excluded


def lag_stats(anchors=None):
    """Empirical lag statistics from SOLID cases only. Refuses to present
    a distribution when there are too few solid cases."""
    solid, excluded = lag_cases(anchors)
    result = {
        "n_solid": len(solid),
        "cases": [{"id": r["id"], "entity": r["indian_entity"],
                   "lag": r["lag"],
                   "midpoint": (r["lag"][0] + r["lag"][1]) / 2.0,
                   "basis": r.get("lag_basis", "")} for r in solid],
        "excluded": [{"id": r["id"], "lag": r["lag"],
                      "basis": r.get("lag_basis", "")} for r in excluded],
        "status": None, "median_midpoint": None, "mean_midpoint": None,
        "overall_range": None,
    }
    if len(solid) < LAG_MIN_SOLID:
        result["status"] = "insufficient"
        return result
    mids = [c["midpoint"] for c in result["cases"]]
    result["median_midpoint"] = statistics.median(mids)
    result["mean_midpoint"] = statistics.mean(mids)
    result["overall_range"] = [min(r["lag"][0] for r in solid),
                               max(r["lag"][1] for r in solid)]
    result["status"] = ("provisional" if len(solid) < LAG_PROVISIONAL_N
                        else "usable")
    return result


# ------------------------------------------------------- derived constraints
def derive_constraints(records):
    """Hard bounds + attested windows + lag-adjusted windows for a set of
    anchor records constraining one entity."""
    taq_bounds = [r["date_ce"][1] for r in records
                  if r["constraint_type"] == "TAQ"]
    tpq_bounds = [r["date_ce"][0] for r in records
                  if r["constraint_type"] == "TPQ"]
    attested = [r for r in records
                if r["constraint_type"] in ("floruit", "synchronism")]
    stats = lag_stats()
    lag_windows = []
    for r in records:
        if r["constraint_type"] != "TAQ":
            continue
        taq = r["date_ce"][1]
        if r.get("lag"):
            lag_windows.append({
                "record": r["id"], "kind": "case-based",
                "window": [taq - r["lag"][1], taq - r["lag"][0]],
                "note": f"this record's own lag {r['lag']} "
                        f"({'solid' if r.get('lag_solid') else 'NOT solid'})",
            })
        if stats["status"] in ("provisional", "usable"):
            lag_windows.append({
                "record": r["id"], "kind": "empirical-distribution",
                "window": [taq - stats["overall_range"][1],
                           taq - int(stats["median_midpoint"])],
                "note": f"empirical lag range {stats['overall_range']}, "
                        f"median {stats['median_midpoint']:.0f} "
                        f"({stats['status']}, n={stats['n_solid']})",
            })
    return {
        "hard_taq": min(taq_bounds) if taq_bounds else None,
        "hard_tpq": max(tpq_bounds) if tpq_bounds else None,
        "attested": attested,
        "lag_windows": lag_windows,
        "lag_status": stats["status"],
    }


def correct(entity, start, end, anchors=None):
    """Intersect a traditional date range [start, end] for `entity` with
    every Chinese-derived constraint on it. Returns a dict with the
    verdict, the corrected interval (or None on hard conflict), and
    human-readable reasoning lines."""
    records = find_anchors(entity, anchors)
    lines, conflicts, soft = [], [], []
    lo, hi = start, end
    if not records:
        return {"entity": entity, "traditional": [start, end],
                "verdict": "no-data", "corrected": None,
                "lines": [f"No Chinese-dated anchors on file for "
                          f"'{entity}'. No correction possible — this is "
                          f"an absence of evidence, not evidence for the "
                          f"traditional date."]}
    for r in records:
        a, b = r["date_ce"]
        tag = f"[{r['id']}] {r['constraint_type']} {fmt_range(r['date_ce'])} ({r['firmness']})"
        if r["constraint_type"] == "TAQ":
            bound = b  # guaranteed: the text existed by the window's end
            if start > bound:
                conflicts.append(
                    f"{tag}: HARD CONFLICT — the traditional range starts "
                    f"{start - bound} years AFTER the Chinese record proves "
                    f"the entity existed ({r['event']}).")
            else:
                if end > bound:
                    lines.append(
                        f"{tag}: traditional end {fmt_year(end)} cut to "
                        f"{fmt_year(bound)} — the entity demonstrably "
                        f"existed by then ({r['chinese_source']}).")
                    hi = min(hi, bound)
                else:
                    lines.append(f"{tag}: satisfied (traditional range "
                                 f"already ends by {fmt_year(bound)}).")
        elif r["constraint_type"] == "TPQ":
            bound = a
            if end < bound:
                conflicts.append(
                    f"{tag}: HARD CONFLICT — the traditional range ends "
                    f"{bound - end} years BEFORE the earliest moment the "
                    f"Chinese record allows ({r['event']}).")
            else:
                if start < bound:
                    lines.append(f"{tag}: traditional start "
                                 f"{fmt_year(start)} raised to "
                                 f"{fmt_year(bound)}.")
                    lo = max(lo, bound)
                else:
                    lines.append(f"{tag}: satisfied.")
        else:  # floruit / synchronism: attested window must intersect
            if end < a:
                conflicts.append(
                    f"{tag}: HARD CONFLICT — the traditional range ends "
                    f"{a - end} years before the attested window opens. "
                    f"Chinese record: {r['event']}.")
            elif start > b:
                conflicts.append(
                    f"{tag}: HARD CONFLICT — the traditional range starts "
                    f"{start - b} years after the attested window closes. "
                    f"Chinese record: {r['event']}.")
            else:
                lines.append(f"{tag}: attested window intersects the "
                             f"traditional range — consistent.")
        # soft lag plausibility for translation TAQs
        if r["constraint_type"] == "TAQ" and r.get("lag"):
            stats = lag_stats()
            if stats["status"] in ("provisional", "usable"):
                implied = [b - end, b - start]  # lag if range were true
                if implied[1] < stats["overall_range"][0]:
                    soft.append(
                        f"[{r['id']}] SOFT WARNING — the traditional range "
                        f"implies a composition-to-translation lag of at "
                        f"most {implied[1]} years, shorter than every "
                        f"solid observed case (min "
                        f"{stats['overall_range'][0]}). Not impossible — "
                        f"the Lankavatara case is {stats['overall_range'][0]} "
                        f"— but it is at the fast edge of the distribution.")
    if conflicts:
        return {"entity": entity, "traditional": [start, end],
                "verdict": "conflict", "corrected": None,
                "lines": conflicts + lines + soft}
    if lo > hi:
        return {"entity": entity, "traditional": [start, end],
                "verdict": "conflict", "corrected": None,
                "lines": lines + soft +
                         ["The constraints jointly empty the interval."]}
    verdict = "corrected" if (lo, hi) != (start, end) else "agrees"
    return {"entity": entity, "traditional": [start, end],
            "verdict": verdict, "corrected": [lo, hi],
            "lines": lines + soft}


# ---------------------------------------------------------------- validation
def validate_record(r, existing_ids=()):
    """Schema validation for `add`. Returns a list of error strings."""
    errs = []
    if not isinstance(r, dict):
        return ["record is not a JSON object"]
    for field, types in REQUIRED_FIELDS.items():
        if field not in r:
            errs.append(f"missing field: {field}")
        elif not isinstance(r[field], types):
            errs.append(f"field {field}: wrong type "
                        f"({type(r[field]).__name__})")
    if errs:
        return errs
    if r["id"] in existing_ids:
        errs.append(f"duplicate id: {r['id']}")
    if r["entity_type"] not in ENTITY_TYPES:
        errs.append(f"entity_type not in {sorted(ENTITY_TYPES)}")
    if r["source_type"] not in SOURCE_TYPES:
        errs.append(f"source_type not in {sorted(SOURCE_TYPES)}")
    if r["constraint_type"] not in CONSTRAINT_TYPES:
        errs.append(f"constraint_type not in {sorted(CONSTRAINT_TYPES)}")
    if r["firmness"] not in FIRMNESS_LEVELS:
        errs.append(f"firmness not in {sorted(FIRMNESS_LEVELS)}")
    dc = r["date_ce"]
    if len(dc) != 2 or not all(isinstance(x, int) for x in dc) or dc[0] > dc[1]:
        errs.append("date_ce must be [earliest, latest] integer CE years, ascending")
    if r["lag"] is not None:
        lg = r["lag"]
        if len(lg) != 2 or not all(isinstance(x, (int, float)) for x in lg) or lg[0] > lg[1]:
            errs.append("lag must be null or [low, high] ascending")
    if not isinstance(r["references"], list) or not r["references"]:
        errs.append("references must be a non-empty list")
    if "firmness_reason" in r and not isinstance(r["firmness_reason"], str):
        errs.append("firmness_reason must be a string")
    return errs


def write_csv(anchors, path):
    fields = ["id", "indian_entity", "entity_type", "chinese_source",
              "source_type", "event", "date_raw", "date_ce_earliest",
              "date_ce_latest", "constraint_type", "lag_low", "lag_high",
              "lag_solid", "firmness", "firmness_reason", "notes",
              "references"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in anchors:
            w.writerow({
                "id": r["id"], "indian_entity": r["indian_entity"],
                "entity_type": r["entity_type"],
                "chinese_source": r["chinese_source"],
                "source_type": r["source_type"], "event": r["event"],
                "date_raw": r["date_raw"],
                "date_ce_earliest": r["date_ce"][0],
                "date_ce_latest": r["date_ce"][1],
                "constraint_type": r["constraint_type"],
                "lag_low": r["lag"][0] if r["lag"] else "",
                "lag_high": r["lag"][1] if r["lag"] else "",
                "lag_solid": r.get("lag_solid", False),
                "firmness": r["firmness"],
                "firmness_reason": r.get("firmness_reason", ""),
                "notes": r["notes"],
                "references": "; ".join(r["references"]),
            })


# ------------------------------------------------------------------ commands
def cmd_lookup(args):
    records = find_anchors(args.entity)
    if not records:
        print(f"No anchors found for '{args.entity}'.")
        return 1
    print(f"# {args.entity} — {len(records)} Chinese-dated anchor(s)\n")
    for r in records:
        print(f"- {r['indian_entity']}  [{r['id']}]")
        print(f"  source: {r['chinese_source']} ({r['source_type']})")
        print(f"  event:  {r['event']}")
        print(f"  date:   {r['date_raw']}  ->  {fmt_range(r['date_ce'])}")
        print(f"  constraint: {r['constraint_type']}   firmness: "
              f"{r['firmness']} — {r.get('firmness_reason', '')}")
        if r.get("lag"):
            print(f"  lag:    {r['lag']} years "
                  f"({'solid' if r.get('lag_solid') else 'not solid'}) — "
                  f"{r.get('lag_basis', '')}")
        print()
    d = derive_constraints(records)
    print("## Derived constraints")
    if d["hard_taq"] is not None:
        print(f"- HARD TAQ: the entity existed by {fmt_year(d['hard_taq'])} "
              f"(latest guaranteed bound across TAQ records).")
    if d["hard_tpq"] is not None:
        print(f"- HARD TPQ: not before {fmt_year(d['hard_tpq'])}.")
    for r in d["attested"]:
        print(f"- ATTESTED {r['constraint_type']}: {fmt_range(r['date_ce'])} "
              f"via {r['chinese_source']} ({r['firmness']}).")
    for w in d["lag_windows"]:
        print(f"- LAG-ADJUSTED composition window ({w['kind']}, from "
              f"{w['record']}): {fmt_range(w['window'])} — PROBABILISTIC, "
              f"not a bound. Basis: {w['note']}.")
    if d["hard_taq"] is None and not d["attested"]:
        print("- No hard bounds derivable from these records.")
    return 0


def cmd_correct(args):
    res = correct(args.entity, args.traditional[0], args.traditional[1])
    print(f"# correct: {args.entity}")
    print(f"traditional range: {fmt_range(res['traditional'])}")
    print(f"verdict: {res['verdict'].upper()}")
    if res["corrected"]:
        print(f"corrected interval: {fmt_range(res['corrected'])}")
    print()
    for line in res["lines"]:
        print(f"- {line}")
    return 0 if res["verdict"] != "no-data" else 1


def cmd_lag(args):
    stats = lag_stats()
    print("# Empirical composition-to-translation lag (SOLID cases only)\n")
    for c in stats["cases"]:
        print(f"- {c['entity']} [{c['id']}]: lag {c['lag']} years "
              f"(midpoint {c['midpoint']:.0f})")
        print(f"    basis: {c['basis']}")
    print(f"\nn_solid = {stats['n_solid']}")
    if stats["status"] == "insufficient":
        print(f"STATUS: INSUFFICIENT — fewer than {LAG_MIN_SOLID} solid "
              f"cases. The tool refuses to present a distribution from "
              f"this; the cases above are all that honestly exists.")
    else:
        print(f"median of midpoints: {stats['median_midpoint']:.0f} years")
        print(f"mean of midpoints:   {stats['mean_midpoint']:.0f} years")
        print(f"overall range:       {stats['overall_range']} years")
        print(f"STATUS: {stats['status'].upper()} — computed from the "
              f"solid cases only"
              + ("; n is at the minimum threshold, treat as indicative, "
                 "not as a fitted distribution."
                 if stats["status"] == "provisional" else "."))
    if stats["excluded"]:
        print(f"\nExcluded (lag present but composition window not "
              f"independently anchored, n={len(stats['excluded'])}):")
        for e in stats["excluded"]:
            print(f"- [{e['id']}] lag {e['lag']} — {e['basis']}")
    return 0


def cmd_panel(args):
    anchors = load_anchors()
    out = args.out or DEFAULT_PANEL_OUT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fields = ["entity", "anchor_id", "constraint_type", "bound_semantics",
              "bound_earliest_ce", "bound_latest_ce", "firmness",
              "source_type", "chinese_source", "lag_low", "lag_high",
              "lag_solid"]
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in anchors:
            if r["constraint_type"] == "TAQ":
                sem = "existed_by_latest"
            elif r["constraint_type"] == "TPQ":
                sem = "not_before_earliest"
            else:
                sem = "attested_window_must_intersect"
            w.writerow({
                "entity": r["indian_entity"], "anchor_id": r["id"],
                "constraint_type": r["constraint_type"],
                "bound_semantics": sem,
                "bound_earliest_ce": r["date_ce"][0],
                "bound_latest_ce": r["date_ce"][1],
                "firmness": r["firmness"], "source_type": r["source_type"],
                "chinese_source": r["chinese_source"],
                "lag_low": r["lag"][0] if r["lag"] else "",
                "lag_high": r["lag"][1] if r["lag"] else "",
                "lag_solid": r.get("lag_solid", False),
            })
    print(f"panel written: {out} ({len(anchors)} anchors)")
    return 0


def cmd_add(args):
    with open(args.file, encoding="utf-8") as f:
        payload = json.load(f)
    new_records = payload if isinstance(payload, list) else [payload]
    with open(ANCHORS_PATH, encoding="utf-8") as f:
        db = json.load(f)
    existing = [r["id"] for r in db["anchors"]]
    all_errs = []
    for r in new_records:
        all_errs += [f"{r.get('id', '?')}: {e}"
                     for e in validate_record(r, existing)]
        existing.append(r.get("id"))
    if all_errs:
        print("REJECTED — schema errors:")
        for e in all_errs:
            print(f"- {e}")
        return 1
    db["anchors"].extend(new_records)
    with open(ANCHORS_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
    write_csv(db["anchors"], os.path.join(DATA_DIR, "anchors.csv"))
    print(f"added {len(new_records)} anchor(s); database now holds "
          f"{len(db['anchors'])}")
    return 0


def cmd_eras(args):
    matches = convert_era(args.era_name, args.year)
    if not matches:
        print(f"Era '{args.era_name}' not in the table. "
              f"(Table covers Later Han through Northern Song; add eras "
              f"to data/eras.json.)")
        return 1
    if len(matches) > 1:
        print(f"WARNING: era name '{args.era_name}' is borne by "
              f"{len(matches)} dynasties — ambiguous without a dynasty:")
    for m in matches:
        line = (f"- {m['era']} ({m['dynasty']}): "
                f"{fmt_year(m['start'])} .. {fmt_year(m['end'])}")
        if "ce" in m:
            line += (f"  |  year {m['year_n']} = {fmt_year(m['ce'])}"
                     + ("" if m["in_range"] else
                        "  [WARNING: beyond the era's attested length]"))
        print(line)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="spine.py",
        description="Chinese Correlation Spine — date Indian history "
                    "by correlation with precisely dated Chinese records.")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("lookup", help="all anchors constraining an entity")
    q.add_argument("entity")
    q.set_defaults(fn=cmd_lookup)

    q = sub.add_parser("correct", help="correct a traditional date range")
    q.add_argument("entity")
    q.add_argument("--traditional", nargs=2, type=int, required=True,
                   metavar=("START", "END"),
                   help="traditional range in CE years (BCE negative)")
    q.set_defaults(fn=cmd_correct)

    q = sub.add_parser("lag", help="empirical lag statistics")
    q.set_defaults(fn=cmd_lag)

    q = sub.add_parser("panel", help="export benchmark-ready anchor table")
    q.add_argument("--out", default=None)
    q.set_defaults(fn=cmd_panel)

    q = sub.add_parser("add", help="append anchors from a JSON file")
    q.add_argument("file")
    q.set_defaults(fn=cmd_add)

    q = sub.add_parser("eras", help="reign-era -> CE conversion info")
    q.add_argument("era_name")
    q.add_argument("year", nargs="?", type=int, default=None)
    q.set_defaults(fn=cmd_eras)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
