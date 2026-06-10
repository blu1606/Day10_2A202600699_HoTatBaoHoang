"""Scratch script: deep analysis of noise patterns in raw CSV."""
import csv, re
from collections import Counter

f = open('data/raw/policy_export_dirty.csv', encoding='utf-8')
rows = list(csv.DictReader(f))

# 1. Repeated special characters (not just "!!!")
special_chars = Counter()
for r in rows:
    t = r['chunk_text']
    for m in re.finditer(r'([!?@#$%^&*])\1+', t):
        special_chars[m.group()] += 1

print('=== REPEATED SPECIAL CHARS ===')
for k, v in special_chars.most_common():
    print(f'  {repr(k)}: {v}')

# 2. Prefix patterns (metadata-like text before colon)
print('\n=== PREFIX PATTERNS (before colon) ===')
prefix_patterns = Counter()
for r in rows:
    t = r['chunk_text']
    m = re.match(r'^([A-Za-z\u00C0-\u1EF9\s]+):\s', t)
    if m:
        prefix_patterns[m.group(1).strip()] += 1
for k, v in prefix_patterns.most_common():
    print(f'  "{k}": {v}')

# 3. Phrase repetition
print('\n=== PHRASE REPETITION ===')
for r in rows:
    t = r['chunk_text']
    m = re.search(r'(\b\S+(?:\s+\S+){1,}?)\s+\1', t)
    if m:
        print(f'  [{r["doc_id"]}] ...{m.group()[:80]}...')

# 4. Sentence-level repetition (same sentence repeated multiple times)
print('\n=== SENTENCE-LEVEL REPETITION ===')
for r in rows:
    t = r['chunk_text']
    # Split by period and check for repeated sentences
    sentences = [s.strip() for s in t.split('.') if len(s.strip()) > 10]
    if len(sentences) != len(set(sentences)):
        dup = [s for s in sentences if sentences.count(s) > 1]
        if dup:
            print(f'  [{r["doc_id"]}] {len(sentences)} sentences, {len(dup)} repeated')
            print(f'    text: {t[:100]}...')

# 5. Content that looks like it has wrong version info
print('\n=== VERSION CONFLICT SIGNALS ===')
for r in rows:
    t = r['chunk_text']
    eff = r.get('effective_date', '')
    doc = r['doc_id']
    # Records where text says "2025" but effective_date is 2026+
    if '2025' in t and eff.startswith('2026'):
        print(f'  [{doc}] date={eff} but text mentions 2025: {t[:80]}')
