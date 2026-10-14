"""
Thin client for VerifyNow (verifynow.co.za) — South Africa's identity
verification API. Used here for the "Face Match (Home Affairs)" bundle:
comparing a live selfie against the official Home Affairs ID photo for a
given SA ID number.

CONFIRMED against the real sandbox API (docs site is a JS-rendered SPA, so
the shape below was extracted from VerifyNow's embedded docs bundle and then
verified with a live sandbox call):

    POST {VERIFYNOW_BASE_URL}/facematch
    Headers: x-api-key, Content-Type: application/json,
             Idempotency-Key (required in production, optional in sandbox)
    Body: {
        "bundle": "facematch",
        "selfie_image_base64": "<base64 JPG/PNG/WEBP/TIFF, max 5MB decoded>",
        "id_number": "<13-digit SA ID number>",
        "mode": "sandbox" | "production",
    }

Real sandbox response observed:
    {
        "success": true,
        "requestId": "...",
        "results": {
            "face_match": {
                "status": "Approved" | "Declined" | "In Review",
                "score": 75,
                ...
            },
            ...
        },
        "remainingCredits": 50
    }

Error responses are `{"error": "...", "message": "...", "code": "..."}` with
4xx status, or a completed-negative "Face match failed" on HTTP 502. This
client fails *closed* — unrecognised shapes are treated as "error", never as
"verified" — so a schema drift can't accidentally wave through an unverified
doctor.
"""
import logging
import uuid

import requests

from core.config import settings

logger = logging.getLogger(__name__)

_VERIFIED_VALUES = {"approved"}
_REJECTED_VALUES = {"declined"}
_REVIEW_VALUES = {"in review"}


class VerifyNowClient:

    @staticmethod
    def verify_face_match(id_number: str, selfie_image_base64: str) -> dict:
        """
        Calls VerifyNow's "Face Match (Home Affairs)" bundle to confirm the
        supplied selfie matches the Home Affairs ID photo for `id_number`.

        Returns a normalized dict:
            {
                "outcome": "verified" | "rejected" | "review" | "error",
                "reference": str | None,   # VerifyNow's request id, for audit
                "score": int | None,       # match confidence score, 0-100
                "detail": str | None,      # human-readable reason on rejection/error
                "raw": dict | None,        # raw VerifyNow response, for debugging/audit
            }
        """
        if not settings.VERIFYNOW_API_KEY:
            logger.error("VerifyNow: VERIFYNOW_API_KEY is not configured")
            return {"outcome": "error", "reference": None, "score": None, "detail": "Verification service not configured", "raw": None}

        mode = "sandbox" if settings.VERIFYNOW_SANDBOX else "production"
        idempotency_key = str(uuid.uuid4())
        headers = {
            "x-api-key": settings.VERIFYNOW_API_KEY,
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        }
        payload = {
            "bundle": "facematch",
            "selfie_image_base64": selfie_image_base64,
            "id_number": id_number,
            "mode": mode,
        }

        try:
            response = requests.post(
                f"{settings.VERIFYNOW_BASE_URL}/facematch",
                json=payload,
                headers=headers,
                timeout=settings.VERIFYNOW_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            logger.error("VerifyNow: request failed: %s", exc)
            return {"outcome": "error", "reference": idempotency_key, "score": None, "detail": "Verification service unreachable", "raw": None}

        try:
            data = response.json()
        except ValueError:
            data = {}

        if response.status_code in (400, 401, 402, 409, 429):
            logger.error("VerifyNow: request rejected, status=%s body=%s", response.status_code, data)
            return {"outcome": "error", "reference": idempotency_key, "score": None, "detail": data.get("message") or data.get("error"), "raw": data}

        if response.status_code == 502:
            # Completed negative (e.g. "Face match failed") vs a transient upstream error
            # both surface as 502 — either way we can't confirm identity, so fail closed.
            logger.warning("VerifyNow: 502 response, body=%s", data)
            return {"outcome": "error", "reference": idempotency_key, "score": None, "detail": data.get("error") or data.get("message") or "Face match failed", "raw": data}

        if response.status_code >= 500:
            logger.error("VerifyNow: server error %s: %s", response.status_code, data)
            return {"outcome": "error", "reference": idempotency_key, "score": None, "detail": "Verification service unavailable", "raw": data}

        if not response.ok or not data.get("success", True):
            logger.error("VerifyNow: unexpected response status=%s body=%s", response.status_code, data)
            return {"outcome": "error", "reference": idempotency_key, "score": None, "detail": data.get("error") or data.get("message"), "raw": data}

        face_match = (data.get("results") or {}).get("face_match") or {}
        outcome = VerifyNowClient._normalize_outcome(face_match.get("status"))
        reference = data.get("requestId") or idempotency_key
        score = face_match.get("score")
        detail = None if outcome == "verified" else (face_match.get("status") or "Verification could not be completed")

        return {"outcome": outcome, "reference": reference, "score": score, "detail": detail, "raw": data}

    @staticmethod
    def _normalize_outcome(status) -> str:
        raw_status = str(status or "").strip().lower()

        if raw_status in _VERIFIED_VALUES:
            return "verified"
        if raw_status in _REJECTED_VALUES:
            return "rejected"
        if raw_status in _REVIEW_VALUES:
            return "review"

        logger.warning("VerifyNow: unrecognised face_match.status, treating as error: %r", status)
        return "error"
