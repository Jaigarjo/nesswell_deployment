"""The deeper layer: per-factor details on a check-in."""


def put(client, h, body, day="2026-09-10", kind="evening"):
    return client.put(f"/entries/{day}/{kind}", headers=h, json=body)


def test_details_roundtrip_and_cleaning(client, auth_header):
    h, _ = auth_header()
    r = put(client, h, {"score": 7, "values": {"exercise": 1, "diet_quality": 4}, "details": {
        "exercise": {"note": "  Felt strong  ", "data": {"type": "Run", "minutes": 35, "intensity": "Hard"}},
        "diet_quality": {"data": {"amount": "About right", "food": ["Sweets", "Home-cooked", "Sweets"], "meals": None}},
        "social": {"note": "   ", "data": {"who": []}},  # empty: dropped
    }})
    assert r.status_code == 200, r.text
    d = r.json()["details"]
    assert d["exercise"] == {"note": "Felt strong", "data": {"type": "Run", "minutes": 35, "intensity": "Hard"}}
    assert d["diet_quality"]["data"] == {"amount": "About right", "food": ["Home-cooked", "Sweets"]}  # deduped, ordered
    assert "social" not in d
    got = client.get("/entries/2026-09-10/evening", headers=h).json()
    assert got["details"] == d


def test_details_replaced_on_save(client, auth_header):
    h, _ = auth_header()
    put(client, h, {"score": 6, "details": {"alcohol": {"data": {"drinks": 3}}}}, day="2026-09-11")
    r = put(client, h, {"score": 6, "details": {"work_stress": {"data": {"hours": 9.5}}}}, day="2026-09-11").json()
    assert set(r["details"]) == {"work_stress"}


def test_details_validation(client, auth_header):
    h, _ = auth_header()
    bad = [
        {"exercise": {"data": {"type": "Skydiving"}}},              # not an option
        {"exercise": {"data": {"minutes": 900}}},                   # out of range
        {"exercise": {"data": {"minutes": True}}},                  # bool isn't a number
        {"exercise": {"data": {"mood": "great"}}},                  # unknown field
        {"alcohol": {"data": {"type": ["Beer", "Mead"]}}},          # bad multi option
        {"sleep_hours": {"data": {"bedtime": "23:30"}}},            # morning factor on evening check-in
        {"made_up": {"note": "x"}},                                 # unknown factor
        {"exercise": {"note": "x" * 1001}},                         # note too long
    ]
    for details in bad:
        assert put(client, h, {"score": 5, "details": details}).status_code == 422, details


def test_time_fields(client, auth_header):
    h, _ = auth_header()
    ok = put(client, h, {"score": 6, "details": {"sleep_hours": {"data": {"bedtime": "23:45", "wake": "07:10"}}}},
             kind="morning")
    assert ok.status_code == 200
    bad = put(client, h, {"score": 6, "details": {"sleep_hours": {"data": {"bedtime": "25:00"}}}}, kind="morning")
    assert bad.status_code == 422


def test_schemas_exposed_and_private(client, auth_header):
    h, _ = auth_header()
    f = {x["key"]: x for x in client.get("/factors", headers=h).json()}
    diet = {fld["key"]: fld for fld in f["diet_quality"]["detail_schema"]}
    assert diet["amount"]["type"] == "choice" and "About right" in diet["amount"]["options"]
    assert f["g_hrv"]["detail_schema"] is None

    other, _ = auth_header()
    put(client, h, {"score": 5, "details": {"exercise": {"note": "private"}}}, day="2026-09-12")
    assert client.get("/entries/2026-09-12/evening", headers=other).status_code == 404
