"""
Cleaning rules — raw export → cleaned rows + quarantine.

Baseline gồm các failure mode mở rộng (allowlist doc_id, parse ngày, HR stale version).
Sinh viên thêm ≥3 rule mới: mỗi rule phải ghi `metric_impact` (xem README — chống trivial).
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Tuple

# =============================================================================
# CẤU HÌNH (CONFIGURATION)
# =============================================================================

# Allowlist doc_id — mở rộng khi nhóm thêm doc mới, phải đồng bộ contract.
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
        "access_control_sop",
    }
)

# Prefix nhiễu từ hệ thống export — KHÔNG chứa prefix nội dung thật
# như "FAQ bổ sung", "VPN", "Nghỉ ốm", "Escalation khẩn cấp"
NOISE_PREFIXES = frozenset({
    "Nội dung không rõ ràng",
})

# Ký tự đặc biệt lặp >= 2 lần liên tiếp → loại bỏ
NOISE_PUNCT_PATTERN = re.compile(r'([!?@#$%^&*])\1+')

SOURCE_DOCS: Dict[str, Dict[str, str]] = {
    "policy_refund_v4.txt": {"doc_id": "policy_refund_v4", "effective_date": "2026-02-01"},
    "sla_p1_2026.txt": {"doc_id": "sla_p1_2026", "effective_date": "2026-01-15"},
    "it_helpdesk_faq.txt": {"doc_id": "it_helpdesk_faq", "effective_date": "2026-01-20"},
    "hr_leave_policy.txt": {"doc_id": "hr_leave_policy", "effective_date": "2026-01-01"},
    "access_control_sop.txt": {"doc_id": "access_control_sop", "effective_date": "2026-01-01"},
}

# Phát hiện nội dung phiên bản cũ theo doc_id.
# Mỗi entry: list regex pattern — nếu match thì quarantine.
# Thêm doc mới hoặc version conflict mới → chỉ sửa dict này.
STALE_CONTENT_RULES: Dict[str, List[re.Pattern]] = {
    "hr_leave_policy": [
        re.compile(r"(?:bản|version)\s+HR\s+2025", re.IGNORECASE),
    ],
}

# Ngưỡng ngày hiệu lực tối thiểu cho từng loại tài liệu (tránh hard-code trong loop)
MIN_EFFECTIVE_DATES: Dict[str, str] = {
    "hr_leave_policy": "2026-01-01",
}

# Quy tắc sửa đổi nội dung lỗi thời/sai lệch (tránh hard-code trong loop)
# Mỗi entry: List[Tuple[Pattern, replacement_text, label_to_append]]
CONTENT_CORRECTION_RULES: Dict[str, List[Tuple[re.Pattern, str, str]]] = {
    "policy_refund_v4": [
        (
            re.compile(r"14\s*ngày\s*làm\s*việc", re.IGNORECASE),
            "7 ngày làm việc",
            "[cleaned: stale_refund_window]"
        ),
        (
            re.compile(r"14\s*ngày", re.IGNORECASE),
            "7 ngày làm việc",
            "[cleaned: stale_refund_window]"
        )
    ]
}

# Tiền tố định nghĩa ngữ cảnh cho RAG (giúp cải thiện chất lượng truy xuất)
CONTEXT_PREFIXES: Dict[str, str] = {
    "policy_refund_v4": "[Chính sách Hoàn tiền Refund Policy]",
    "sla_p1_2026": "[Quy định SLA Ticket IT Incident]",
    "it_helpdesk_faq": "[IT Helpdesk FAQ hỗ trợ]",
    "hr_leave_policy": "[Chính sách Nghỉ phép Nhân viên HR]",
    "access_control_sop": "[Quy trình Cấp quyền truy cập Access Control]",
}


# =============================================================================
# STEP 1: INTERNAL HELPERS (CÁC HÀM TRỢ GIÚP NỘI BỘ)
# Các hàm tiện ích dùng để chuẩn hóa chuỗi, ngày tháng và tạo ID duy nhất
# =============================================================================

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def _norm_text(s: str) -> str:
    """Normalize string by stripping, collapsing whitespaces, and converting to lowercase.

    Args:
        s: Raw input string.

    Returns:
        Normalized lowercase string with single space separator.
    """
    return " ".join((s or "").strip().split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    """Generate stable hash-based unique chunk ID.

    Args:
        doc_id: The document identifier.
        chunk_text: Text content of the chunk.
        seq: Sequence number of the chunk.

    Returns:
        Stable identifier string.
    """
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """Normalize effective date to ISO format YYYY-MM-DD.

    Args:
        raw: Raw date string from input data.

    Returns:
        Tuple containing:
          - iso_date: Date in YYYY-MM-DD format (empty if parsing fails).
          - error_reason: Description of the parse error if any.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    
    # Loại bỏ phần thời gian nếu có (ví dụ: "2026-04-11T00:00:00" -> "2026-04-11")
    s = re.split(r'[T ]', s)[0]
    
    # Thử parse các định dạng ngày phổ biến trong thực tế
    formats = [
        ("%Y-%m-%d", "%Y-%m-%d"),
        ("%d/%m/%Y", "%Y-%m-%d"),
        ("%Y/%m/%d", "%Y-%m-%d"),
        ("%d-%m-%Y", "%Y-%m-%d"),
        ("%m/%d/%Y", "%Y-%m-%d"),  # Kiểu Mỹ
    ]
    
    for fmt, out_fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            if 1900 <= dt.year <= 2100:
                return dt.strftime(out_fmt), ""
        except ValueError:
            continue
            
    return "", "invalid_effective_date_format"


