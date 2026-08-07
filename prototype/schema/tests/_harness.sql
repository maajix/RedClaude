-- Assertion harness. Every check runs inside a plpgsql subtransaction that is
-- always rolled back, so checks cannot contaminate each other.

CREATE SCHEMA IF NOT EXISTS t;

CREATE TABLE IF NOT EXISTS t.results (
    ord   serial,
    id    text,
    kind  text,
    pass  boolean,
    note  text
);

-- Expect p_sql to raise, with SQLERRM containing p_match.
CREATE OR REPLACE FUNCTION t.expect_raise(p_id text, p_sql text, p_match text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE p_sql;
        RAISE EXCEPTION 'T_NO_ERROR';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM = 'T_NO_ERROR' THEN
            INSERT INTO t.results (id, kind, pass, note)
            VALUES (p_id, 'expect_raise', false, 'no error raised');
        ELSIF position(p_match in SQLERRM) > 0 THEN
            INSERT INTO t.results (id, kind, pass, note)
            VALUES (p_id, 'expect_raise', true, SQLERRM);
        ELSE
            INSERT INTO t.results (id, kind, pass, note)
            VALUES (p_id, 'expect_raise', false,
                    'wrong error: ' || SQLERRM || ' (wanted ~ ' || p_match || ')');
        END IF;
    END;
END $$;

-- Expect p_sql to succeed. Always rolled back.
CREATE OR REPLACE FUNCTION t.expect_ok(p_id text, p_sql text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE p_sql;
        RAISE EXCEPTION 'T_NO_ERROR';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM = 'T_NO_ERROR' THEN
            INSERT INTO t.results (id, kind, pass, note)
            VALUES (p_id, 'expect_ok', true, '');
        ELSE
            INSERT INTO t.results (id, kind, pass, note)
            VALUES (p_id, 'expect_ok', false, SQLERRM);
        END IF;
    END;
END $$;

-- Expect a boolean predicate to hold. p_sql must return one boolean.
CREATE OR REPLACE FUNCTION t.expect_true(p_id text, p_sql text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE b boolean;
BEGIN
    BEGIN
        EXECUTE p_sql INTO b;
        INSERT INTO t.results (id, kind, pass, note)
        VALUES (p_id, 'expect_true', coalesce(b, false), coalesce(b::text,'NULL'));
    EXCEPTION WHEN OTHERS THEN
        INSERT INTO t.results (id, kind, pass, note)
        VALUES (p_id, 'expect_true', false, SQLERRM);
    END;
END $$;
