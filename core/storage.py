"""
Storage for documents collected during doctor onboarding (currently just the
proof-of-banking upload in the finalize step).

Two backends, switched by `settings.STORAGE_BACKEND`:
  - "local" (default): saves to disk under LOCAL_STORAGE_DIR and is served
    back via the static mount in `main.py` (`/uploads/...`). Dev-only -
    unencrypted, not backed up, not access-controlled. Fine for local
    testing, NOT for production.
  - "s3": uploads to S3 (server-side encrypted). This is what production
    should use - just set STORAGE_BACKEND=s3 and fill in the AWS_* settings,
    no other code changes needed since callers only ever get back an opaque
    `proof_of_banking_path` string. Admin viewing should be switched to
    presigned URLs at that point rather than the static mount.
"""
import logging
import mimetypes
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from core.config import BASE_DIR, settings

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
}


def _validate_and_read(file: UploadFile) -> tuple[bytes, str]:
    """Shared validation for both backends. Returns (contents, extension)."""
    content_type = (file.content_type or "").lower()
    extension = ALLOWED_CONTENT_TYPES.get(content_type)
    if extension is None:
        # Some browsers/clients omit or mis-set content_type - fall back to
        # sniffing the filename extension before rejecting.
        guessed_type, _ = mimetypes.guess_type(file.filename or "")
        extension = ALLOWED_CONTENT_TYPES.get((guessed_type or "").lower())
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proof of banking must be a PDF, PNG, or JPEG file",
        )

    max_bytes = settings.PROOF_OF_BANKING_MAX_MB * 1024 * 1024
    contents = file.file.read(max_bytes + 1)
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proof of banking must be {settings.PROOF_OF_BANKING_MAX_MB}MB or smaller",
        )
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    return contents, extension


def upload_proof_of_banking(registration_id: str, file: UploadFile) -> str:
    """
    Validates and stores a proof-of-banking document (PDF/PNG/JPG), returning
    an opaque key/path to store on `doctor_banking_details.proof_of_banking_path`.
    """
    contents, extension = _validate_and_read(file)
    relative_key = f"doctor-onboarding/proof-of-banking/{registration_id}/{uuid.uuid4().hex}.{extension}"
    content_type = file.content_type or f"application/{extension}"

    if settings.STORAGE_BACKEND == "s3":
        return _upload_to_s3(relative_key, contents, content_type)
    return _upload_to_local_disk(relative_key, contents)


def _upload_to_local_disk(relative_key: str, contents: bytes) -> str:
    root = Path(settings.LOCAL_STORAGE_DIR)
    if not root.is_absolute():
        root = BASE_DIR / root
    destination = root / relative_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(contents)
    logger.info("Saved proof of banking to local disk: %s", destination)
    return relative_key


def local_storage_path(relative_key: str) -> Path:
    """
    Resolves a stored `proof_of_banking_path` to an absolute path on disk,
    guarding against path traversal. Only meaningful when STORAGE_BACKEND=local.
    """
    root = Path(settings.LOCAL_STORAGE_DIR)
    if not root.is_absolute():
        root = BASE_DIR / root
    root = root.resolve()
    resolved = (root / relative_key).resolve()
    if root not in resolved.parents and resolved != root:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document path")
    if not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return resolved


def presigned_s3_url(relative_key: str, expires_in: int = 300) -> str:
    """Only meaningful when STORAGE_BACKEND=s3. Returns a short-lived GET URL."""
    import boto3
    from botocore.client import Config as BotoConfig

    client = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        config=BotoConfig(signature_version="s3v4"),
        **({"aws_access_key_id": settings.AWS_ACCESS_KEY_ID, "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY}
           if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY else {}),
        **({"endpoint_url": settings.AWS_ENDPOINT_URL_S3} if settings.AWS_ENDPOINT_URL_S3 else {}),
    )
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET_NAME, "Key": relative_key},
        ExpiresIn=expires_in,
    )


def _upload_to_s3(relative_key: str, contents: bytes, content_type: str) -> str:
    import boto3
    from botocore.client import Config as BotoConfig
    from botocore.exceptions import BotoCoreError, ClientError

    if not settings.S3_BUCKET_NAME:
        logger.error("S3_BUCKET_NAME is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage is not configured, please try again shortly",
        )

    kwargs = {
        "region_name": settings.AWS_REGION,
        "config": BotoConfig(signature_version="s3v4"),
    }
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    if settings.AWS_ENDPOINT_URL_S3:
        # Local dev only (Minio/LocalStack) - unset in production to hit AWS directly.
        kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL_S3

    try:
        client = boto3.client("s3", **kwargs)
        client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=relative_key,
            Body=contents,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 upload failed for key=%s: %s", relative_key, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not upload proof of banking, please try again shortly",
        ) from exc

    return relative_key
