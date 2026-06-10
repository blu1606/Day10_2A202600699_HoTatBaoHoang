"""Trace: tìm root cause cho chunk bị mất sau cleaning pipeline."""
import csv
import re
from transform.cleaning_rules import (
    ALLOWED_DOC_IDS, NOISE_PREFIXES, NOISE_PUNCT_PATTERN,
    STALE_CONTENT_RULES, TEXT_SANITIZERS,
    load_raw_csv, _norm_text, _normalize_effective_date,
)
from pathlib import Path

raw = load_raw_csv(Path("data/raw/policy_export_dirty.csv"))

# 1. Tìm tất cả chunk sla_p1_2026 trong raw
print("=== RAW: sla_p1_2026 chunks ===")
sla_raw = [r for r in raw if r["doc_id"] == "sla_p1_2026"]
for r in sla_raw:
    print(f"  id={r['chunk_id']} date={r['effective_date']} text={r['chunk_text'][:100]}")

# 2. Simulate cleaning cho từng chunk sla_p1_2026, trace từng bước
print(f"\n=== TRACE: sla_p1_2026 cleaning ===")
seen_text = set()
for r in sla_raw:
    text = r["chunk_text"]
    eff_raw = r["effective_date"]
    cid = r["chunk_id"]
    
    # Date check
    eff_norm, eff_err = _normalize_effective_date(eff_raw)
    if eff_err:
        print(f"  [{cid}] QUARANTINE: {eff_err}")
        continue
    
    # Stale content check
    stale = False
    for p in STALE_CONTENT_RULES.get("sla_p1_2026", []):
        if p.search(text):
            stale = True
            break
    if stale:
        print(f"  [{cid}] QUARANTINE: stale_content")
        continue
    
    # Sanitization trace
    sanitized = text
    for sanitizer in TEXT_SANITIZERS:
        before = sanitized
        sanitized = sanitizer(sanitized)
        if sanitized != before:
            print(f"  [{cid}] SANITIZER {sanitizer.__name__}:")
            print(f"    BEFORE: {before[:120]}")
            print(f"    AFTER:  {sanitized[:120]}")
    sanitized = " ".join(sanitized.split()).strip()
    
    if not sanitized:
        print(f"  [{cid}] QUARANTINE: empty after sanitization")
        continue
    
    # Dedup check
    key = _norm_text(sanitized)
    if key in seen_text:
        print(f"  [{cid}] QUARANTINE: duplicate_chunk_text")
        print(f"    text: {sanitized[:120]}")
        continue
    seen_text.add(key)
    print(f"  [{cid}] KEPT: {sanitized[:120]}")

# 3. Check cleaned CSV — what sla_p1_2026 chunks survived?
print(f"\n=== CLEANED: sla_p1_2026 chunks that survived ===")
cleaned_path = Path("artifacts/cleaned")
latest = sorted(cleaned_path.glob("cleaned_*.csv"))[-1] if list(cleaned_path.glob("cleaned_*.csv")) else None
if latest:
    with latest.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["doc_id"] == "sla_p1_2026":
                print(f"  {row['chunk_text'][:120]}")

# 4. Check nguồn gốc — file sla_p1_2026.txt chứa gì về escalation?
print(f"\n=== SOURCE: sla_p1_2026.txt — tìm 'escalat' ===")
src = Path("data/docs/sla_p1_2026.txt").read_text(encoding="utf-8")
for line in src.split("\n"):
    if "escalat" in line.lower() or "10 phút" in line.lower():
        print(f"  {line.strip()}")
