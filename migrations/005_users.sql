-- Migration 005: users table for multi-user web app
-- Rollback: DROP TABLE users;

CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    google_sub          TEXT NOT NULL UNIQUE,
    email               TEXT NOT NULL UNIQUE,
    display_name        TEXT,
    refresh_token       TEXT NOT NULL,
    delivery_email      TEXT NOT NULL DEFAULT '',
    timezone            TEXT NOT NULL DEFAULT 'America/New_York',
    status              TEXT NOT NULL DEFAULT 'active',
    onboarding_complete BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_brief_at       TIMESTAMPTZ
);