# =============================================================================
# STEP 2: TEXT SANITIZERS (LÀM SẠCH VÀ CHUẨN HÓA DỮ LIỆU)
# Pipeline các hàm làm sạch text thô và chuẩn hóa các trường thông tin đặc thù
# =============================================================================

def _strip_noise_prefixes(text: str) -> str:
    """Remove noise prefix from the beginning of the text.

    Args:
        text: Raw chunk text.

    Returns:
        Sanitized text without leading noise prefixes.
    """
    for prefix in NOISE_PREFIXES:
        pattern = re.compile(r'^' + re.escape(prefix) + r':\s*', re.IGNORECASE)
        text = pattern.sub('', text)
    return text


def _strip_repeated_punctuation(text: str) -> str:
    """Remove repeated punctuation marks (>= 2 times consecutive).

    Args:
        text: Input text.

    Returns:
        Text with duplicate punctuation symbols removed.
    """
    return NOISE_PUNCT_PATTERN.sub('', text)


def _collapse_repeated_phrases(text: str) -> str:
    """Collapse duplicate contiguous phrases (1-2 words).

    Args:
        text: Input text.

    Returns:
        Text with collapsed repeating words/phrases.
    """
    return re.sub(r'\b(\w+(?:\s+\w+)?)(?:\s+\1)+\b', r'\1', text)


def _collapse_repeated_sentences(text: str) -> str:
    """Remove duplicated contiguous sentences in a chunk.

    Args:
        text: Input text.

    Returns:
        Text with duplicate contiguous sentences collapsed.
    """
    # Tách câu dựa trên dấu chấm theo sau bởi khoảng trắng hoặc cuối chuỗi (tránh viết tắt/URL/email)
    parts = [s.strip() for s in re.split(r'\.(?=\s|$)', text)]
    deduped: List[str] = []
    for part in parts:
        if not part:
            continue
        if not deduped or part != deduped[-1]:
            deduped.append(part)
    result = '. '.join(deduped)
    if result and not result.endswith('.'):
        result += '.'
    return result


def _normalize_phone_extensions(text: str) -> str:
    """Normalize various phone extension styles to standard "ext. <number>".

    Args:
        text: Input text.

    Returns:
        Text with phone extensions normalized.

    Metric Impact:
        Chuẩn hóa cách hiển thị các nhánh hỗ trợ nội bộ, cải thiện độ khớp từ khóa 
        và phân cấp thông tin trong cơ sở dữ liệu khi Agent thực hiện đối chiếu.
    """
    return re.sub(r'\b(?:nhánh|ext)\.?\s*(\d+)\b', r'ext. \1', text, flags=re.IGNORECASE)


def _normalize_urls_and_emails(text: str) -> str:
    """Normalize URLs and email addresses to lowercase and fix white spaces.

    Args:
        text: Input text.

    Returns:
        Text with normalized URLs and emails.

    Metric Impact:
        Loại bỏ khoảng trắng nhân tạo trong URL/email do export hoặc do tách câu lỗi,
        đảm bảo các thuật ngữ kỹ thuật được biểu diễn đồng nhất dưới dạng 1 token liên tục, giảm nhiễu nhúng.
    """
    # 1. Sửa lỗi khoảng trắng quanh dấu chấm trong email/URL: e.g. "company. internal" -> "company.internal"
    text = re.sub(r'(\w+)\s*\.\s*(\w+)', r'\1.\2', text)
    
    # 2. Lowercase các email và URL để đảm bảo tìm kiếm chính xác
    def _lower_match(match: re.Match) -> str:
        return match.group(0).lower()
        
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', _lower_match, text)
    text = re.sub(r'\bhttps?://[A-Za-z0-9.-]+(?:\.[A-Z|a-z]{2,})+(?:/[A-Za-z0-9._%+-]*)*\b', _lower_match, text)
    return text


