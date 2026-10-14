-- Doctor banking details: collapsed back into ONE step (finalize),
-- submitted together with the proof-of-banking document and schedule.
-- Admin approval is a single action - there's no separate banking review
-- gate, so `review_status` is dropped. Account number is encrypted
-- application-side (Fernet, see core/crypto.py) before being stored.

BEGIN;

ALTER TABLE health.doctor_banking_details
    DROP COLUMN IF EXISTS review_status,
    ADD COLUMN IF NOT EXISTS bank_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS account_holder_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS account_number_encrypted TEXT,
    ADD COLUMN IF NOT EXISTS account_number_last4 VARCHAR(4),
    ADD COLUMN IF NOT EXISTS branch_code VARCHAR(20),
    ADD COLUMN IF NOT EXISTS account_type VARCHAR(50);

-- Backfill the new NOT NULL columns for any pre-existing rows before
-- tightening constraints, then:
ALTER TABLE health.doctor_banking_details
    ALTER COLUMN bank_name SET NOT NULL,
    ALTER COLUMN account_holder_name SET NOT NULL,
    ALTER COLUMN account_number_encrypted SET NOT NULL,
    ALTER COLUMN account_number_last4 SET NOT NULL,
    ALTER COLUMN branch_code SET NOT NULL,
    ALTER COLUMN account_type SET NOT NULL;

-- The separate post-approval payout-account table/endpoint was reverted -
-- drop it if it was created by the earlier version of this change:
DROP TABLE IF EXISTS health.doctor_payout_accounts;

COMMIT;
