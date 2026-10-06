import copy
import random
import threading

from reconcile import (
    cas_transition,
    commit_sales,
    flush_outbox,
    reconcile,
    FakePlatform,
    TicketBook,
)


def listed(version=1, listings=None):
    return {
        "ticket_id": "t1",
        "state": "listed",
        "version": version,
        "listings": listings
        or {"viagogo": "active", "stubhub": "active", "twickets": "active"},
        "applied_event_ids": [],
        "winner_event_id": None,
    }


def sale(event_id, platform, sold_at, ticket_id="t1"):
    return {
        "event_id": event_id,
        "ticket_id": ticket_id,
        "platform": platform,
        "sold_at": sold_at,
        "kind": "sale",
    }


def types(actions):
    return [item["type"] for item in actions]


def test_two_sales_same_timestamp_platform_priority():
    actions = reconcile(
        listed(),
        [sale("e-stub", "stubhub", 1000), sale("e-via", "viagogo", 1000)],
    )
    marks = [item for item in actions if item["type"] == "mark_sold"]
    assert len(marks) == 1
    assert marks[0]["platform"] == "viagogo"
    assert marks[0]["event_id"] == "e-via"
    assert marks[0]["expected_version"] == 1
    cancels = [item for item in actions if item["type"] == "cancel_order"]
    assert len(cancels) == 1
    assert cancels[0]["event_id"] == "e-stub"
    delisted = {item["platform"] for item in actions if item["type"] == "delist"}
    assert delisted == {"stubhub", "twickets"}
    assert "viagogo" not in delisted


def test_earlier_timestamp_wins_even_if_it_is_listed_second():
    actions = reconcile(
        listed(),
        [sale("late", "viagogo", 500), sale("early", "stubhub", 100)],
    )
    marks = [item for item in actions if item["type"] == "mark_sold"]
    assert marks[0]["event_id"] == "early"
    assert marks[0]["platform"] == "stubhub"


def test_duplicate_event_is_idempotent():
    state = listed()
    events = [sale("e1", "viagogo", 10), sale("e1", "viagogo", 10)]
    once = reconcile(state, events)
    assert types(once).count("mark_sold") == 1
    book = TicketBook(listed())
    first = commit_sales(book, events)
    second = commit_sales(book, events)
    assert types(first).count("mark_sold") == 1
    assert second == []
    assert book.ticket["applied_event_ids"] == ["e1"]
    assert book.ticket["state"] == "sold"
    assert book.ticket["version"] == 2


def test_replay_after_sold_does_not_cancel_the_winner():
    book = TicketBook(listed())
    commit_sales(book, [sale("e1", "viagogo", 10), sale("e2", "stubhub", 20)])
    again = reconcile(
        book.ticket,
        [sale("e1", "viagogo", 10), sale("e2", "stubhub", 20)],
    )
    assert again == []


def test_late_event_after_commit_is_cancelled():
    book = TicketBook(listed())
    commit_sales(book, [sale("e1", "viagogo", 300)])
    flush_outbox(
        book,
        {
            "stubhub": FakePlatform(),
            "twickets": FakePlatform(),
            "viagogo": FakePlatform(),
        },
    )
    late = reconcile(book.ticket, [sale("e-early", "stubhub", 100)])
    assert [item["type"] for item in late] == ["cancel_order"]
    assert late[0]["reason"] == "already_sold"
    assert book.ticket["winner_event_id"] == "e1"


def test_illegal_transition_and_version_conflict():
    ticket = {
        "ticket_id": "t1",
        "state": "sourced",
        "version": 0,
        "listings": {},
        "applied_event_ids": [],
        "winner_event_id": None,
    }
    ok, reason = cas_transition(ticket, 0, "sold")
    assert ok is False
    assert reason == "illegal_transition"
    assert ticket["state"] == "sourced"
    assert ticket["version"] == 0

    listed_ticket = listed(version=4)
    ok, reason = cas_transition(listed_ticket, 3, "sold")
    assert ok is False
    assert reason == "version_conflict"
    assert listed_ticket["version"] == 4
    assert listed_ticket["state"] == "listed"


def test_lifecycle_only_moves_one_step():
    ticket = {
        "ticket_id": "t1",
        "state": "sourced",
        "version": 0,
        "listings": {},
        "applied_event_ids": [],
        "winner_event_id": None,
    }
    for new_state in ("bought", "listed", "sold", "delivered"):
        ok, ticket = cas_transition(ticket, ticket["version"], new_state)
        assert ok is True
    assert ticket["state"] == "delivered"
    assert ticket["version"] == 4
    ok, reason = cas_transition(ticket, ticket["version"], "listed")
    assert ok is False
    assert reason == "illegal_transition"


def test_sale_before_listed_is_rejected():
    ticket = listed()
    ticket["state"] = "bought"
    actions = reconcile(ticket, [sale("e1", "viagogo", 10)])
    assert actions[0]["type"] == "reject_event"
    assert actions[0]["reason"] == "not_listed"
    book = TicketBook(ticket)
    commit_sales(book, [sale("e1", "viagogo", 10)])
    assert book.ticket["state"] == "bought"
    assert commit_sales(book, [sale("e1", "viagogo", 10)]) == []


