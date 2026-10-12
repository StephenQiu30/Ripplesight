-- Independent restrictive authority only; never import into the business DB.
BEGIN;
CREATE SCHEMA restriction_journal;
REVOKE ALL ON SCHEMA restriction_journal FROM PUBLIC;

CREATE TABLE restriction_journal.head (
    slot SMALLINT PRIMARY KEY CHECK (slot = 1),
    ledger_id UUID NOT NULL,
    epoch BIGINT NOT NULL CHECK (epoch > 0),
    normalization_version TEXT NOT NULL CHECK (normalization_version = 'resource_uuid.v1'),
    sequence BIGINT NOT NULL CHECK (sequence >= 0),
    digest TEXT NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$')
);
CREATE TABLE restriction_journal.events (
    sequence BIGINT PRIMARY KEY CHECK (sequence > 0),
    operation_id UUID NOT NULL,
    owner_id UUID NOT NULL,
    action TEXT NOT NULL CHECK (action = 'deny_resource'),
    resource_type TEXT NOT NULL CHECK (resource_type ~ '^[a-z][a-z0-9_]{0,63}$'),
    resource_id UUID NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN (
        'user_request', 'retention_expired', 'authorization_revoked', 'source_deleted'
    )),
    occurred_at TIMESTAMPTZ NOT NULL,
    previous_digest TEXT NOT NULL CHECK (previous_digest ~ '^[0-9a-f]{64}$'),
    digest TEXT NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
    UNIQUE (owner_id, operation_id)
);
CREATE INDEX journal_resource_lookup ON restriction_journal.events
    (owner_id, resource_type, resource_id);

-- Only the DDL owner may initialize once. A missing head is never auto-repaired.
CREATE FUNCTION restriction_journal.initialize(p_ledger UUID, p_epoch BIGINT)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    payload pg_catalog.text;
BEGIN
    payload := '{"epoch":' || p_epoch::pg_catalog.text || ',"ledger_id":"' || p_ledger::pg_catalog.text ||
        '","normalization_version":"resource_uuid.v1"}';
    INSERT INTO restriction_journal.head VALUES (
        1, p_ledger, p_epoch, 'resource_uuid.v1', 0,
        encode(sha256(convert_to('ripplesight.recovery.genesis.v1', 'UTF8') ||
            decode('00', 'hex') || convert_to(payload, 'UTF8')), 'hex')
    );
END;
$$;

CREATE FUNCTION restriction_journal.append(
    p_ledger UUID, p_epoch BIGINT, p_owner UUID, p_operation UUID,
    p_type TEXT, p_resource UUID, p_reason TEXT
) RETURNS restriction_journal.events
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    current_head restriction_journal.head%ROWTYPE;
    receipt restriction_journal.events%ROWTYPE;
    payload pg_catalog.text;
BEGIN
    SELECT * INTO current_head FROM restriction_journal.head WHERE slot = 1 FOR UPDATE;
    IF NOT FOUND OR current_head.ledger_id IS DISTINCT FROM p_ledger OR
        current_head.epoch IS DISTINCT FROM p_epoch OR
        current_head.normalization_version <> 'resource_uuid.v1' THEN
        RAISE EXCEPTION USING ERRCODE = 'RJ002', MESSAGE = 'journal authority unavailable';
    END IF;
    SELECT * INTO receipt FROM restriction_journal.events
        WHERE owner_id = p_owner AND operation_id = p_operation;
    IF FOUND THEN
        IF receipt.resource_type IS DISTINCT FROM p_type OR
            receipt.resource_id IS DISTINCT FROM p_resource OR
            receipt.reason IS DISTINCT FROM p_reason THEN
            RAISE EXCEPTION USING ERRCODE = 'RJ001', MESSAGE = 'journal operation conflict';
        END IF;
        RETURN receipt;
    END IF;
    receipt.sequence := current_head.sequence + 1;
    receipt.operation_id := p_operation;
    receipt.owner_id := p_owner;
    receipt.action := 'deny_resource';
    receipt.resource_type := p_type;
    receipt.resource_id := p_resource;
    receipt.reason := p_reason;
    receipt.occurred_at := clock_timestamp();
    receipt.previous_digest := current_head.digest;
    -- All strings are constrained ASCII identifiers/enums/UUIDs, not free text.
    -- Alphabetic keys and fixed UTC microseconds match the Python contract.
    payload := '{"action":"deny_resource","occurred_at":"' ||
        to_char(receipt.occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') ||
        '","operation_id":"' || p_operation::pg_catalog.text || '","owner_id":"' || p_owner::pg_catalog.text ||
        '","previous_digest":"' || receipt.previous_digest || '","reason":"' || p_reason ||
        '","resource_id":"' || p_resource::pg_catalog.text || '","resource_type":"' || p_type ||
        '","sequence":' || receipt.sequence::pg_catalog.text || '}';
    receipt.digest := encode(sha256(convert_to('ripplesight.recovery.entry.v1', 'UTF8') ||
        decode('00', 'hex') || convert_to(payload, 'UTF8')), 'hex');
    INSERT INTO restriction_journal.events SELECT receipt.*;
    UPDATE restriction_journal.head SET sequence = receipt.sequence, digest = receipt.digest
        WHERE slot = 1;
    RETURN receipt;
END;
$$;

REVOKE ALL ON ALL TABLES IN SCHEMA restriction_journal FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA restriction_journal FROM PUBLIC;
COMMIT;
