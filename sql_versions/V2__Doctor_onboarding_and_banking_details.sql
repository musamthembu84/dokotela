-- Doctor onboarding redesign: VerifyNow (Home Affairs) identity checks
-- replace manual HPCSA/document upload verification, and doctors now
-- submit banking details (encrypted account number + proof-of-banking
-- document) together with their schedule as a single finalize step.
-- Admin approval is a single action - there's no separate banking review
-- gate. Account number is encrypted application-side (Fernet, see
-- core/crypto.py) before being stored; only the last 4 digits are kept
-- in the clear for display.
--
-- Apply against the `health` schema. Review before running against a DB
-- that already has data - if doctor_profiles already has rows, drop/
-- rename columns manually with a backfill plan instead of blindly
-- running this against live data.

BEGIN;

-- doctor_profiles: hpcsa_number -> practice_number, archive the old
-- manual-upload document paths (renamed rather than dropped, so existing
-- doctors onboarded via the old flow don't lose their stored paths),
-- add id_number + verifynow_reference, verified_at becomes nullable
-- (only set once VerifyNow actually confirms identity).
ALTER TABLE health.doctor_profiles
    RENAME COLUMN hpcsa_number TO practice_number;

ALTER TABLE health.doctor_profiles
    RENAME COLUMN identity_document_path TO legacy_identity_document_path;

ALTER TABLE health.doctor_profiles
    RENAME COLUMN qualification_path TO legacy_qualification_path;

ALTER TABLE health.doctor_profiles
    ALTER COLUMN legacy_identity_document_path DROP NOT NULL,
    ALTER COLUMN legacy_qualification_path DROP NOT NULL,
    ADD COLUMN id_number VARCHAR(20),
    ADD COLUMN verifynow_reference VARCHAR(255),
    ALTER COLUMN verified_at DROP NOT NULL;

-- Pre-existing doctor_profiles rows (onboarded via the old manual
-- HPCSA/document flow) have no id_number and no way to backfill one
-- automatically (it's collected from VerifyNow for new doctors only),
-- so id_number stays nullable here - enforced at the application layer
-- for the new onboarding flow instead of a blanket NOT NULL. A partial
-- unique index still prevents duplicates among rows that do have one.
CREATE UNIQUE INDEX doctor_profiles_id_number_key
    ON health.doctor_profiles (id_number)
    WHERE id_number IS NOT NULL;

-- New table: doctor banking details, submitted at the final onboarding
-- step alongside the proof-of-banking document and schedule. Admin
-- approval of the whole application is what gates the doctor going
-- live - there's no separate banking review step.
CREATE TABLE health.doctor_banking_details
(
    id                       SERIAL PRIMARY KEY,
    doctor_id                INTEGER      NOT NULL UNIQUE REFERENCES health.users (id) ON DELETE CASCADE,
    bank_name                VARCHAR(255) NOT NULL,
    account_holder_name      VARCHAR(255) NOT NULL,
    account_number_encrypted TEXT         NOT NULL,
    account_number_last4     VARCHAR(4)   NOT NULL,
    branch_code              VARCHAR(20)  NOT NULL,
    account_type             VARCHAR(50)  NOT NULL,
    proof_of_banking_path    VARCHAR(255) NOT NULL,
    created_at               TIMESTAMP    NOT NULL DEFAULT now()
);

-- doctor_onboarding_tokens is no longer written to by the new self-serve
-- doctor registration flow (identity verification is now done inline via
-- VerifyNow before anything is persisted, gated by a Redis-only
-- registration id instead of a DB-linked token). Left in place for any
-- historical rows; safe to DROP once confirmed unused:
-- DROP TABLE health.doctor_onboarding_tokens;

COMMIT;