def test_delist_timeout_then_retry():
    book = TicketBook(listed())
    commit_sales(
        book,
        [sale("e1", "viagogo", 10), sale("e2", "stubhub", 20)],
    )
    stubhub = FakePlatform(delist_results=["timeout", "ok"])
    others = {
        "viagogo": FakePlatform(),
        "stubhub": stubhub,
        "twickets": FakePlatform(),
    }
    flush_outbox(book, others)
    assert stubhub.delist_calls == ["t1"]
    assert book.ticket["listings"]["stubhub"] == "active"
    assert book.ticket["listings"]["viagogo"] == "sold"
    assert any(item["action"]["platform"] == "stubhub" for item in book.outbox)
    flush_outbox(book, others)
    assert book.ticket["listings"]["stubhub"] == "delisted"
    assert book.outbox == []
    assert book.alerts == []


def test_delist_gives_up_after_three_failures():
    book = TicketBook(listed())
    commit_sales(book, [sale("e1", "viagogo", 10)])
    stubhub = FakePlatform(delist_results=["timeout", "fail", "timeout"])
    twickets = FakePlatform(delist_results=["ok"])
    adapters = {
        "viagogo": FakePlatform(),
        "stubhub": stubhub,
        "twickets": twickets,
    }
    flush_outbox(book, adapters)
    flush_outbox(book, adapters)
    flush_outbox(book, adapters)
    assert book.ticket["listings"]["stubhub"] == "active"
    assert book.ticket["listings"]["twickets"] == "delisted"
    assert book.outbox == []
    assert len(stubhub.delist_calls) == 3
    assert any(item["platform"] == "stubhub" for item in book.alerts)
    assert book.ticket["state"] == "sold"


def test_reconcile_does_not_mutate_inputs():
    state = listed()
    events = [sale("e1", "stubhub", 5), sale("e2", "viagogo", 5)]
    before_state = copy.deepcopy(state)
    before_events = copy.deepcopy(events)
    reconcile(state, events)
    assert state == before_state
    assert events == before_events


def test_threads_allow_one_sale():
    book = TicketBook(listed())
    gate = threading.Barrier(2)
    found = []
    guard = threading.Lock()

    def run(event):
        gate.wait()
        actions = commit_sales(book, [event])
        with guard:
            found.append(actions)

    first = threading.Thread(target=run, args=(sale("e1", "viagogo", 100),))
    second = threading.Thread(target=run, args=(sale("e2", "stubhub", 100),))
    first.start()
    second.start()
    first.join(5)
    second.join(5)
    assert not first.is_alive()
    assert not second.is_alive()
    marks = [
        item
        for batch in found
        for item in batch
        if item["type"] == "mark_sold"
    ]
    cancels = [
        item
        for batch in found
        for item in batch
        if item["type"] == "cancel_order"
    ]
    assert len(marks) == 1
    assert len(cancels) == 1
    assert book.ticket["state"] == "sold"
    assert book.ticket["version"] == 2
    assert book.ticket["winner_event_id"] == marks[0]["event_id"]


def test_seeded_property_one_winner_and_replay():
    rng = random.Random(20261006)
    platforms = ["viagogo", "stubhub", "twickets", "other"]
    for trial in range(40):
        events = []
        for index in range(rng.randint(1, 8)):
            events.append(
                sale(
                    f"t{trial}-e{index}",
                    rng.choice(platforms),
                    rng.randint(0, 50),
                )
            )
        if rng.random() < 0.3 and events:
            events.append(dict(events[0]))
        state = listed()
        before = copy.deepcopy(state)
        first = reconcile(state, events)
        second = reconcile(state, events)
        assert first == second
        assert state == before
        marks = [item for item in first if item["type"] == "mark_sold"]
        assert len(marks) == 1
        winner = marks[0]
        delisted = {item["platform"] for item in first if item["type"] == "delist"}
        assert winner["platform"] not in delisted
        assert delisted == {"viagogo", "stubhub", "twickets"} - {winner["platform"]}
        best = None
        seen = set()
        order = {"viagogo": 0, "stubhub": 1, "twickets": 2}
        for event in events:
            if event["event_id"] in seen:
                continue
            seen.add(event["event_id"])
            if best is None:
                best = event
                continue
            if event["sold_at"] < best["sold_at"]:
                best = event
                continue
            if event["sold_at"] > best["sold_at"]:
                continue
            event_rank = order.get(event["platform"], 3)
            best_rank = order.get(best["platform"], 3)
            if event_rank < best_rank:
                best = event
                continue
            if event_rank > best_rank:
                continue
            if str(event["event_id"]) < str(best["event_id"]):
                best = event
        assert winner["event_id"] == best["event_id"]
        book = TicketBook(copy.deepcopy(state))
        commit_sales(book, events)
        assert reconcile(book.ticket, events) == []
        assert book.ticket["state"] == "sold"
        assert book.ticket["version"] == 2


def test_log_appends_and_keeps_old_rows():
    book = TicketBook(listed())
    commit_sales(book, [sale("e1", "viagogo", 10)])
    first = list(book.log)
    assert first[0]["to_state"] == "sold"
    flush_outbox(
        book,
        {
            "viagogo": FakePlatform(),
            "stubhub": FakePlatform(),
            "twickets": FakePlatform(),
        },
    )
    assert book.log[: len(first)] == first
    assert len(book.log) > len(first)
    assert book.log[-1]["result"] == "ok"


def test_bool_timestamp_is_rejected():
    try:
        reconcile(listed(), [sale("e1", "viagogo", True)])
    except TypeError as exc:
        assert "sold_at" in str(exc)
    else:
        raise AssertionError("bool timestamp was accepted")
