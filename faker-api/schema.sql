-- RDS PostgreSQL Schema
-- Run this once before the first DAG execution

-- ── Raw ingestion tables ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_users (
    id              SERIAL PRIMARY KEY,
    external_id     VARCHAR(64),
    firstname       VARCHAR(100),
    lastname        VARCHAR(100),
    email           VARCHAR(200),
    phone           VARCHAR(50),
    address         JSONB,
    ingested_at     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw_orders (
    id              SERIAL PRIMARY KEY,
    external_id     VARCHAR(64),
    user_id         VARCHAR(64),
    product         VARCHAR(200),
    quantity        INT,
    unit_price      NUMERIC(10, 2),
    total_price     NUMERIC(10, 2),
    status          VARCHAR(50),
    ingested_at     TIMESTAMP DEFAULT NOW()
);

-- ── Processed / enriched tables ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS processed_users (
    id              SERIAL PRIMARY KEY,
    external_id     VARCHAR(64) UNIQUE,
    full_name       VARCHAR(200),
    email           VARCHAR(200),
    email_domain    VARCHAR(100),
    phone           VARCHAR(50),
    city            VARCHAR(100),
    country         VARCHAR(100),
    processed_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS processed_orders (
    id              SERIAL PRIMARY KEY,
    external_id     VARCHAR(64) UNIQUE,
    user_id         VARCHAR(64),
    product         VARCHAR(200),
    quantity        INT,
    unit_price      NUMERIC(10, 2),
    total_price     NUMERIC(10, 2),
    revenue_band    VARCHAR(20),   -- LOW / MEDIUM / HIGH
    status          VARCHAR(50),
    processed_at    TIMESTAMP DEFAULT NOW()
);

-- ── Pipeline run audit log ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              SERIAL PRIMARY KEY,
    dag_id          VARCHAR(200),
    run_id          VARCHAR(200),
    records_fetched INT,
    records_loaded  INT,
    status          VARCHAR(50),
    started_at      TIMESTAMP,
    finished_at     TIMESTAMP DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_raw_users_ingested     ON raw_users(ingested_at);
CREATE INDEX IF NOT EXISTS idx_raw_orders_ingested    ON raw_orders(ingested_at);
CREATE INDEX IF NOT EXISTS idx_proc_users_ext_id      ON processed_users(external_id);
CREATE INDEX IF NOT EXISTS idx_proc_orders_ext_id     ON processed_orders(external_id);
CREATE INDEX IF NOT EXISTS idx_proc_orders_user       ON processed_orders(user_id);
