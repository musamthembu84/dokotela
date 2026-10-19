-- Align consultation_notes with the ORM model (models/models.py), which
-- splits the single `notes` column into `ai_note` (AI-authored SOAP
-- summary) and `doctor_note` (doctor-authored note), and adds
-- `updated_at` for edit tracking.
--
-- The old `notes` column is kept (made nullable) for backward
-- compatibility with existing rows/tooling rather than dropped, per
-- request. Existing data is backfilled into `ai_note` or `doctor_note`
-- based on the `author` column.

BEGIN;

SET search_path TO health;

-- Columns/backfill are guarded so this is a safe no-op on a database
-- where consultation_notes was already created with the new shape
-- directly (no `notes` column ever existed) rather than migrated here.
ALTER TABLE consultation_notes
    ADD COLUMN IF NOT EXISTS ai_note TEXT,
    ADD COLUMN IF NOT EXISTS doctor_note TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'health'
          AND table_name = 'consultation_notes'
          AND column_name = 'notes'
    ) THEN
        -- Backfill existing notes into the new columns based on author.
        UPDATE consultation_notes
        SET ai_note = notes
        WHERE author = 'ai';

        UPDATE consultation_notes
        SET doctor_note = notes
        WHERE author = 'doctor';

        ALTER TABLE consultation_notes
            ALTER COLUMN notes DROP NOT NULL;
    END IF;
END $$;

COMMIT;
