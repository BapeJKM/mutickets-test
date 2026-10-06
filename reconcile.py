import threading

PRIORITY = ("viagogo", "stubhub", "twickets")

MAX_ATTEMPTS = 3

LEGAL = {
    "sourced": "bought",
    "bought": "listed",
    "listed": "sold",
    "sold": "delivered",
}


def platform_rank(name):
    try:
        return PRIORITY.index(name)
    except ValueError:
        return len(PRIORITY)


def sale_beats(left, right):
    if left["sold_at"] != right["sold_at"]:
        return left["sold_at"] < right["sold_at"]
    left_rank = platform_rank(left["platform"])
    right_rank = platform_rank(right["platform"])
    if left_rank != right_rank:
        return left_rank < right_rank
    return str(left["event_id"]) < str(right["event_id"])


def _action(kind, ticket_id, event_id, platform, reason, expected_version):
    return {
        "type": kind,
        "ticket_id": ticket_id,
        "event_id": event_id,
        "platform": platform,
        "reason": reason,
        "expected_version": expected_version,
    }


def _add_delist(actions, ticket_id, event_id, platform, reason):
    for existing in actions:
        if existing["type"] == "delist" and existing["platform"] == platform:
            return
    actions.append(
        _action("delist", ticket_id, event_id, platform, reason, None)
    )


def reconcile(known_state, incoming_sale_events):
    seen = set(known_state["applied_event_ids"])
    fresh = []
    for event in incoming_sale_events:
        if event.get("kind", "sale") != "sale":
            continue
        if event["ticket_id"] != known_state["ticket_id"]:
            continue
        if type(event["sold_at"]) is not int:
            raise TypeError("sold_at must be an integer millisecond timestamp")
        if event["event_id"] in seen:
            continue
        fresh.append(event)
        seen.add(event["event_id"])

    if not fresh:
        return []

    state = known_state["state"]
    listings = known_state["listings"]
    ticket_id = known_state["ticket_id"]

    if state in ("sold", "delivered"):
        actions = []
        for event in fresh:
            actions.append(
                _action(
                    "cancel_order",
                    ticket_id,
                    event["event_id"],
                    event["platform"],
                    "already_sold",
                    None,
                )
            )
            if listings.get(event["platform"]) == "active":
                _add_delist(
                    actions,
                    ticket_id,
                    event["event_id"],
                    event["platform"],
                    "already_sold",
                )
        return actions

    if state != "listed":
        return [
            _action(
                "reject_event",
                ticket_id,
                event["event_id"],
                event["platform"],
                "not_listed",
                None,
            )
            for event in fresh
        ]

    winner = fresh[0]
    for event in fresh[1:]:
        if sale_beats(event, winner):
            winner = event

    actions = [
        _action(
            "mark_sold",
            ticket_id,
            winner["event_id"],
            winner["platform"],
            "winner",
            known_state["version"],
        )
    ]
    for event in fresh:
        if event["event_id"] == winner["event_id"]:
            continue
        actions.append(
            _action(
                "cancel_order",
                ticket_id,
                event["event_id"],
                event["platform"],
                "lost_tiebreak",
                None,
            )
        )
    for platform, status in listings.items():
        if status != "active":
            continue
        if platform == winner["platform"]:
            continue
        _add_delist(
            actions,
            ticket_id,
            winner["event_id"],
            platform,
            "winner_elsewhere",
        )
    return actions


def cas_transition(ticket, expected_version, new_state):
    if ticket["version"] != expected_version:
        return False, "version_conflict"
    if LEGAL.get(ticket["state"]) != new_state:
        return False, "illegal_transition"
    nxt = {
        "ticket_id": ticket["ticket_id"],
        "state": new_state,
        "version": ticket["version"] + 1,
        "listings": dict(ticket["listings"]),
        "applied_event_ids": list(ticket["applied_event_ids"]),
        "winner_event_id": ticket.get("winner_event_id"),
    }
    return True, nxt


