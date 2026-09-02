"""File upload API routes for Berb Web UI.

Provides a multipart upload endpoint for PDF and data files.
Files are validated by extension and size, then saved to a managed
uploads directory. The returned paths can be passed as
``uploaded_file_paths`` when creating a research job.

Pattern follows ``berb/server/routes/voice.py`` (``UploadFile``,
``File(...)``, ``APIRouter``).
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["uploads"])

# Maximum upload size: 100 MB per file
MAX_UPLOAD_SIZE = 100 * 1024 * 1024
# Allowed file extensions
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".csv",
        ".json",
        ".jsonl",
        ".txt",
        ".md",
        ".yaml",
        ".yml",
        ".py",
        ".tsv",
    }
)
# Default upload directory (relative to CWD or absolute)
_DEFAULT_UPLOAD_DIR = "uploads"


def _get_upload_dir() -> Path:
    """Resolve the upload directory, creating it if needed.

    Uses the ``BERB_UPLOAD_DIR`` environment variable if set,
    otherwise falls back to ``uploads/`` in the current directory.
    """
    upload_dir = Path(os.environ.get("BERB_UPLOAD_DIR", _DEFAULT_UPLOAD_DIR))
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _validate_filename(filename: str) -> str:
    """Sanitise a filename and validate its extension.

    Args:
        filename: Original upload filename.

    Returns:
        Sanitised basename (path separators stripped).

    Raises:
        HTTPException(400): If the extension is not allowed.
    """
    # Strip any directory components
    name = Path(filename).name
    if not name:
        raise HTTPException(status_code=400, detail="Empty filename")

    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{ext}' is not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return name


def _compute_sha256(content: bytes) -> str:
    """Compute SHA-256 hex digest of file content."""
    return hashlib.sha256(content).hexdigest()


@router.post("/uploads", summary="Upload one or more files")
async def upload_files(
    files: list[UploadFile] = File(..., description="Files to upload (PDF, CSV, JSON, etc.)"),
) -> dict:
    """Upload one or more files for a research run.

    Saves validated files to the uploads directory with a
    ``{sha256_prefix}_{original_name}`` naming scheme to prevent
    collisions and aid deduplication.

    Returns a list of dicts, each with ``path`` (absolute), ``size``,
    ``sha256``, and ``original_name``. Use the returned ``path`` values
    as ``uploaded_file_paths`` in a subsequent research job creation
    request.

    **Example:**

    .. code-block:: bash

        curl -X POST http://localhost:8000/api/uploads \\
            -F "files=@paper.pdf" \\
            -F "files=@data.csv"

    **Response:**

    .. code-block:: json

        {
            "files": [
                {
                    "path": "/abs/path/to/uploads/a1b2_paper.pdf",
                    "original_name": "paper.pdf",
                    "size": 123456,
                    "sha256": "a1b2c3d4e5f6..."
                }
            ]
        }
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    upload_dir = _get_upload_dir()
    saved: list[dict] = []

    for file in files:
        # Validate extension
        safe_name = _validate_filename(file.filename or "unnamed")

        # Read content
        try:
            content = await file.read()
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to read uploaded file '{safe_name}': {exc}",
            ) from exc

        # Validate size
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File '{safe_name}' exceeds {MAX_UPLOAD_SIZE // (1024 * 1024)} MB limit",
            )

        # Compute checksum for deduplication
        sha = _compute_sha256(content)

        # Write file with checksum prefix to avoid collisions
        dest_path = upload_dir / f"{sha}_{safe_name}"
        try:
            dest_path.write_bytes(content)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save file '{safe_name}': {exc}",
            ) from exc

        abs_path = str(dest_path.resolve())
        saved.append(
            {
                "path": abs_path,
                "original_name": safe_name,
                "size": len(content),
                "sha256": sha,
            }
        )

        logger.info(
            "Uploaded: %s → %s (%d bytes, sha256=%s)",
            safe_name,
            abs_path,
            len(content),
            sha,
        )

    return {"files": saved}
