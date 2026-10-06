from discover import sample_event
from listing import create_listing
from pricing import price_for_margin
from purchase import run_purchase
from reconcile import (
    FakePlatform,
    TicketBook,
    cas_transition,
    commit_sales,
    flush_outbox,
)


def _line(text, lines):
    lines.append(text)


def run_demo():
    lines = []
    event = sample_event()
    _line("1 source", lines)
    _line(f"event {event['event']}", lines)
    _line(f"date {event['date']}", lines)
    _line(f"venue {event['venue']}", lines)
    _line("sections not obtained", lines)
    _line("primary price not obtained", lines)
    _line("availability not obtained", lines)
    _line(f"limit {event['limit']}", lines)

    ledger = {"attempts": {}}
    bought = run_purchase("t1", "a1", {}, ledger, quantity=1, limit=event["limit"])
    _line("2 purchase", lines)
    _line(
        f"attempt {bought['attempt_id']} status {bought['status']} reason {bought['reason']}",
        lines,
    )
    for row in bought["trace"]:
        _line(
            f"state {row['state']} result {row['result']} detail {row['detail']} proxy {row['proxy_id']}",
            lines,
        )

    cost = 100.0
    via = price_for_margin(cost, 0.12, 0.15)
    stub = price_for_margin(cost, 0.09, 0.15)
    _line("3 price", lines)
    _line("cost 100.00 is an example, not the event face value", lines)
    _line(f"viagogo brief fee 0.12 list {via:.2f}", lines)
    _line(f"stubhub brief fee 0.09 list {stub:.2f}", lines)

    store = {}
    first = create_listing(store, "t1", "viagogo", via)
    second = create_listing(store, "t1", "stubhub", stub)
    again = create_listing(store, "t1", "viagogo", via)
    _line("4 list", lines)
    _line(f"viagogo {first['key']} {first['reason']}", lines)
    _line(f"stubhub {second['key']} {second['reason']}", lines)
    _line(f"viagogo again {again['reason']}", lines)

    ticket = {
        "ticket_id": "t1",
        "state": "sourced",
        "version": 0,
        "listings": {},
        "applied_event_ids": [],
        "winner_event_id": None,
    }
    ok, ticket = cas_transition(ticket, 0, "bought")
    if not ok:
        raise RuntimeError(ticket)
    ticket["listings"] = {"viagogo": "active", "stubhub": "active"}
    ok, ticket = cas_transition(ticket, ticket["version"], "listed")
    if not ok:
        raise RuntimeError(ticket)

    book = TicketBook(ticket)
    actions = commit_sales(
        book,
        [
            {
                "event_id": "e1",
                "ticket_id": "t1",
                "platform": "viagogo",
                "sold_at": 10,
                "kind": "sale",
            }
        ],
    )
    flush_outbox(
        book,
        {"viagogo": FakePlatform(), "stubhub": FakePlatform()},
    )
    _line("5 sale", lines)
    for action in actions:
        _line(f"action {action['type']} platform {action['platform']}", lines)
    _line(f"ticket state {book.ticket['state']}", lines)
    _line(f"viagogo listing {book.ticket['listings']['viagogo']}", lines)
    _line(f"stubhub listing {book.ticket['listings']['stubhub']}", lines)

    failed = run_purchase(
        "t1",
        "a2",
        {"queue": "expired"},
        ledger,
        quantity=1,
        limit=event["limit"],
    )
    unknown = run_purchase(
        "t1",
        "a3",
        {"proxy": "died"},
        ledger,
        quantity=1,
        limit=event["limit"],
    )
    repeat = run_purchase(
        "t1",
        "a3",
        {"proxy": "ok", "pay": "ok"},
        ledger,
        quantity=1,
        limit=event["limit"],
    )
    _line("6 failure stubs", lines)
    _line(f"queue {failed['status']} {failed['reason']}", lines)
    _line(f"proxy {unknown['status']} {unknown['reason']}", lines)
    _line(
        f"repeat status {repeat['status']} reason {repeat['reason']} repeated_charge {repeat['repeated_charge']}",
        lines,
    )
    return lines


def main():
    print("\n".join(run_demo()))


if __name__ == "__main__":
    main()
