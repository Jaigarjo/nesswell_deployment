from datetime import date, timedelta


def test_save_and_read_back(client, auth_header):
    h, _ = auth_header()
    body = {"score": 7, "note": "slept ok", "values": {"sleep_hours": 7.5, "sleep_quality": 4}}
    r = client.put("/entries/2026-09-01/morning", json=body, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["values"] == {"sleep_hours": 7.5, "sleep_quality": 4}

    got = client.get("/entries/2026-09-01/morning", headers=h).json()
    assert got["score"] == 7 and got["note"] == "slept ok"


def test_save_replaces_existing(client, auth_header):
    h, _ = auth_header()
    client.put("/entries/2026-09-02/evening", json={"score": 5, "values": {"exercise": 1, "alcohol": 1}}, headers=h)
    r = client.put("/entries/2026-09-02/evening", json={"score": 8, "values": {"exercise": 1}}, headers=h).json()
    assert r["score"] == 8 and r["values"] == {"exercise": 1}  # alcohol removed


def test_validation(client, auth_header):
    h, _ = auth_header()
    cases = [
        {"score": 11},
        {"score": 0},
        {"score": 5, "values": {"made_up": 1}},
        {"score": 5, "values": {"exercise": 1}},        # evening factor on morning
        {"score": 5, "values": {"sleep_hours": 30}},    # above max
        {"score": 5, "values": {"sleep_quality": 2.5}}, # scale must be whole
    ]
    for body in cases:
        assert client.put("/entries/2026-09-03/morning", json=body, headers=h).status_code == 422, body
    assert client.put("/entries/2026-09-03/lunch", json={"score": 5}, headers=h).status_code == 422
    assert client.put("/entries/2026-09-03/evening", json={"score": 5, "values": {"exercise": 2}}, headers=h).status_code == 422


def test_any_past_date_but_not_future(client, auth_header):
    h, _ = auth_header()
    today = date.fromisoformat(client.get("/me", headers=h).json()["today"])
    assert client.put(f"/entries/{today}/morning", json={"score": 6}, headers=h).status_code == 200
    assert client.put("/entries/2019-03-14/morning", json={"score": 6}, headers=h).status_code == 200
    tomorrow = today + timedelta(days=1)
    assert client.put(f"/entries/{tomorrow}/morning", json={"score": 6}, headers=h).status_code == 422


def test_list_range_and_order(client, auth_header):
    h, _ = auth_header()
    for d, k, s in [("2026-08-10", "evening", 6), ("2026-08-10", "morning", 4), ("2026-08-12", "morning", 9)]:
        client.put(f"/entries/{d}/{k}", json={"score": s}, headers=h)
    rows = client.get("/entries?start=2026-08-01&end=2026-08-31", headers=h).json()
    assert [(r["day"], r["kind"]) for r in rows] == [
        ("2026-08-12", "morning"), ("2026-08-10", "morning"), ("2026-08-10", "evening")]
    assert client.get("/entries?start=2026-08-31&end=2026-08-01", headers=h).status_code == 422


def test_users_cannot_see_or_delete_each_other(client, auth_header):
    alice, _ = auth_header()
    bob, _ = auth_header()
    client.put("/entries/2026-09-05/morning", json={"score": 3}, headers=alice)
    assert client.get("/entries/2026-09-05/morning", headers=bob).status_code == 404
    assert client.get("/entries?start=2026-09-01&end=2026-09-30", headers=bob).json() == []
    assert client.delete("/entries/2026-09-05/morning", headers=bob).status_code == 404
    assert client.get("/entries/2026-09-05/morning", headers=alice).status_code == 200


def test_delete(client, auth_header):
    h, _ = auth_header()
    client.put("/entries/2026-09-06/evening", json={"score": 4, "values": {"social": 1}}, headers=h)
    assert client.delete("/entries/2026-09-06/evening", headers=h).status_code == 204
    assert client.get("/entries/2026-09-06/evening", headers=h).status_code == 404
