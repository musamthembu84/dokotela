-- Doctor onboarding redesign: VerifyNow (Home Affairs) identity checks
-- replace manual HPCSA/document upload verification, and doctors now
-- only submit banking details for admin review (no more document paths).
--
-- Apply against the `health` schema. Review before running in production -
-- if doctor_profiles already has rows, drop/rename columns manually with a
-- backfill plan instead of blindly running this against live data.

BEGIN;

-- doctor_profiles: hpcsa_number -> practice_number, drop document paths,
-- add id_number + verifynow_reference, verified_at becomes nullable
-- (only set once VerifyNow actually confirms identity).
ALTER TABLE health.doctor_profiles
    RENAME COLUMN hpcsa_number TO practice_number;

ALTER TABLE health.doctor_profiles
    DROP COLUMN identity_document_path,
    DROP COLUMN qualification_path,
    ADD COLUMN id_number VARCHAR(20),
    ADD COLUMN verifynow_reference VARCHAR(255),
    ALTER COLUMN verified_at DROP NOT NULL;

-- Backfill id_number for any pre-existing rows before adding the
-- NOT NULL + UNIQUE constraints below, then:
ALTER TABLE health.doctor_profiles
    ALTER COLUMN id_number SET NOT NULL,
    ADD CONSTRAINT doctor_profiles_id_number_key UNIQUE (id_number);

-- New table: doctor banking details, uploaded at the final onboarding
-- step and manually reviewed by an admin (bank_statement_path points at
-- the uploaded statement) before the doctor is approved.
CREATE TABLE health.doctor_banking_details (
    id                    SERIAL PRIMARY KEY,
    doctor_id             INTEGER NOT NULL UNIQUE REFERENCES health.users(id) ON DELETE CASCADE,
    bank_name             VARCHAR(255) NOT NULL,
    account_holder_name   VARCHAR(255) NOT NULL,
    account_number        VARCHAR(255) NOT NULL,
    branch_code           VARCHAR(20) NOT NULL,
    account_type          VARCHAR(50) NOT NULL,
    bank_statement_path   VARCHAR(255) NOT NULL,
    review_status         VARCHAR(50) NOT NULL DEFAULT 'pending_review',
    created_at            TIMESTAMP NOT NULL DEFAULT now()
);

-- doctor_onboarding_tokens is no longer written to by the new self-serve
-- doctor registration flow (identity verification is now done inline via
-- VerifyNow before anything is persisted, gated by a Redis-only
-- registration id instead of a DB-linked token). Left in place for any
-- historical rows; safe to DROP once confirmed unused:
-- DROP TABLE health.doctor_onboarding_tokens;

COMMIT;
