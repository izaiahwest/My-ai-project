#!/usr/bin/env python3
"""Build products/hierarchy.xlsx from products/research.csv.

research.csv holds one row per product pulled from Daily Virals (pass 2).
Rows are merged by TikTok Shop link (or by name if there's no link), so
re-runs keep history.

Score /100 (Izaiah's formula, see CLAUDE.md Part 1):
  momentum   ratio >=20% -> 40, 10-20% -> 25, <10% -> 10
  saturation Low 25, Medium 12, High 0
  repeatable videos_per_day * 2, max 20
  fits me    15  (products that don't fit are dropped, not scored)
Tie-break: higher $ per sale.

Missing data is never guessed: the cell stays empty and Notes gets "not shown: <field>".
"""
import csv, sys, re
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "products" / "research.csv"
OUT = ROOT / "products" / "hierarchy.xlsx"

FIELDS = ["product", "link", "category", "price", "commission_pct", "lifetime_units",
          "units_7d", "creators", "top3_views", "saturation", "fits_me", "videos_per_day",
          "why", "angle", "swipe_link", "status", "notes", "drop_reason", "first_seen"]

HEADERS = ["Rank", "Product", "TikTok Shop link", "Category", "Price", "Commission %",
           "$ per sale", "Lifetime units", "Units last 7 days", "7-day ratio",
           "Creators promoting", "Saturation", "Fits me?", "Videos a day I could film",
           "Leverage score", "Why it's high leverage", "Video angle", "Swipe video link",
           "Status", "Notes"]

MAKEUP = re.compile(r"\b(makeup|make-up|lipstick|lip gloss|mascara|foundation|concealer|eyeliner|eyeshadow|blush|bronzer|contour|lash)\b", re.I)


def num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("$", "").replace("%", "")
    if s == "":
        return None
    m = re.fullmatch(r"([\d.]+)\s*([kKmM]?)", s)
    if not m:
        return None
    n = float(m.group(1))
    return n * {"": 1, "k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6}[m.group(2)]


def score(r):
    lt, d7 = num(r["lifetime_units"]), num(r["units_7d"])
    ratio = (d7 / lt) if lt and d7 is not None else None
    mom = None if ratio is None else (40 if ratio >= .20 else 25 if ratio >= .10 else 10)
    sat = {"low": 25, "medium": 12, "high": 0}.get((r["saturation"] or "").strip().lower())
    vpd = num(r["videos_per_day"])
    rep = None if vpd is None else min(20, vpd * 2)
    parts = [mom, sat, rep]
    total = None if any(p is None for p in parts) else sum(parts) + 15
    return ratio, total


def drop_reason(r):
    if r.get("drop_reason"):
        return r["drop_reason"]
    if MAKEUP.search(f'{r["product"]} {r["category"]}'):
        return "Fits me: makeup"
    if (r["fits_me"] or "").strip().lower() in ("no", "n", "false"):
        return "Fits me: audience wouldn't believe it"
    d7, lt = num(r["units_7d"]), num(r["lifetime_units"])
    if d7 == 0:
        return "Momentum: no sales in last 7 days"
    if lt is not None and lt > 500_000:
        return "Saturation: over ~500K lifetime units"
    return None


def load():
    if not SRC.exists():
        sys.exit(f"missing {SRC}")
    rows, seen = [], {}
    with open(SRC, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r = {k: (r.get(k) or "").strip() for k in FIELDS}
            key = (r["link"] or r["product"]).lower()
            if key in seen:  # later rows update earlier ones, but keep Status/Notes
                old = seen[key]
                for k, v in r.items():
                    if v:
                        old[k] = v
                continue
            seen[key] = r
            rows.append(r)
    return rows


def main():
    rows = load()
    kept, dropped = [], []
    for r in rows:
        reason = drop_reason(r)
        if reason:
            dropped.append((r, reason))
            continue
        ratio, total = score(r)
        price, comm = num(r["price"]), num(r["commission_pct"])
        per_sale = round(price * comm / 100, 2) if price is not None and comm is not None else None
        missing = [h for h, k in [("price", "price"), ("commission", "commission_pct"),
                                  ("lifetime units", "lifetime_units"), ("7-day units", "units_7d"),
                                  ("creators", "creators"), ("saturation", "saturation"),
                                  ("videos/day", "videos_per_day")] if not r[k]]
        notes = r["notes"]
        if missing:
            notes = (notes + "; " if notes else "") + "not shown: " + ", ".join(missing)
        kept.append(dict(r=r, ratio=ratio, total=total, per_sale=per_sale, notes=notes))

    kept.sort(key=lambda x: (x["total"] if x["total"] is not None else -1,
                             x["per_sale"] or 0), reverse=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Hierarchy"
    hdr_font = Font(bold=True, color="FFFFFF")
    hdr_fill = PatternFill("solid", fgColor="1E5631")
    link_font = Font(color="0563C1", underline="single")

    def header(sheet, cols):
        sheet.append(cols)
        for c in sheet[1]:
            c.font, c.fill = hdr_font, hdr_fill
            c.alignment = Alignment(wrap_text=True, vertical="center")
        sheet.freeze_panes = "A2"

    header(ws, HEADERS)
    for i, k in enumerate(kept, 1):
        r = k["r"]
        ws.append([i, r["product"], r["link"] or None, r["category"] or None, num(r["price"]),
                   (num(r["commission_pct"]) / 100) if num(r["commission_pct"]) is not None else None,
                   k["per_sale"], num(r["lifetime_units"]), num(r["units_7d"]), k["ratio"],
                   num(r["creators"]), r["saturation"] or None, "Yes", num(r["videos_per_day"]),
                   k["total"], r["why"] or None, r["angle"] or None, r["swipe_link"] or None,
                   r["status"] or "New", k["notes"] or None])
        row = ws.max_row
        for col in (3, 18):
            c = ws.cell(row, col)
            if c.value and str(c.value).startswith("http"):
                c.hyperlink, c.font = c.value, link_font
        ws.cell(row, 5).number_format = '"$"#,##0.00'
        ws.cell(row, 6).number_format = "0%"
        ws.cell(row, 7).number_format = '"$"#,##0.00'
        ws.cell(row, 8).number_format = "#,##0"
        ws.cell(row, 9).number_format = "#,##0"
        ws.cell(row, 10).number_format = "0.0%"

    widths = [6, 34, 30, 16, 9, 11, 10, 13, 12, 10, 12, 11, 8, 11, 10, 40, 40, 30, 10, 36]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    wd = wb.create_sheet("Dropped")
    header(wd, ["Product", "TikTok Shop link", "Category", "Lifetime units", "Units last 7 days", "Rule failed"])
    for r, reason in dropped:
        wd.append([r["product"], r["link"] or None, r["category"] or None,
                   num(r["lifetime_units"]), num(r["units_7d"]), reason])
        c = wd.cell(wd.max_row, 2)
        if c.value and str(c.value).startswith("http"):
            c.hyperlink, c.font = c.value, link_font
    for i, w in enumerate([34, 30, 16, 13, 12, 40], 1):
        wd.column_dimensions[get_column_letter(i)].width = w

    wb.save(OUT)
    print(f"{len(kept)} ranked, {len(dropped)} dropped -> {OUT}")
    for i, k in enumerate(kept[:5], 1):
        print(f'{i}. {k["r"]["product"]}  score={k["total"]}  $/sale={k["per_sale"]}')


if __name__ == "__main__":
    main()
