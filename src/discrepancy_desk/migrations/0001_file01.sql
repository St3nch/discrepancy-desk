CREATE SCHEMA desk AUTHORIZATION desk_owner;
SET LOCAL ROLE desk_owner;

CREATE SEQUENCE desk.record_admission_order_seq CACHE 1;

CREATE TABLE desk.record_admission (
    admission_order bigint PRIMARY KEY,
    admitted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    actor_kind text NOT NULL CHECK (actor_kind IN ('operator', 'system')),
    label text NOT NULL CHECK (btrim(label) <> '')
);

CREATE TABLE desk.file (
    file_id uuid PRIMARY KEY,
    public_id text NOT NULL UNIQUE CHECK (public_id ~ '^DD-[0-9]{4}$'),
    subject text NOT NULL CHECK (btrim(subject) <> ''),
    investigation_question text NOT NULL CHECK (btrim(investigation_question) <> ''),
    admission_order bigint NOT NULL REFERENCES desk.record_admission
);

CREATE TABLE desk.artifact (
    artifact_id uuid PRIMARY KEY,
    hash_algorithm text NOT NULL CHECK (hash_algorithm = 'sha256'),
    digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    media_type text NOT NULL CHECK (media_type LIKE '%/%'),
    vault_key text NOT NULL CHECK (vault_key ~ '^vault/sha256/[0-9a-f]{2}/[0-9a-f]{64}$'),
    page_count integer CHECK (page_count > 0),
    duration_ms bigint CHECK (duration_ms > 0),
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    UNIQUE (hash_algorithm, digest),
    CHECK (media_type <> 'application/pdf' OR page_count IS NOT NULL),
    CHECK (
        (media_type NOT LIKE 'audio/%' AND media_type NOT LIKE 'video/%')
        OR duration_ms IS NOT NULL
    )
);

CREATE TABLE desk.capture (
    capture_id uuid PRIMARY KEY,
    artifact_id uuid NOT NULL REFERENCES desk.artifact,
    acquisition_url text NOT NULL CHECK (btrim(acquisition_url) <> ''),
    acquisition_host text NOT NULL CHECK (btrim(acquisition_host) <> ''),
    retrieved_at timestamptz NOT NULL,
    reported_media_type text,
    expected_hash_algorithm text NOT NULL CHECK (expected_hash_algorithm = 'sha256'),
    expected_digest text NOT NULL CHECK (expected_digest ~ '^[0-9a-f]{64}$'),
    expected_byte_size bigint NOT NULL CHECK (expected_byte_size >= 0),
    asserted_source_identity text,
    asserted_by text,
    identity_verification_state text NOT NULL
        CHECK (identity_verification_state IN ('unverified', 'contested')),
    identity_verification_basis text,
    provenance_note text NOT NULL CHECK (btrim(provenance_note) <> ''),
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    CHECK (
        (asserted_source_identity IS NULL OR btrim(asserted_source_identity) <> '')
        AND (asserted_by IS NULL OR btrim(asserted_by) <> '')
        AND (identity_verification_basis IS NULL OR btrim(identity_verification_basis) <> '')
        AND
        (asserted_source_identity IS NULL) = (asserted_by IS NULL)
    ),
    CHECK (
        identity_verification_state <> 'contested'
        OR (
            asserted_source_identity IS NOT NULL
            AND asserted_by IS NOT NULL
            AND identity_verification_basis IS NOT NULL
        )
    )
);

CREATE TABLE desk.file_capture (
    file_id uuid NOT NULL REFERENCES desk.file,
    capture_id uuid NOT NULL REFERENCES desk.capture,
    relevance_note text NOT NULL CHECK (btrim(relevance_note) <> ''),
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    PRIMARY KEY (file_id, capture_id)
);

CREATE TABLE desk.surface (
    surface_id uuid PRIMARY KEY,
    artifact_id uuid NOT NULL REFERENCES desk.artifact,
    surface_kind text NOT NULL CHECK (btrim(surface_kind) <> ''),
    produced_by_method text NOT NULL CHECK (btrim(produced_by_method) <> ''),
    produced_by_actor text NOT NULL CHECK (btrim(produced_by_actor) <> ''),
    produced_by_version text,
    produced_at timestamptz NOT NULL,
    hash_algorithm text NOT NULL CHECK (hash_algorithm = 'sha256'),
    digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    media_type text NOT NULL CHECK (media_type LIKE '%/%'),
    text_length integer NOT NULL CHECK (text_length > 0),
    vault_key text NOT NULL CHECK (vault_key ~ '^vault/sha256/[0-9a-f]{2}/[0-9a-f]{64}$'),
    source_locator_id uuid NOT NULL,
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    UNIQUE (hash_algorithm, digest, artifact_id, surface_kind, source_locator_id)
);

