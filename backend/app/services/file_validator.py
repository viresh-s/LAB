"""
File validation service for uploaded PDFs.

Security checks performed:
  1. File size limit (default: 10 MB)
  2. MIME type check (must be application/pdf)
  3. Magic bytes check (must start with %PDF-)
  4. Filename sanitization (remove path traversal, special chars)

Usage:
    from app.services.file_validator import validate_pdf

    errors = await validate_pdf(file)
    if errors:
        raise HTTPException(400, detail=errors)
"""
import logging
import re
from typing import Optional

from fastapi import UploadFile

log = logging.getLogger(__name__)

# ── Limits ────────────────────────────────────────────────────────────────────
MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024  # 5 MB

# ── PDF magic bytes ───────────────────────────────────────────────────────────
# Every valid PDF starts with "%PDF-" (hex: 25 50 44 46 2D)
PDF_MAGIC_BYTES = b"%PDF-"

# ── Allowed MIME types ────────────────────────────────────────────────────────
ALLOWED_MIME_TYPES = {"application/pdf"}


async def validate_pdf(
    file: UploadFile,
    max_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> list[str]:
    """
    Validate an uploaded file to ensure it's a safe PDF.

    Args:
        file: The uploaded file from FastAPI's UploadFile.
        max_size_bytes: Maximum allowed file size in bytes.

    Returns:
        List of error messages. Empty list = file is valid.
    """
    errors = []

    # ── 1. Check filename ─────────────────────────────────────────────────
    if not file.filename:
        errors.append("No filename provided.")
        return errors

    # Sanitize filename
    safe_name = sanitize_filename(file.filename)
    if not safe_name.lower().endswith(".pdf"):
        errors.append(f"File must be a PDF. Got: {file.filename}")

    # ── 2. Check MIME type ────────────────────────────────────────────────
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        errors.append(
            f"Invalid file type: {content_type}. Only PDF files are allowed."
        )

    # ── 3. Read file content and check size ───────────────────────────────
    content = await file.read()
    await file.seek(0)  # Reset for later use

    if len(content) == 0:
        errors.append("File is empty.")
        return errors

    if len(content) > max_size_bytes:
        size_mb = len(content) / (1024 * 1024)
        errors.append(
            f"File too large: {size_mb:.1f} MB. Maximum allowed: {MAX_FILE_SIZE_MB} MB."
        )

    # ── 4. Check magic bytes ──────────────────────────────────────────────
    if not content[:5] == PDF_MAGIC_BYTES:
        errors.append(
            "File does not appear to be a valid PDF (invalid file header). "
            "The file may be corrupt or is not a real PDF."
        )

    # ── 5. Scan for suspicious content ────────────────────────────────────
    # Check for JavaScript in PDF (common attack vector)
    suspicious_patterns = [
        b"/JavaScript",
        b"/JS ",
        b"/Launch",
        b"/EmbeddedFile",
        b"/OpenAction",
        b"/AA ",          # Additional Actions
        b"/RichMedia",
    ]

    # Only check first 100KB to avoid scanning massive files
    scan_region = content[:102400]
    for pattern in suspicious_patterns:
        if pattern in scan_region:
            errors.append(
                f"PDF contains potentially unsafe content: {pattern.decode('ascii', errors='replace')}. "
                "Please upload a clean PDF report."
            )
            break  # One warning is enough

    if errors:
        log.warning("[file_validator] Rejected file '%s': %s", file.filename, errors)
    else:
        log.info(
            "[file_validator] File '%s' validated: %d bytes, type=%s",
            safe_name, len(content), content_type,
        )

    return errors


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal and injection.

    - Removes directory components (path traversal: ../, /, \\)
    - Removes special characters except alphanumeric, -, _, .
    - Limits length to 100 characters
    """
    # Remove any directory path
    filename = filename.replace("\\", "/")
    filename = filename.split("/")[-1]

    # Remove special characters (keep alphanumeric, -, _, .)
    filename = re.sub(r"[^\w\-.]", "_", filename)

    # Limit length
    if len(filename) > 100:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = name[:95] + ("." + ext if ext else "")

    return filename or "report.pdf"


def generate_storage_path(lab_id: str, booking_id: str) -> str:
    """
    Generate a lab-isolated storage path for a report PDF.

    Format: {lab_id}/{booking_id}.pdf

    This ensures:
      - Each lab's files are in their own folder
      - Lab A cannot access Lab B's folder (enforced by Supabase Storage RLS)
      - Each booking has exactly one report file
    """
    # Sanitize IDs to prevent path traversal
    safe_lab_id = re.sub(r"[^\w\-]", "", lab_id)
    safe_booking_id = re.sub(r"[^\w\-]", "", booking_id)

    return f"{safe_lab_id}/{safe_booking_id}.pdf"
