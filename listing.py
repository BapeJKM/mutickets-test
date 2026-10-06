def listing_key(ticket_id, platform):
    return f"{ticket_id}:{platform}"


def create_listing(store, ticket_id, platform, price):
    key = listing_key(ticket_id, platform)
    if key in store:
        return {"ok": False, "key": key, "reason": "already_listed"}
    store[key] = {
        "ticket_id": ticket_id,
        "platform": platform,
        "price": price,
        "status": "active",
    }
    return {"ok": True, "key": key, "reason": "created"}
