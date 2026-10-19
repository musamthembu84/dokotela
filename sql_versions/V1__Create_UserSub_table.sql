-- Schema is created/owned by Flyway via flyway.schemas=health (see docker-flyway.config).
-- Setting search_path here makes the rest of this script schema-agnostic.
SET search_path TO health;

CREATE TABLE users
(
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(255) NOT NULL UNIQUE,
    email           VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    role            VARCHAR(50)  NOT NULL,                   -- patient, doctor, admin
    status          VARCHAR(50)  NOT NULL DEFAULT 'pending', -- pending, active, suspended, deleted
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE payments
(
    id                      SERIAL PRIMARY KEY,
    user_id                 INTEGER        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    amount                  DECIMAL(10, 2) NOT NULL,
    currency                VARCHAR(3)     NOT NULL DEFAULT 'ZAR',
    status                  VARCHAR(50)    NOT NULL, -- pending, completed, failed, cancelled
    provider                VARCHAR(50)    NOT NULL DEFAULT 'payfast',
    payment_reference       VARCHAR(255) UNIQUE,     -- PayFast pf_payment_id or m_payment_id
    consultation_session_id VARCHAR(255),            -- Redis session ID used before persistence
    created_at              TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE consultations
(
    id         SERIAL PRIMARY KEY,
    patient_id INTEGER     NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    payment_id INTEGER     NOT NULL REFERENCES payments (id) ON DELETE RESTRICT,
    status     VARCHAR(50) NOT NULL, -- paid, assigned, in_progress, completed, cancelled
    created_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE consultation_notes
(
    id              SERIAL PRIMARY KEY,
    consultation_id INTEGER      NOT NULL REFERENCES consultations (id) ON DELETE CASCADE,
    author          VARCHAR(50)  NOT NULL, -- ai, doctor
    type            VARCHAR(100) NOT NULL, -- SOAP_AI, SOAP_DOCTOR, diagnosis, prescription, follow_up
    notes           TEXT         NOT NULL,
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE visits
(
    id              SERIAL PRIMARY KEY,
    consultation_id INTEGER     NOT NULL REFERENCES consultations (id) ON DELETE CASCADE,
    patient_id      INTEGER     NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    doctor_id       INTEGER     NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    scheduled_at    TIMESTAMP   NOT NULL,
    status          VARCHAR(50) NOT NULL, -- scheduled, confirmed, in_progress, completed, cancelled, no_show
    created_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    channel_name    VARCHAR(255) UNIQUE,
    video_provider  VARCHAR(50)          DEFAULT 'agora',
    video_status    VARCHAR(50)          DEFAULT 'waiting'
);

CREATE TABLE doctor_profiles
(
    id                     SERIAL PRIMARY KEY,
    user_id                INTEGER REFERENCES users (id) ON DELETE CASCADE,
    full_legal_name        VARCHAR(255) NOT NULL,
    hpcsa_number           VARCHAR(50)  NOT NULL UNIQUE,
    speciality             VARCHAR(100) NOT NULL,

    identity_document_path VARCHAR(500) NOT NULL,
    qualification_path     VARCHAR(500) NOT NULL,
    profile_photo_path     VARCHAR(500),

    verification_status    VARCHAR(50)  NOT NULL DEFAULT 'pending',


    verified_at            TIMESTAMP,
    created_at             TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE doctor_availability
(
    id                    SERIAL PRIMARY KEY,
    doctor_id             INTEGER   NOT NULL
        REFERENCES users (id) ON DELETE CASCADE,

    day_of_week           INTEGER   NOT NULL, -- 0=Monday, 6=Sunday
    start_time            TIME      NOT NULL,
    end_time              TIME      NOT NULL,
    slot_duration_minutes INTEGER   NOT NULL DEFAULT 30,
    is_active             BOOLEAN   NOT NULL DEFAULT TRUE,

    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


--prevents random onboarding attempts, someone changing another doctors onboarding enumeration attacks
CREATE TABLE doctor_onboarding_tokens
(
    id         SERIAL PRIMARY KEY,

    doctor_id  INTEGER      NOT NULL
        REFERENCES users (id) ON DELETE CASCADE,

    token      VARCHAR(255) NOT NULL UNIQUE,

    expires_at TIMESTAMP    NOT NULL,

    used       BOOLEAN      NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);