CREATE TABLE desk.locator (
    locator_id uuid PRIMARY KEY,
    locator_kind text NOT NULL
        CHECK (
            locator_kind IN (
                'document_page_char_range',
                'document_page',
                'media_time_range'
            )
        ),
    contract_version smallint NOT NULL CHECK (contract_version = 1),
    artifact_id uuid REFERENCES desk.artifact,
    surface_id uuid REFERENCES desk.surface,
    page_number integer,
    start_char integer,
    end_char integer,
    start_ms bigint,
    end_ms bigint,
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    CHECK (
        (
            locator_kind = 'document_page'
            AND artifact_id IS NOT NULL
            AND surface_id IS NULL
            AND page_number > 0
            AND start_char IS NULL
            AND end_char IS NULL
            AND start_ms IS NULL
            AND end_ms IS NULL
        )
        OR (
            locator_kind = 'document_page_char_range'
            AND artifact_id IS NULL
            AND surface_id IS NOT NULL
            AND page_number > 0
            AND start_char >= 0
            AND end_char > start_char
            AND start_ms IS NULL
            AND end_ms IS NULL
        )
        OR (
            locator_kind = 'media_time_range'
            AND artifact_id IS NOT NULL
            AND surface_id IS NULL
            AND page_number IS NULL
            AND start_char IS NULL
            AND end_char IS NULL
            AND start_ms >= 0
            AND end_ms > start_ms
        )
    )
);

ALTER TABLE desk.surface
    ADD CONSTRAINT surface_source_locator_fk
    FOREIGN KEY (source_locator_id)
    REFERENCES desk.locator
    DEFERRABLE INITIALLY DEFERRED;

CREATE FUNCTION desk.require_surface_source_locator_artifact()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM desk.locator locator
        LEFT JOIN desk.surface located_surface
          ON located_surface.surface_id = locator.surface_id
        WHERE locator.locator_id = NEW.source_locator_id
          AND NEW.artifact_id = COALESCE(locator.artifact_id, located_surface.artifact_id)
    ) THEN
        RAISE EXCEPTION 'Surface Artifact must match its source Locator target Artifact'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER require_surface_source_locator_artifact
AFTER INSERT ON desk.surface
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION desk.require_surface_source_locator_artifact();

CREATE TABLE desk.excerpt (
    excerpt_id uuid PRIMARY KEY,
    locator_id uuid NOT NULL REFERENCES desk.locator,
    surface_id uuid REFERENCES desk.surface,
    capture_id uuid NOT NULL REFERENCES desk.capture,
    exact_text text NOT NULL CHECK (exact_text <> ''),
    hash_algorithm text NOT NULL CHECK (hash_algorithm = 'sha256'),
    digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
    admission_order bigint NOT NULL REFERENCES desk.record_admission
);

CREATE FUNCTION desk.require_excerpt_surface_locator_binding()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    locator_surface_id uuid;
BEGIN
    SELECT locator.surface_id
    INTO locator_surface_id
    FROM desk.locator locator
    WHERE locator.locator_id = NEW.locator_id;

    IF locator_surface_id IS NOT NULL THEN
        IF NEW.surface_id IS NOT NULL
           AND NEW.surface_id IS DISTINCT FROM locator_surface_id THEN
            RAISE EXCEPTION 'Excerpt Surface must match its Locator Surface'
                USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.surface_id IS NULL OR NOT EXISTS (
        SELECT 1
        FROM desk.surface surface
        WHERE surface.surface_id = NEW.surface_id
          AND surface.source_locator_id = NEW.locator_id
    ) THEN
        RAISE EXCEPTION 'Excerpt Surface must derive from its Locator'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER require_excerpt_surface_locator_binding
AFTER INSERT ON desk.excerpt
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION desk.require_excerpt_surface_locator_binding();

