-- Ticket 64: the mission packet's ceiling is configured, like the capsule's.
--
-- Decision 11 says a Mission packet has "a configured serialized byte and
-- estimated-token ceiling". The capsule beside it has had one since
-- 20260814T010000Z -- `capsule_max_bytes` and `capsule_max_tokens` on the
-- weights row, copied onto the session that was admitted under them -- and the
-- packet had none. `packet_module.compile` was called with no `limits=`, so
-- every worker and every orchestrator packet was fitted to whatever constants
-- `packet.py` happened to hold, and an operator lowering the one ceiling they
-- could set bounded one of the two documents a child reads.
--
-- Two columns and no more. The packet is compiled fresh for one turn out of
-- the state as it stands, so it takes the setting as it stands -- which is why
-- these are not copied onto `orchestrator_sessions` the way the capsule's are.
-- What a campaign inherits is measured against what the campaign was admitted
-- under; what one turn reads is measured against what is configured now, and an
-- operator who lowers this ceiling should see the next packet honour it rather
-- than wait out a campaign.
--
-- The defaults are `packet.py`'s own constants, for the reason the capsule's
-- share them: the same fitter fits both documents, and a second pair of numbers
-- here would be a second answer to a question the module already answers.

ALTER TABLE scheduler_weights
    ADD COLUMN packet_max_bytes  integer NOT NULL DEFAULT 65536
        CHECK (packet_max_bytes > 0),
    ADD COLUMN packet_max_tokens integer NOT NULL DEFAULT 8192
        CHECK (packet_max_tokens > 0);

COMMENT ON COLUMN scheduler_weights.packet_max_bytes IS
  'The serialized ceiling one Mission packet is fitted to. Read at the moment the packet is compiled rather than copied onto a session: a packet is one turn''s reading of current state, so it is bounded by the setting that is current.';
COMMENT ON COLUMN scheduler_weights.packet_max_tokens IS
  'The estimated-token ceiling one Mission packet is fitted to, at the same four bytes per token the capsule estimates with. Whichever of the two ceilings is smaller is the one that binds.';
