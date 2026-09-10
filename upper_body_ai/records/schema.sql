-- =============================================================================
-- THERAYU PATIENT RECORDS
-- =============================================================================
-- One SQLite file on the clinic PC. Health data never leaves the machine.
--
-- DESIGN NOTES
--
-- * Angles are stored in degrees as REAL. Joint keys are the exact strings the
--   existing angle engine emits ("elbow_flexion_left" and friends) so nothing
--   has to be translated between the live path and the record.
--
-- * exercise_results holds one row per exercise performed. joint_summaries
--   fans out every clinical joint measured during that exercise, so a report
--   can show the prescribed joint AND spot compensation elsewhere.
--
-- * angle_samples is a DOWNSAMPLED trace (a few hertz), not every frame. At
--   10 fps a ten minute session would be 6000 rows per joint; the charts do not
--   need that resolution and the database should stay small enough to copy onto
--   a USB stick.
--
-- * day_index on sessions is days since that patient's FIRST session, so
--   "day 1 versus day 10" is a column rather than a computation every time.
-- =============================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- people ----
CREATE TABLE IF NOT EXISTS patients (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE,       -- clinic-facing ID, e.g. THR-0001
    full_name       TEXT    NOT NULL,
    date_of_birth   TEXT,                          -- ISO date, optional
    sex             TEXT,                          -- free text; not validated
    phone           TEXT,
    notes           TEXT,
    created_at      TEXT    NOT NULL,
    archived        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(full_name);

CREATE TABLE IF NOT EXISTS clinicians (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    role            TEXT,
    created_at      TEXT    NOT NULL
);

-- ------------------------------------------------------------ catalogue ----
CREATE TABLE IF NOT EXISTS conditions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE,
    name            TEXT    NOT NULL,
    body_region     TEXT    NOT NULL,              -- UPPER | LOWER | FULL
    description     TEXT
);

CREATE TABLE IF NOT EXISTS exercises (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE,
    name            TEXT    NOT NULL,
    body_mode       TEXT    NOT NULL,              -- UPPER_BODY | LOWER_BODY | FULL_BODY
    primary_joint   TEXT    NOT NULL,              -- angle key, e.g. shoulder_abduction_left
    mirror_joint    TEXT,                          -- opposite side, for symmetry scoring
    movement_type   TEXT    NOT NULL DEFAULT 'REP',-- REP | HOLD

    -- Not every tracked joint is a range to be maximised. shoulder_abduction
    -- improving means a bigger number; trunk_posture and neck_inclination are
    -- DEVIATIONS from neutral, where improving means a SMALLER number. Scoring
    -- one as though it were the other would report worsening posture as
    -- progress, so the direction is declared per exercise.
    goal            TEXT    NOT NULL DEFAULT 'INCREASE',  -- INCREASE | REDUCE

    instructions    TEXT
);

-- A condition's prescription: which exercises, in what order, to what target.
CREATE TABLE IF NOT EXISTS protocols (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id    INTEGER NOT NULL REFERENCES conditions(id) ON DELETE CASCADE,
    exercise_id     INTEGER NOT NULL REFERENCES exercises(id)  ON DELETE CASCADE,
    sequence        INTEGER NOT NULL,
    target_rom_deg  REAL,                          -- the ROM we are working towards
    target_reps     INTEGER,
    target_hold_sec INTEGER,

    -- The band a rep must enter to count, and that a hold must stay inside.
    -- Kept on the protocol rather than the exercise so the same movement can be
    -- prescribed conservatively for a fresh post-op patient and aggressively
    -- later in the same course of treatment.
    band_min_deg    REAL,
    band_max_deg    REAL,

    UNIQUE(condition_id, exercise_id)
);

-- -------------------------------------------------------- prescriptions ----
-- A clinician assigns a condition to a patient. The patient then only picks
-- their own name; the exercise list follows from the active assignment.
CREATE TABLE IF NOT EXISTS assignments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      INTEGER NOT NULL REFERENCES patients(id)   ON DELETE CASCADE,
    condition_id    INTEGER NOT NULL REFERENCES conditions(id) ON DELETE RESTRICT,
    clinician_id    INTEGER REFERENCES clinicians(id),
    assigned_at     TEXT    NOT NULL,
    active          INTEGER NOT NULL DEFAULT 1,
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_assign_patient ON assignments(patient_id, active);

-- ------------------------------------------------------------- sessions ----
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    assignment_id   INTEGER REFERENCES assignments(id),
    condition_id    INTEGER REFERENCES conditions(id),
    started_at      TEXT    NOT NULL,
    ended_at        TEXT,
    day_index       INTEGER NOT NULL DEFAULT 1,    -- 1 on the first ever session
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_patient ON sessions(patient_id, started_at);

CREATE TABLE IF NOT EXISTS exercise_results (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER NOT NULL REFERENCES sessions(id)  ON DELETE CASCADE,
    exercise_id       INTEGER NOT NULL REFERENCES exercises(id) ON DELETE RESTRICT,
    sequence          INTEGER NOT NULL DEFAULT 1,
    started_at        TEXT    NOT NULL,
    ended_at          TEXT,
    duration_sec      REAL    NOT NULL DEFAULT 0,

    -- Headline clinical numbers, all for the exercise's primary joint.
    rom_min_deg       REAL,
    rom_max_deg       REAL,
    rom_range_deg     REAL,                        -- max - min, the ROM achieved
    target_rom_deg    REAL,                        -- copied from protocol at the time
    rom_pct_of_target REAL,

    reps_completed    INTEGER NOT NULL DEFAULT 0,
    target_reps       INTEGER,
    hold_sec_total    REAL    NOT NULL DEFAULT 0,
    target_hold_sec   INTEGER,

    mean_quality_pct  REAL,                        -- from movement_quality_pct
    in_target_pct     REAL,                        -- share of time inside target band
    symmetry_delta    REAL,                        -- primary vs mirror joint

    frames_analysed   INTEGER NOT NULL DEFAULT 0,
    aborted           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_results_session ON exercise_results(session_id);

-- Every clinical joint seen during that exercise, not just the prescribed one.
-- Compensation shows up here: a shoulder exercise where trunk_posture climbs.
CREATE TABLE IF NOT EXISTS joint_summaries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_result_id  INTEGER NOT NULL REFERENCES exercise_results(id) ON DELETE CASCADE,
    joint_key           TEXT    NOT NULL,
    min_deg             REAL,
    max_deg             REAL,
    mean_deg            REAL,
    range_deg           REAL,
    UNIQUE(exercise_result_id, joint_key)
);

-- Downsampled trace for the progress charts.
CREATE TABLE IF NOT EXISTS angle_samples (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_result_id  INTEGER NOT NULL REFERENCES exercise_results(id) ON DELETE CASCADE,
    t_ms                INTEGER NOT NULL,
    joint_key           TEXT    NOT NULL,
    value_deg           REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_result ON angle_samples(exercise_result_id, joint_key);

-- Patient-reported outcome, captured after an exercise. Optional but clinically
-- worth far more than it costs to collect.
CREATE TABLE IF NOT EXISTS patient_reported (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_result_id  INTEGER NOT NULL UNIQUE REFERENCES exercise_results(id) ON DELETE CASCADE,
    pain_score          INTEGER,                   -- 0-10 numeric rating scale
    exertion_score      INTEGER,                   -- 6-20 Borg RPE, or 0-10 if you prefer
    comment             TEXT
);

-- ------------------------------------------------------------ bookkeeping ---
CREATE TABLE IF NOT EXISTS schema_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