CREATE FUNCTION desk.require_excerpt_capture_locator_artifact()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM desk.capture capture
        JOIN desk.locator locator
          ON locator.locator_id = NEW.locator_id
        LEFT JOIN desk.surface surface
          ON surface.surface_id = locator.surface_id
        WHERE capture.capture_id = NEW.capture_id
          AND capture.artifact_id = COALESCE(locator.artifact_id, surface.artifact_id)
    ) THEN
        RAISE EXCEPTION 'Excerpt Capture must contain its Locator target Artifact'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER require_excerpt_capture_locator_artifact
AFTER INSERT ON desk.excerpt
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION desk.require_excerpt_capture_locator_artifact();

CREATE TABLE desk.observation (
    observation_id uuid PRIMARY KEY,
    statement text NOT NULL CHECK (btrim(statement) <> ''),
    admission_order bigint NOT NULL REFERENCES desk.record_admission
);

CREATE TABLE desk.file_observation (
    file_id uuid NOT NULL REFERENCES desk.file,
    observation_id uuid NOT NULL REFERENCES desk.observation,
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    PRIMARY KEY (file_id, observation_id)
);

CREATE TABLE desk.observation_excerpt (
    observation_id uuid NOT NULL REFERENCES desk.observation,
    excerpt_id uuid NOT NULL REFERENCES desk.excerpt,
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    PRIMARY KEY (observation_id, excerpt_id)
);

CREATE FUNCTION desk.require_observation_excerpt()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM desk.observation_excerpt evidence
        WHERE evidence.observation_id = NEW.observation_id
          AND evidence.admission_order = NEW.admission_order
    ) THEN
        RAISE EXCEPTION 'Observation requires an Excerpt evidence path'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER require_observation_excerpt
AFTER INSERT ON desk.observation
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION desk.require_observation_excerpt();

CREATE FUNCTION desk.require_observation_excerpt_file()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM desk.file_observation observation_file
        WHERE observation_file.observation_id = NEW.observation_id
          AND NOT EXISTS (
              SELECT 1
              FROM desk.excerpt excerpt
              JOIN desk.file_capture file_capture
                ON file_capture.capture_id = excerpt.capture_id
               AND file_capture.file_id = observation_file.file_id
              WHERE excerpt.excerpt_id = NEW.excerpt_id
          )
    ) THEN
        RAISE EXCEPTION 'Every Observation File must include its Excerpt Capture'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER require_observation_excerpt_file
AFTER INSERT ON desk.observation_excerpt
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION desk.require_observation_excerpt_file();

CREATE FUNCTION desk.require_file_observation_captures()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM desk.observation_excerpt observation_evidence
        JOIN desk.excerpt excerpt
          ON excerpt.excerpt_id = observation_evidence.excerpt_id
        WHERE observation_evidence.observation_id = NEW.observation_id
          AND NOT EXISTS (
              SELECT 1
              FROM desk.file_capture file_capture
              WHERE file_capture.file_id = NEW.file_id
                AND file_capture.capture_id = excerpt.capture_id
          )
    ) THEN
        RAISE EXCEPTION 'Observation File must include every Excerpt Capture'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER require_file_observation_captures
AFTER INSERT ON desk.file_observation
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION desk.require_file_observation_captures();

CREATE TABLE desk.claim (
    claim_id uuid PRIMARY KEY,
    admission_order bigint NOT NULL REFERENCES desk.record_admission
);

CREATE TABLE desk.claim_version (
    claim_version_id uuid PRIMARY KEY,
    claim_id uuid NOT NULL REFERENCES desk.claim,
    version_number integer NOT NULL CHECK (version_number > 0),
    proposition text NOT NULL CHECK (btrim(proposition) <> ''),
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    UNIQUE (claim_id, version_number)
);

CREATE TABLE desk.file_claim (
    file_id uuid NOT NULL REFERENCES desk.file,
    claim_id uuid NOT NULL REFERENCES desk.claim,
    relevance_note text NOT NULL CHECK (btrim(relevance_note) <> ''),
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    PRIMARY KEY (file_id, claim_id)
);

CREATE TABLE desk.claim_version_observation_basis (
    claim_version_id uuid NOT NULL REFERENCES desk.claim_version,
    observation_id uuid NOT NULL REFERENCES desk.observation,
    relation_kind text NOT NULL CHECK (relation_kind IN ('supports', 'contradicts')),
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    PRIMARY KEY (claim_version_id, observation_id, relation_kind)
);

