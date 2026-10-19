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

ALTER TABLE consultation_notes
    ADD COLUMN ai_note TEXT,
    ADD COLUMN doctor_note TEXT,
    ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- Backfill existing notes into the new columns based on author.
UPDATE consultation_notes
SET ai_note = notes
WHERE author = 'ai';

UPDATE consultation_notes
SET doctor_note = notes
WHERE author = 'doctor';

ALTER TABLE consultation_notes
    ALTER COLUMN notes DROP NOT NULL;

COMMIT;
