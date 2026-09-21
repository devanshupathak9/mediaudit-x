"""
Extracts real LCD policy records from CMS's own bulk "current LCD"
database export into our medical-policies schema.

WHERE TO GET THE SOURCE FILE: cms.gov/medicare-coverage-database ->
"Downloadable Databases" -> the current LCD zip (contains lcd.csv, the
full national LCD table, plus contractor/jurisdiction lookup tables).
Download it in a normal browser -- CMS's own site blocks automated
fetches (Akamai bot-protection returns "Access Denied" on every path,
including the bare domain root; see ingest_policies.py's docstring),
but a human downloading through the browser has no such restriction.
Unzip it, then unzip the nested *_csv.zip inside it -- that's the
CSV_DIR this script reads from.

This was run for real on 17 Sept 2026 against that export to produce
data/real_cms_lcd_policies.json, pulling LCD L36575 "Total Knee
Arthroplasty" (CPT 27447) and LCD L34163 "Total Hip Arthroplasty" (CPT
27130) -- both status=A (currently active), both adopted by Noridian
Healthcare Solutions, LLC. It strips CMS's embedded HTML, splits the
`indication` field on its own real "Limitations" heading into
clinical_indications / contraindications, and resolves the adopting
MAC's real name via the contractor cross-reference tables.

icd10_codes is deliberately left blank: this CSV table doesn't carry
ICD-10 codes (those ship in a separate "billing and coding article"
export not included in this download) -- left empty rather than guessed.

Usage:
    python -m app.ingestion.extract_real_cms_lcds /path/to/unzipped/csv/dir \\
        --out data/real_cms_lcd_policies.json
"""
import argparse
import csv
import html
import json
import re
from pathlib import Path

csv.field_size_limit(10**9)

TARGET_LCD_IDS = {
    "36575": {"policy_id": "POL-MEDICARE-LCD-36575", "cpt_codes": "27447"},   # Total Knee Arthroplasty
    "34163": {"policy_id": "POL-MEDICARE-LCD-34163", "cpt_codes": "27130"},   # Total Hip Arthroplasty
}

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t]+")
NL_RE = re.compile(r"\n{3,}")


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = TAG_RE.sub("\n", raw)
    text = html.unescape(text)
    text = WS_RE.sub(" ", text)
    text = NL_RE.sub("\n\n", text)
    return text.strip()


def load_contractors_for_lcd(csv_dir: Path, lcd_id: str) -> list[str]:
    names = set()
    contractor_ids = set()
    with open(csv_dir / "lcd_x_contractor.csv", newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if row["lcd_id"] == lcd_id:
                contractor_ids.add(row["contractor_id"])
    if not contractor_ids:
        return []
    with open(csv_dir / "contractor.csv", newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if row["contractor_id"] in contractor_ids:
                names.add(row["contractor_bus_name"])
    return sorted(names)


def extract(csv_dir: Path, target_lcd_ids: dict = TARGET_LCD_IDS) -> list[dict]:
    found = {}
    with open(csv_dir / "lcd.csv", newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if row["lcd_id"] in target_lcd_ids:
                found[row["lcd_id"]] = row

    docs = []
    for lcd_id, meta in target_lcd_ids.items():
        row = found.get(lcd_id)
        if not row:
            print(f"[warn] lcd_id {lcd_id} not present in this export")
            continue

        indication_full = strip_html(row.get("indication", ""))
        associated_info = strip_html(row.get("associated_info", ""))
        cms_cov_policy = strip_html(row.get("cms_cov_policy", ""))
        contractors = load_contractors_for_lcd(csv_dir, lcd_id)

        # CMS's export puts both "medically necessary when..." indications
        # AND "will NOT consider medically necessary when..." limitations in
        # the same free-text `indication` field, separated by its own real
        # "Limitations" heading. Split on that so our clinical_indications /
        # contraindications fields match the schema instead of dumping
        # everything into one field.
        split_match = re.search(r"\n\s*Limitations\s*\n", indication_full)
        if split_match:
            clinical_indications = indication_full[: split_match.start()].strip()
            limitations_section = indication_full[split_match.end():].strip()
        else:
            clinical_indications = indication_full
            limitations_section = ""

        contraindications = (limitations_section + "\n\n" + associated_info).strip()

        step_therapy_required = bool(
            re.search(r"(conservative|physical) therap", clinical_indications, re.IGNORECASE)
            and re.search(r"\b(month|week)s?\b", clinical_indications, re.IGNORECASE)
        )

        doc = {
            "policy_id": meta["policy_id"],
            "payer_name": "Medicare (CMS Local Coverage Determination)",
            "title": row["title"],
            "cpt_codes": meta["cpt_codes"],
            "icd10_codes": "",
            "clinical_indications": clinical_indications[:6000],
            "contraindications": contraindications[:3000],
            "step_therapy_required": step_therapy_required,
            "_source_note": (
                f"Real CMS LCD L{lcd_id} '{row['title']}', status={row['status']} "
                f"(A=active), last_updated={row['last_updated']}, "
                f"effective={row.get('rev_eff_date') or row.get('orig_det_eff_date')}. "
                f"Adopted by contractor(s): {', '.join(contractors) or 'unknown'}. "
                f"Extracted verbatim (HTML-stripped) from CMS's own 'current LCD' bulk "
                f"CSV database export (lcd.csv), downloaded from the CMS Medicare "
                f"Coverage Database. ICD-10 codes intentionally left blank (not present "
                f"in this table) rather than fabricated. Legal basis cited in the LCD "
                f"itself: {cms_cov_policy[:400]}"
            ),
        }
        docs.append(doc)
        print(f"Extracted L{lcd_id}: {row['title']} ({len(indication_full)} chars indication)")

    return docs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_dir", type=Path, help="Path to the unzipped CMS current-LCD CSV directory (contains lcd.csv)")
    parser.add_argument("--out", type=Path, default=Path("data/real_cms_lcd_policies.json"))
    args = parser.parse_args()

    docs = extract(args.csv_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(docs, indent=2))
    print(f"\nWrote {len(docs)} real policy docs -> {args.out}")
