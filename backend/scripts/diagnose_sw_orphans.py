"""Diagnostic: investigate why 13 SW industry members are orphaned.

Root symptom observed during the first full sync:
- `sync_sw_industry` reported 5851/5864 members inserted, 13 orphans.
- All 13 orphans map to L3 `index_code=850412.SI` (特钢Ⅲ) in `pro.index_member_all`.
- But `pro.index_classify(level='L3', src='SW2021')` returns `index_code=850401.SI`
  for the row named 特钢Ⅲ. So the two endpoints disagree on the L3 index_code.

This script re-fetches both endpoints and prints enough evidence to decide:
  1. Is this a stable Tushare data inconsistency (same industry, two codes)?
  2. Or does the classify row 850401 actually mean something different from 850412?
  3. Are there OTHER industries with the same double-code issue?
  4. Does `pro.index_member(index_code=850401.SI)` return the same 13 stocks?

Run:
    TUSHARE_TOKEN=... uv run python scripts/diagnose_sw_orphans.py

The script only reads from Tushare and the local DB. It does not modify anything.
"""

from __future__ import annotations

import os
import sys

import pandas as pd

try:
    import tushare as ts
except ImportError:
    print("ERROR: tushare not installed. Run `uv sync --group dev` from backend/.", file=sys.stderr)
    sys.exit(1)


def _pro():
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        print("ERROR: TUSHARE_TOKEN env var is required.", file=sys.stderr)
        sys.exit(2)
    ts.set_token(token)
    return ts.pro_api()


def _print_section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    pro = _pro()

    _print_section("STEP 1  fetch index_classify(level=L3, src=SW2021)")
    classify_df = pro.index_classify(level="L3", src="SW2021")
    print(f"total L3 rows: {len(classify_df)}")
    print(f"columns: {list(classify_df.columns)}")

    dup_names = classify_df["industry_name"].value_counts()
    dup_names = dup_names[dup_names > 1]
    print(f"industry_names appearing more than once in classify L3: {len(dup_names)}")
    if len(dup_names):
        print(dup_names.to_string())
    else:
        print("(none — every L3 name is unique inside classify)")

    _print_section("STEP 2  fetch full index_member_all with pagination")
    frames = []
    offset = 0
    while True:
        page = pro.index_member_all(is_new="Y", offset=offset, limit=3000)
        if page.empty:
            break
        frames.append(page)
        offset += 3000
        if offset > 30_000:
            break
    member_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    print(f"total member rows: {len(member_df)}")
    print(f"columns: {list(member_df.columns)}")

    _print_section("STEP 3  compute code sets and their intersection")
    classify_index_codes: set[str] = set(classify_df["index_code"].dropna().astype(str))
    member_index_codes: set[str] = set(member_df["l3_code"].dropna().astype(str))
    only_in_classify = classify_index_codes - member_index_codes
    only_in_member = member_index_codes - classify_index_codes
    intersection = classify_index_codes & member_index_codes
    print(f"classify L3 index_codes: {len(classify_index_codes)}")
    print(f"member l3_codes:         {len(member_index_codes)}")
    print(f"intersection:            {len(intersection)}")
    print(f"only in classify (no members carry this L3 code):        {len(only_in_classify)}")
    print(f"only in member  (member says L3 not in classify):        {len(only_in_member)}")

    _print_section("STEP 4  for every L3 code that lives only in member data, look up its details")
    for code in sorted(only_in_member):
        rows = member_df[member_df["l3_code"] == code]
        if rows.empty:
            continue
        first = rows.iloc[0]
        # Look for a matching classify row by industry_name
        match = classify_df[classify_df["industry_name"] == first["l3_name"]]
        print(f"\n  orphan member l3_code = {code}")
        print(f"    l3_name in member      = {first['l3_name']}")
        print(f"    l2_code / l2_name      = {first['l2_code']} / {first['l2_name']}")
        print(f"    l1_code / l1_name      = {first['l1_code']} / {first['l1_name']}")
        print(f"    members under this code = {len(rows)}")
        print(f"    sample ts_codes: {list(rows['ts_code'].head(3))}")
        if match.empty:
            print(f"    ▶ NO classify row with industry_name={first['l3_name']!r}  ← truly missing")
        else:
            for _, mrow in match.iterrows():
                print(
                    f"    ▶ classify has SAME NAME with different code: "
                    f"index_code={mrow['index_code']} industry_code={mrow['industry_code']} "
                    f"parent_code={mrow['parent_code']}"
                )

    _print_section("STEP 5  cross-check: call pro.index_member for the classify-side code (850401.SI)")
    try:
        alt = pro.index_member(index_code="850401.SI", is_new="Y")
        print(f"pro.index_member(index_code=850401.SI) returned {len(alt)} rows")
        if not alt.empty:
            print("columns:", list(alt.columns))
            print(alt.head(15).to_string())
    except Exception as exc:
        print(f"pro.index_member(850401.SI) errored: {type(exc).__name__}: {exc}")

    _print_section("STEP 6  cross-check: call pro.index_member for the member-side code (850412.SI)")
    try:
        alt = pro.index_member(index_code="850412.SI", is_new="Y")
        print(f"pro.index_member(index_code=850412.SI) returned {len(alt)} rows")
        if not alt.empty:
            print("columns:", list(alt.columns))
            print(alt.head(15).to_string())
    except Exception as exc:
        print(f"pro.index_member(850412.SI) errored: {type(exc).__name__}: {exc}")

    _print_section("STEP 7  scan classify for ALL L3 codes whose industry_code doesn't match the {8|85}xxxx pattern")
    # SW2021 L3 index_codes usually start with 85 (850xxx / 851xxx / 852xxx …).
    # Anything that doesn't may be legacy. This is a hint, not proof.
    weird = classify_df[~classify_df["index_code"].str.startswith("85")]
    print(f"L3 rows whose index_code does NOT start with '85': {len(weird)}")
    if not weird.empty:
        print(weird.to_string())

    _print_section("SUMMARY")
    print("If the orphan set == {850412.SI} and classify has a 特钢Ⅲ under 850401.SI with the")
    print("same parent chain, and pro.index_member(850401.SI) returns the same 13 tickers,")
    print("this is a Tushare data inconsistency: two codes for the same industry.")
    print()
    print("Options for the service layer (do NOT apply automatically):")
    print("  (a) Extend hydration to fall back on industry_name when l3_index_code is unknown.")
    print("      Remap the member's l3_index_code to the classify one.")
    print("  (b) Add a hand-maintained alias map (l3_index_code alias → canonical).")
    print("  (c) Accept the loss (13/5864 = 0.22%) and log the orphans.")


if __name__ == "__main__":
    main()