CREATE TABLE desk.decision (
    decision_id uuid PRIMARY KEY,
    authorized_by text NOT NULL CHECK (btrim(authorized_by) <> ''),
    decision_text text NOT NULL CHECK (btrim(decision_text) <> ''),
    admission_order bigint NOT NULL REFERENCES desk.record_admission
);

CREATE TABLE desk.claim_posture_decision_effect (
    decision_id uuid PRIMARY KEY REFERENCES desk.decision,
    claim_version_id uuid NOT NULL REFERENCES desk.claim_version,
    posture text NOT NULL
        CHECK (posture IN ('open', 'supported', 'not_supported', 'unresolved')),
    admission_order bigint NOT NULL REFERENCES desk.record_admission
);

CREATE TABLE desk.decision_supersession (
    decision_id uuid PRIMARY KEY REFERENCES desk.decision,
    supersedes_decision_id uuid NOT NULL REFERENCES desk.decision,
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    CHECK (decision_id <> supersedes_decision_id)
);

CREATE TABLE desk.discrepancy (
    discrepancy_id uuid PRIMARY KEY,
    file_id uuid NOT NULL REFERENCES desk.file,
    local_id text NOT NULL CHECK (local_id ~ '^D[0-9]{2}$'),
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    UNIQUE (file_id, local_id)
);

CREATE TABLE desk.discrepancy_version (
    discrepancy_version_id uuid PRIMARY KEY,
    discrepancy_id uuid NOT NULL REFERENCES desk.discrepancy,
    version_number integer NOT NULL CHECK (version_number > 0),
    question text NOT NULL CHECK (btrim(question) <> ''),
    lifecycle_state text NOT NULL
        CHECK (lifecycle_state IN ('open', 'narrowed', 'adequately_explained', 'closed')),
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    UNIQUE (discrepancy_id, version_number)
);

CREATE TABLE desk.discrepancy_observation_ref (
    discrepancy_version_id uuid NOT NULL REFERENCES desk.discrepancy_version,
    observation_id uuid NOT NULL REFERENCES desk.observation,
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    PRIMARY KEY (discrepancy_version_id, observation_id)
);

CREATE TABLE desk.discrepancy_claim_ref (
    discrepancy_version_id uuid NOT NULL REFERENCES desk.discrepancy_version,
    claim_version_id uuid NOT NULL REFERENCES desk.claim_version,
    admission_order bigint NOT NULL REFERENCES desk.record_admission,
    PRIMARY KEY (discrepancy_version_id, claim_version_id)
);

CREATE INDEX capture_artifact_idx ON desk.capture (artifact_id);
CREATE INDEX file_capture_capture_idx ON desk.file_capture (capture_id);
CREATE INDEX surface_artifact_idx ON desk.surface (artifact_id);
CREATE INDEX surface_source_locator_idx ON desk.surface (source_locator_id);
CREATE INDEX locator_artifact_idx ON desk.locator (artifact_id) WHERE artifact_id IS NOT NULL;
CREATE INDEX locator_surface_idx ON desk.locator (surface_id) WHERE surface_id IS NOT NULL;
CREATE INDEX excerpt_locator_idx ON desk.excerpt (locator_id);
CREATE INDEX excerpt_surface_idx ON desk.excerpt (surface_id) WHERE surface_id IS NOT NULL;
CREATE INDEX excerpt_capture_idx ON desk.excerpt (capture_id);
CREATE INDEX file_observation_observation_idx ON desk.file_observation (observation_id);
CREATE INDEX observation_excerpt_excerpt_idx ON desk.observation_excerpt (excerpt_id);
CREATE INDEX claim_version_claim_idx ON desk.claim_version (claim_id);
CREATE INDEX file_claim_claim_idx ON desk.file_claim (claim_id);
CREATE INDEX claim_basis_observation_idx
    ON desk.claim_version_observation_basis (observation_id, claim_version_id);
CREATE INDEX decision_effect_claim_version_idx
    ON desk.claim_posture_decision_effect (claim_version_id, decision_id);
CREATE INDEX decision_supersession_reverse_idx
    ON desk.decision_supersession (supersedes_decision_id, decision_id);