def _enrich_it_synonyms(text: str) -> str:
    """Enrich common IT/English terms with their Vietnamese translations.

    Args:
        text: Input text.

    Returns:
        Text with enriched terms.

    Metric Impact:
        Cải thiện khả năng tìm kiếm ngữ nghĩa đối với các mô hình nhúng chỉ hỗ trợ tốt 
        tiếng Anh như all-MiniLM-L6-v2, giúp các câu hỏi bằng tiếng Việt (dùng từ 'cập nhật') khớp chính xác 
        với tài liệu thô dùng từ Tiếng Anh (như 'update').
    """
    # Tránh thay thế nếu từ đã được viết kèm chú thích
    replacements = [
        (re.compile(r'\bfirst response\b(?! \((?:phản hồi ban đầu|phản hồi đầu tiên)\))', re.IGNORECASE), "first response (phản hồi ban đầu phản hồi đầu tiên)"),
        (re.compile(r'\bresolution\b(?! \((?:giải quyết|xử lý|khắc phục)\))', re.IGNORECASE), "resolution (xử lý khắc phục)"),
        (re.compile(r'\bupdate\b(?! \((?:cập nhật|tiến độ|thông tin tiến độ)\))', re.IGNORECASE), "update (cập nhật thông tin tiến độ)"),
        (re.compile(r'\bresolve\b(?! \((?:giải quyết|xử lý|khắc phục)\))', re.IGNORECASE), "resolve (giải quyết khắc phục)"),
        (re.compile(r'\bstakeholder\b(?! \((?:bên liên quan|người liên quan)\))', re.IGNORECASE), "stakeholder (bên liên quan người liên quan)"),
        (re.compile(r'\bescalation\b(?! \((?:leo thang|chuyển cấp)\))', re.IGNORECASE), "escalation (leo thang chuyển cấp)"),
        (re.compile(r'\bticket\b(?! \((?:yêu cầu hỗ trợ|phiếu yêu cầu)\))', re.IGNORECASE), "ticket (yêu cầu hỗ trợ)"),
    ]
    for pattern, repl in replacements:
        text = pattern.sub(repl, text)
    return text


def _enrich_rag_context(text: str, doc_id: str) -> str:
    """Enrich chunk with contextual prefix describing the document type.

    Args:
        text: Input text.
        doc_id: The identifier of the document.

    Returns:
        Enriched text with prefix.

    Metric Impact:
        Nâng cao chất lượng biểu diễn ngữ nghĩa của các vector nhúng (embedding),
        giúp mô hình nhúng SentenceTransformer all-MiniLM-L6-v2 (vốn nhạy tiếng Anh) nhận biết 
        chính xác phân vùng tài liệu và ticket type liên quan, cải thiện tỷ lệ truy xuất đúng Top-1.
    """
    prefix = CONTEXT_PREFIXES.get(doc_id, "")
    if prefix and not text.startswith(prefix):
        return f"{prefix} {text}"
    return text


# Pipeline: thứ tự áp dụng CÓ Ý NGHĨA
# 1. Strip prefix trước (vì prefix che nội dung thật)
# 2. Strip punctuation (vì !!! có thể đứng sau prefix)
# 3. Collapse phrases (word-level)
# 4. Collapse sentences (sentence-level — xử lý sau cùng)
# 5. Normalize phone extensions
# 6. Normalize URLs and emails
# 7. Enrich IT synonyms
TEXT_SANITIZERS = [
    _strip_noise_prefixes,
    _strip_repeated_punctuation,
    _collapse_repeated_phrases,
    _collapse_repeated_sentences,
    _normalize_phone_extensions,
    _normalize_urls_and_emails,
    _enrich_it_synonyms,
]


# =============================================================================
# STEP 3: IO FUNCTIONS (CÁC HÀM ĐỌC VÀ GHI FILE)
# Đọc dữ liệu đầu vào (raw CSV, source docs) và xuất kết quả (cleaned, quarantine)
# =============================================================================

def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    """Load raw exported CSV file and parse rows into dictionaries.

    Args:
        path: Path to the raw CSV file.

    Returns:
        List of dictionaries representing each row in the CSV.
    """
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, r in enumerate(reader, start=1):
            row = {k: (v or "").strip() for k, v in r.items()}
            row.setdefault("source", "data/raw/policy_export_dirty.csv")
            row.setdefault("source_type", "raw_export")
            row.setdefault("chunk_index", str(i))
            rows.append(row)
    return rows


