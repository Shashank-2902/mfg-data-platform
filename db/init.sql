-- Creates every table the project needs. Safe to run more than once.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- One row per sensor reading. event_time is synthetic (see README).
CREATE TABLE IF NOT EXISTS raw_readings (
    machine_id            text             NOT NULL,
    event_time            timestamptz      NOT NULL,
    received_at           timestamptz      NOT NULL DEFAULT now(),
    udi                   integer          NOT NULL,
    product_type          text             NOT NULL,
    air_temp_k            double precision NOT NULL,
    process_temp_k        double precision NOT NULL,
    rotational_speed_rpm  integer          NOT NULL,
    torque_nm             double precision NOT NULL,
    tool_wear_min         integer          NOT NULL,
    machine_failure       integer          NOT NULL,
    twf                   integer          NOT NULL,
    hdf                   integer          NOT NULL,
    pwf                   integer          NOT NULL,
    osf                   integer          NOT NULL,
    rnf                   integer          NOT NULL,
    -- Same machine and same time means the same reading, so a repeat is skipped.
    PRIMARY KEY (machine_id, event_time)
);

SELECT create_hypertable('raw_readings', 'event_time',
                         chunk_time_interval => interval '1 day',
                         if_not_exists => TRUE);

-- Messages that failed validation are kept here instead of being lost.
CREATE TABLE IF NOT EXISTS rejected_readings (
    id           bigserial   PRIMARY KEY,
    received_at  timestamptz NOT NULL DEFAULT now(),
    reason       text        NOT NULL,
    payload      text        NOT NULL
);

-- Alerts the monitor wants to send. A row stays here until n8n confirms delivery.
CREATE TABLE IF NOT EXISTS outbox (
    id               bigserial   PRIMARY KEY,
    machine_id       text        NOT NULL,
    incident_type    text        NOT NULL,
    severity         text        NOT NULL,
    message          text        NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    attempts         integer     NOT NULL DEFAULT 0,
    next_attempt_at  timestamptz NOT NULL DEFAULT now(),
    delivered_at     timestamptz
);

-- The incident log. n8n inserts here, the monitor closes incidents when they clear.
CREATE TABLE IF NOT EXISTS incidents (
    id             bigserial   PRIMARY KEY,
    machine_id     text        NOT NULL,
    incident_type  text        NOT NULL,
    severity       text        NOT NULL,
    message        text        NOT NULL,
    status         text        NOT NULL DEFAULT 'open',
    opened_at      timestamptz NOT NULL DEFAULT now(),
    resolved_at    timestamptz,
    outbox_id      bigint
);

-- Only one open incident per machine and type. This is the dedupe rule.
CREATE UNIQUE INDEX IF NOT EXISTS one_open_incident
    ON incidents (machine_id, incident_type)
    WHERE status = 'open';
