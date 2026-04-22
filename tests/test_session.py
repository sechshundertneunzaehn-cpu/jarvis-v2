from bridge.session import Mode, Phase, Session, SessionStore


def test_new_session_defaults():
    store = SessionStore()
    s = store.new(caller_id="+1")
    assert s.phase == Phase.RINGING
    assert s.mode == Mode.ASSISTANT
    assert s.pair_id
    assert s.conference_name.startswith("pair-")
    assert store.active_count() == 1


def test_bind_and_lookup_by_call_sid():
    store = SessionStore()
    s = store.new()
    s.add_leg("user", "CA_user")
    store.bind_call(s.pair_id, "CA_user")
    assert store.by_call("CA_user") is s
    assert store.by_call("CA_missing") is None


def test_ended_session_not_active():
    store = SessionStore()
    s = store.new()
    s.end()
    assert s.phase == Phase.ENDED
    assert s.ended_at is not None
    assert store.active_count() == 0


def test_snapshot_shape():
    store = SessionStore()
    s = store.new(caller_id="+12")
    s.add_leg("user", "CA_x")
    snap = s.snapshot()
    assert snap["pair_id"] == s.pair_id
    assert snap["caller_id"] == "+12"
    assert "user" in snap["legs"]
    assert snap["cost_usd"] == 0.0


def test_dashboard_excludes_ended():
    store = SessionStore()
    a = store.new()
    b = store.new()
    b.end()
    dash = store.dashboard()
    assert dash["active_count"] == 1
    ids = {e["pair_id"] for e in dash["sessions"]}
    assert a.pair_id in ids
    assert b.pair_id not in ids


def test_purge_ended():
    store = SessionStore()
    s = store.new()
    s.add_leg("user", "CA1")
    store.bind_call(s.pair_id, "CA1")
    s.end()
    s.ended_at = 0  # ancient
    assert store.purge_ended(older_than_s=60) == 1
    assert store.by_call("CA1") is None


def test_mark_leg_left():
    store = SessionStore()
    s = store.new()
    s.add_leg("target", "CA_t")
    s.mark_leg_left("target")
    assert s.legs["target"].hung_up_at is not None