CREATE INDEX discrepancy_file_idx ON desk.discrepancy (file_id);
CREATE INDEX discrepancy_version_discrepancy_idx
    ON desk.discrepancy_version (discrepancy_id, version_number);
CREATE INDEX discrepancy_observation_reverse_idx
    ON desk.discrepancy_observation_ref (observation_id, discrepancy_version_id);
CREATE INDEX discrepancy_claim_reverse_idx
    ON desk.discrepancy_claim_ref (claim_version_id, discrepancy_version_id);

CREATE FUNCTION desk.validate_locator_contract()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    artifact_media_type text;
    artifact_page_count integer;
    artifact_duration_ms bigint;
    source_page_number integer;
    target_surface_kind text;
    target_text_length integer;
BEGIN
    IF NEW.locator_kind IN ('document_page', 'media_time_range') THEN
        SELECT media_type, page_count, duration_ms
        INTO artifact_media_type, artifact_page_count, artifact_duration_ms
        FROM desk.artifact
        WHERE artifact_id = NEW.artifact_id;
    END IF;

    IF NEW.locator_kind = 'document_page' THEN
        IF artifact_media_type <> 'application/pdf'
           OR NEW.page_number > artifact_page_count THEN
            RAISE EXCEPTION 'document page Locator is outside its PDF Artifact'
                USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.locator_kind = 'media_time_range' THEN
        IF (
            artifact_media_type NOT LIKE 'audio/%'
            AND artifact_media_type NOT LIKE 'video/%'
        ) OR NEW.end_ms > artifact_duration_ms THEN
            RAISE EXCEPTION 'media time Locator is outside its recording Artifact'
                USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.locator_kind = 'document_page_char_range' THEN
        SELECT s.surface_kind, source.page_number, s.text_length
        INTO target_surface_kind, source_page_number, target_text_length
        FROM desk.surface s
        JOIN desk.locator source ON source.locator_id = s.source_locator_id
        WHERE s.surface_id = NEW.surface_id;
        IF target_surface_kind <> 'document_page_text'
           OR source_page_number IS DISTINCT FROM NEW.page_number
           OR NEW.end_char > target_text_length THEN
            RAISE EXCEPTION 'document text Locator does not match its page-text Surface'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER validate_locator_contract
BEFORE INSERT ON desk.locator
FOR EACH ROW EXECUTE FUNCTION desk.validate_locator_contract();

CREATE FUNCTION desk.validate_decision_supersession()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    current_claim_id uuid;
    prior_claim_id uuid;
BEGIN
    SELECT cv.claim_id INTO current_claim_id
    FROM desk.claim_posture_decision_effect effect
    JOIN desk.claim_version cv ON cv.claim_version_id = effect.claim_version_id
    WHERE effect.decision_id = NEW.decision_id;
    SELECT cv.claim_id INTO prior_claim_id
    FROM desk.claim_posture_decision_effect effect
    JOIN desk.claim_version cv ON cv.claim_version_id = effect.claim_version_id
    WHERE effect.decision_id = NEW.supersedes_decision_id;
    IF current_claim_id IS NULL OR current_claim_id IS DISTINCT FROM prior_claim_id THEN
        RAISE EXCEPTION 'Decision supersession must remain within one Claim'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER validate_decision_supersession
BEFORE INSERT ON desk.decision_supersession
FOR EACH ROW EXECUTE FUNCTION desk.validate_decision_supersession();

CREATE FUNCTION desk.reject_governed_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'governed Desk Record is append-only'
        USING ERRCODE = '55000';
END;
$$;

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'record_admission', 'file', 'artifact', 'capture', 'file_capture',
        'surface', 'locator', 'excerpt', 'observation', 'file_observation',
        'observation_excerpt', 'claim', 'claim_version', 'file_claim',
        'claim_version_observation_basis', 'decision',
        'claim_posture_decision_effect', 'decision_supersession',
        'discrepancy', 'discrepancy_version',
        'discrepancy_observation_ref', 'discrepancy_claim_ref'
    ]
    LOOP
        EXECUTE format(
            'CREATE TRIGGER reject_mutation_%I '
            'BEFORE UPDATE OR DELETE OR TRUNCATE ON desk.%I '
            'FOR EACH STATEMENT EXECUTE FUNCTION desk.reject_governed_mutation()',
            table_name,
            table_name
        );
    END LOOP;
END;
$$;