class FakePlatform:
    def __init__(self, delist_results=None, cancel_results=None):
        self._delist = list(delist_results or [])
        self._cancel = list(cancel_results or [])
        self.delist_calls = []
        self.cancel_calls = []

    def delist(self, ticket_id):
        self.delist_calls.append(ticket_id)
        if self._delist:
            return self._delist.pop(0)
        return "ok"

    def cancel(self, ticket_id):
        self.cancel_calls.append(ticket_id)
        if self._cancel:
            return self._cancel.pop(0)
        return "ok"


class TicketBook:
    def __init__(self, ticket):
        self.lock = threading.Lock()
        self.ticket = ticket
        self.outbox = []
        self.alerts = []
        self.log = []


def _remember(ticket, event_id):
    ids = list(ticket["applied_event_ids"])
    if event_id not in ids:
        ids.append(event_id)
    ticket["applied_event_ids"] = ids


def _enqueue(book, action):
    if action["type"] == "delist":
        key = ("delist", action["platform"], action["ticket_id"])
    else:
        key = (
            action["type"],
            action["platform"],
            action["ticket_id"],
            action["event_id"],
        )
    for item in book.outbox:
        if item["key"] == key:
            return
    book.outbox.append(
        {
            "key": key,
            "action": action,
            "attempts": 0,
            "status": "pending",
        }
    )


def commit_sales(book, events):
    with book.lock:
        actions = reconcile(book.ticket, events)
        kept = []
        for action in actions:
            if action["type"] == "mark_sold":
                ok, nxt = cas_transition(
                    book.ticket,
                    action["expected_version"],
                    "sold",
                )
                if not ok:
                    return kept
                old_state = book.ticket["state"]
                nxt["listings"] = dict(nxt["listings"])
                nxt["listings"][action["platform"]] = "sold"
                nxt["winner_event_id"] = action["event_id"]
                book.ticket = nxt
                _remember(book.ticket, action["event_id"])
                book.log.append(
                    {
                        "ticket_id": nxt["ticket_id"],
                        "from_state": old_state,
                        "to_state": "sold",
                        "version": nxt["version"],
                        "event_id": action["event_id"],
                    }
                )
                kept.append(action)
                continue
            if action["type"] in ("cancel_order", "delist"):
                _enqueue(book, action)
                _remember(book.ticket, action["event_id"])
                kept.append(action)
                continue
            if action["type"] == "reject_event":
                _remember(book.ticket, action["event_id"])
                kept.append(action)
        return kept


def flush_outbox(book, adapters):
    with book.lock:
        for item in list(book.outbox):
            if item["status"] != "pending":
                continue
            action = item["action"]
            platform = action["platform"]
            adapter = adapters.get(platform)
            if adapter is None:
                item["status"] = "failed"
                book.alerts.append(
                    {
                        "type": "missing_adapter",
                        "platform": platform,
                        "ticket_id": action["ticket_id"],
                    }
                )
                continue
            if action["type"] == "delist":
                result = adapter.delist(action["ticket_id"])
            elif action["type"] == "cancel_order":
                result = adapter.cancel(action["ticket_id"])
            else:
                item["status"] = "done"
                continue
            item["attempts"] += 1
            if result == "ok":
                item["status"] = "done"
                if action["type"] == "delist":
                    listings = dict(book.ticket["listings"])
                    listings[platform] = "delisted"
                    book.ticket["listings"] = listings
                book.log.append(
                    {
                        "ticket_id": action["ticket_id"],
                        "from_state": book.ticket["state"],
                        "to_state": book.ticket["state"],
                        "version": book.ticket["version"],
                        "event_id": action["event_id"],
                        "platform": platform,
                        "result": "ok",
                    }
                )
                continue
            if item["attempts"] >= MAX_ATTEMPTS:
                item["status"] = "failed"
                book.alerts.append(
                    {
                        "type": "gave_up",
                        "platform": platform,
                        "ticket_id": action["ticket_id"],
                        "action": action["type"],
                        "attempts": item["attempts"],
                    }
                )
                book.log.append(
                    {
                        "ticket_id": action["ticket_id"],
                        "from_state": book.ticket["state"],
                        "to_state": book.ticket["state"],
                        "version": book.ticket["version"],
                        "event_id": action["event_id"],
                        "platform": platform,
                        "result": "gave_up",
                    }
                )
        book.outbox = [
            item for item in book.outbox if item["status"] == "pending"
        ]