def _chunk_source_doc(text: str) -> List[str]:
    """Split the text of source document into smaller chunks based on section headers.

    Args:
        text: Full content of the source document.

    Returns:
        List of chunk texts.
    """
    chunks: List[str] = []
    current: List[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("=== ") and current:
            chunk = "\n".join(current).strip()
            if len(chunk) >= 20:
                chunks.append(chunk)
            current = [stripped]
        else:
            current.append(stripped)

    chunk = "\n".join(current).strip()
    if len(chunk) >= 20:
        chunks.append(chunk)
    return chunks


def load_source_docs(docs_dir: Path, exported_at: str) -> List[Dict[str, str]]:
    """Load and chunk all source documents from docs directory.

    Args:
        docs_dir: Path to directory containing source txt files.
        exported_at: Timestamp of pipeline execution.

    Returns:
        List of dictionaries containing document metadata and chunk text.
    """
    rows: List[Dict[str, str]] = []
    for file_name, meta in SOURCE_DOCS.items():
        path = docs_dir / file_name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for i, chunk in enumerate(_chunk_source_doc(text), start=1):
            rows.append(
                {
                    "doc_id": meta["doc_id"],
                    "chunk_text": chunk,
                    "effective_date": meta["effective_date"],
                    "exported_at": exported_at,
                    "source": f"data/docs/{file_name}",
                    "source_type": "source_doc",
                    "chunk_index": str(i),
                }
            )
    return rows


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write cleaned rows to output CSV file.

    Args:
        path: Output file path.
        rows: List of cleaned dictionaries.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at", "source", "source_type", "chunk_index"]
    if not rows:
        path.write_text(",".join(fieldnames) + "\n", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write quarantined rows with error reasons to CSV file.

    Args:
        path: Output file path.
        rows: List of quarantined dictionaries.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# =============================================================================
# STEP 4: CORE CLEANING LOGIC (LOGIC LỌC VÀ LÀM SẠCH CHÍNH)
# Hàm thực thi chính chạy qua pipeline để làm sạch và phân loại dữ liệu
# =============================================================================

def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Core function to process, clean, and split input rows into cleaned and quarantined records.

    Args:
        rows: List of input raw or source document dictionaries.
        apply_refund_window_fix: Whether to apply content correction rules.

    Returns:
        Tuple containing:
          - cleaned: List of cleaned dictionaries ready for embedding.
          - quarantine: List of quarantined dictionaries with reason.
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")
        source = raw.get("source", "data/raw/policy_export_dirty.csv")
        source_type = raw.get("source_type", "raw_export")
        chunk_index = raw.get("chunk_index", str(seq + 1))

        # 1. Allowlist filter
        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        # 2. Date normalization
        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        # 3. Date-based stale filter (config-driven)
        min_eff_date = MIN_EFFECTIVE_DATES.get(doc_id)
        if min_eff_date and eff_norm < min_eff_date:
            quarantine.append(
                {
                    **raw,
                    "reason": f"stale_{doc_id}_effective_date",
                    "effective_date_normalized": eff_norm,
                }
            )
            continue

        # 4. Content-based stale filter (config-driven)
        stale_patterns = STALE_CONTENT_RULES.get(doc_id, [])
        stale_hit = False
        for pattern in stale_patterns:
            if pattern.search(text):
                quarantine.append(
                    {
                        **raw,
                        "reason": f"stale_content_{doc_id}",
                        "effective_date_normalized": eff_norm,
                        "matched_pattern": pattern.pattern,
                    }
                )
                stale_hit = True
                break
        if stale_hit:
            continue

        # 5. Text sanitization pipeline
        sanitized = text
        for sanitizer in TEXT_SANITIZERS:
            sanitized = sanitizer(sanitized)
        sanitized = " ".join(sanitized.split()).strip()  # normalize whitespace

        # 6. Empty text check SAU sanitization
        if not sanitized:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        # 7. Content deduplication (trên text đã sanitized)
        key = _norm_text(sanitized)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        # 8. Content correction (config-driven)
        fixed_text = sanitized
        if apply_refund_window_fix:
            corrections = CONTENT_CORRECTION_RULES.get(doc_id, [])
            applied_labels = []
            for pattern, repl, label in corrections:
                if pattern.search(fixed_text):
                    fixed_text = pattern.sub(repl, fixed_text)
                    if label and label not in applied_labels:
                        applied_labels.append(label)
            if applied_labels:
                fixed_text += " " + " ".join(applied_labels)

        # 9. Context enrichment (RAG retrieval enhancement)
        enriched_text = _enrich_rag_context(fixed_text, doc_id)

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, enriched_text, seq),
                "doc_id": doc_id,
                "chunk_text": enriched_text,
                "effective_date": eff_norm,
                "exported_at": exported_at or "",
                "source": source,
                "source_type": source_type,
                "chunk_index": chunk_index,
            }
        )

    return cleaned, quarantine
