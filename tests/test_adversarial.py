import threading

from reconcile import (
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


def marks(actions):
    return [item for item in actions if item["type"] == "mark_sold"]


def cancels(actions):
    return [item for item in actions if item["type"] == "cancel_order"]


def test_two_sales_in_one_call_do_not_double_mark_sold():
    orders = [
        [sale("a-stub", "stubhub", 1000), sale("z-via", "viagogo", 1000)],
        [sale("z-via", "viagogo", 1000), sale("a-stub", "stubhub", 1000)],
    ]
    for events in orders:
        actions = reconcile(listed(), events)
        assert types(actions).count("mark_sold") == 1
        assert len(marks(actions)) == 1
        assert marks(actions)[0]["event_id"] == "z-via"
        assert marks(actions)[0]["platform"] == "viagogo"
        assert marks(actions)[0]["expected_version"] == 1
        assert [item["event_id"] for item in cancels(actions)] == ["a-stub"]
        delisted = {item["platform"] for item in actions if item["type"] == "delist"}
        assert delisted == {"stubhub", "twickets"}
        assert "viagogo" not in delisted

        book = TicketBook(listed())
        committed = commit_sales(book, events)
        assert types(committed).count("mark_sold") == 1
        assert len(marks(committed)) == 1
        assert marks(committed)[0]["event_id"] == "z-via"
        assert book.ticket["state"] == "sold"
        assert book.ticket["version"] == 2
        assert book.ticket["winner_event_id"] == "z-via"
        assert book.ticket["listings"]["viagogo"] == "sold"
        sold_names = [
            name
            for name, status in book.ticket["listings"].items()
            if status == "sold"
        ]
        assert sold_names == ["viagogo"]
        assert len([row for row in book.log if row["to_state"] == "sold"]) == 1
        assert "a-stub" in book.ticket["applied_event_ids"]
        assert "z-via" in book.ticket["applied_event_ids"]


def test_replay_after_commit_returns_no_mark_sold_and_does_not_cancel_winner():
    book = TicketBook(listed())
    first = commit_sales(
        book,
        [sale("e-win", "viagogo", 10), sale("e-lose", "stubhub", 50)],
    )
    assert len(marks(first)) == 1
    assert marks(first)[0]["event_id"] == "e-win"
    winner = book.ticket["winner_event_id"]
    version = book.ticket["version"]
    outbox_len = len(book.outbox)
    replay = [
        sale("e-lose", "stubhub", 50),
        sale("e-win", "viagogo", 10),
        sale("e-win", "viagogo", 1),
        sale("e-win", "stubhub", 0),
    ]
    second = commit_sales(book, replay)
    assert second == []
    assert marks(second) == []
    assert cancels(second) == []
    assert not any(
        item["type"] == "cancel_order" and item["event_id"] == winner
        for item in second
    )
    assert book.ticket["winner_event_id"] == winner
    assert book.ticket["state"] == "sold"
    assert book.ticket["version"] == version
    assert book.ticket["listings"]["viagogo"] == "sold"
    assert len(book.outbox) == outbox_len
    assert not any(
        item["action"]["type"] == "cancel_order"
        and item["action"]["event_id"] == winner
        for item in book.outbox
    )
    assert commit_sales(book, [sale("e-win", "viagogo", 10)]) == []
    assert book.ticket["winner_event_id"] == "e-win"


def test_earlier_sold_at_wins_when_it_appears_second():
    events = [sale("a-late", "viagogo", 1000), sale("z-early", "stubhub", 999)]
    actions = reconcile(listed(), events)
    assert len(marks(actions)) == 1
    assert marks(actions)[0]["event_id"] == "z-early"
    assert marks(actions)[0]["platform"] == "stubhub"
    assert [item["event_id"] for item in cancels(actions)] == ["a-late"]
    assert cancels(actions)[0]["reason"] == "lost_tiebreak"
    assert "viagogo" in {
        item["platform"] for item in actions if item["type"] == "delist"
    }
    assert "stubhub" not in {
        item["platform"] for item in actions if item["type"] == "delist"
    }

    book = TicketBook(listed())
    committed = commit_sales(book, events)
    assert len(marks(committed)) == 1
    assert marks(committed)[0]["event_id"] == "z-early"
    assert types(committed).count("mark_sold") == 1
    assert book.ticket["winner_event_id"] == "z-early"
    assert book.ticket["listings"]["stubhub"] == "sold"
    assert book.ticket["listings"]["viagogo"] != "sold"
    assert book.ticket["state"] == "sold"
    assert book.ticket["version"] == 2


def test_sale_after_sold_is_cancelled_and_winner_stays():
    book = TicketBook(listed())
    commit_sales(book, [sale("z-committed", "stubhub", 800)])
    assert book.ticket["winner_event_id"] == "z-committed"
    assert book.ticket["version"] == 2
    assert book.ticket["listings"]["stubhub"] == "sold"

    late = commit_sales(book, [sale("a-older", "viagogo", 1)])
    assert types(late).count("mark_sold") == 0
    late_cancels = cancels(late)
    assert len(late_cancels) == 1
    assert late_cancels[0]["event_id"] == "a-older"
    assert late_cancels[0]["reason"] == "already_sold"
    assert not any(item["event_id"] == "z-committed" for item in late_cancels)
    assert book.ticket["winner_event_id"] == "z-committed"
    assert book.ticket["state"] == "sold"
    assert book.ticket["version"] == 2
    assert book.ticket["listings"]["stubhub"] == "sold"
    assert book.ticket["listings"]["viagogo"] == "active"
    assert "z-committed" in book.ticket["applied_event_ids"]
    assert "a-older" in book.ticket["applied_event_ids"]
    assert not any(
        item["action"]["type"] == "cancel_order"
        and item["action"]["event_id"] == "z-committed"
        for item in book.outbox
    )

    again = commit_sales(book, [sale("a-older", "viagogo", 1)])
    assert again == []
    assert book.ticket["winner_event_id"] == "z-committed"
    assert book.ticket["version"] == 2

    adapters = {
        "viagogo": FakePlatform(),
        "stubhub": FakePlatform(),
        "twickets": FakePlatform(),
    }
    flush_outbox(book, adapters)
    assert book.ticket["winner_event_id"] == "z-committed"
    assert book.ticket["state"] == "sold"
    assert book.ticket["version"] == 2
    assert book.ticket["listings"]["stubhub"] == "sold"
    assert book.ticket["listings"]["viagogo"] == "delisted"
    assert adapters["stubhub"].cancel_calls == []
    assert adapters["viagogo"].cancel_calls == ["t1"]


def test_delist_timeout_then_ok_while_other_platform_delists_on_first_flush():
    book = TicketBook(listed())
    commit_sales(book, [sale("e1", "viagogo", 10)])
    assert book.ticket["listings"]["viagogo"] == "sold"
    stubhub = FakePlatform(delist_results=["timeout", "ok"])
    twickets = FakePlatform()
    viagogo = FakePlatform()
    adapters = {
        "viagogo": viagogo,
        "stubhub": stubhub,
        "twickets": twickets,
    }

    flush_outbox(book, adapters)
    assert stubhub.delist_calls == ["t1"]
    assert twickets.delist_calls == ["t1"]
    assert viagogo.delist_calls == []
    assert book.ticket["listings"]["stubhub"] == "active"
    assert book.ticket["listings"]["twickets"] == "delisted"
    assert book.ticket["listings"]["viagogo"] == "sold"
    assert book.ticket["state"] == "sold"
    assert book.ticket["winner_event_id"] == "e1"
    assert book.ticket["version"] == 2
    assert book.alerts == []
    pending = [
        item for item in book.outbox if item["action"]["platform"] == "stubhub"
    ]
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"
    assert pending[0]["attempts"] == 1
    assert pending[0]["action"]["type"] == "delist"
    assert all(item["action"]["platform"] != "twickets" for item in book.outbox)
    assert len(book.outbox) == 1

    flush_outbox(book, adapters)
    assert stubhub.delist_calls == ["t1", "t1"]
    assert twickets.delist_calls == ["t1"]
    assert book.ticket["listings"]["stubhub"] == "delisted"
    assert book.ticket["listings"]["twickets"] == "delisted"
    assert book.ticket["listings"]["viagogo"] == "sold"
    assert book.outbox == []
    assert book.alerts == []
    assert book.ticket["state"] == "sold"
    assert book.ticket["version"] == 2
    assert book.ticket["winner_event_id"] == "e1"
    assert len([row for row in book.log if row["from_state"] != row["to_state"]]) == 1


def test_two_threads_one_mark_sold():
    for trial in range(25):
        book = TicketBook(listed())
        gate = threading.Barrier(2)
        found = []
        errors = []
        guard = threading.Lock()

        def run(
            event,
            book=book,
            gate=gate,
            found=found,
            errors=errors,
            guard=guard,
        ):
            gate.wait()
            try:
                actions = commit_sales(book, [event])
            except Exception as exc:
                with guard:
                    errors.append(repr(exc))
                return
            with guard:
                found.append(actions)

        via_id = f"e-via-{trial}"
        stub_id = f"e-stub-{trial}"
        first = threading.Thread(
            target=run,
            args=(sale(via_id, "viagogo", 400),),
        )
        second = threading.Thread(
            target=run,
            args=(sale(stub_id, "stubhub", 100),),
        )
        first.daemon = True
        second.daemon = True
        first.start()
        second.start()
        first.join(5)
        second.join(5)
        assert not first.is_alive()
        assert not second.is_alive()
        assert errors == []
        assert len(found) == 2
        sold_marks = [
            item
            for batch in found
            for item in batch
            if item["type"] == "mark_sold"
        ]
        sold_cancels = [
            item
            for batch in found
            for item in batch
            if item["type"] == "cancel_order"
        ]
        assert len(sold_marks) == 1
        assert len(sold_cancels) == 1
        assert sold_cancels[0]["event_id"] != sold_marks[0]["event_id"]
        assert sold_cancels[0]["reason"] == "already_sold"
        assert book.ticket["state"] == "sold"
        assert book.ticket["version"] == 2
        assert book.ticket["winner_event_id"] == sold_marks[0]["event_id"]
        assert len([row for row in book.log if row["to_state"] == "sold"]) == 1
        assert via_id in book.ticket["applied_event_ids"]
        assert stub_id in book.ticket["applied_event_ids"]
        out_cancels = [
            item["action"]["event_id"]
            for item in book.outbox
            if item["action"]["type"] == "cancel_order"
        ]
        assert out_cancels == [sold_cancels[0]["event_id"]]
        assert sold_marks[0]["event_id"] not in out_cancels
        sold_names = [
            name
            for name, status in book.ticket["listings"].items()
            if status == "sold"
        ]
        assert sold_names == [sold_marks[0]["platform"]]
