def run_purchase(ticket_id, attempt_id, outcomes, ledger, quantity=1, limit=6):
    prior = ledger["attempts"].get(attempt_id)
    if prior is not None and prior["status"] in ("unknown", "bought", "failed"):
        return {
            "ticket_id": ticket_id,
            "attempt_id": attempt_id,
            "status": prior["status"],
            "reason": "already_finished",
            "repeated_charge": False,
            "alert": False,
            "account": prior["account"],
            "proxy_id": prior["proxy_id"],
            "trace": [],
        }

    account = outcomes.get("account", "buyer-1")
    proxy_id = outcomes.get("proxy_id", "uk-sticky-1")
    trace = []

    def rec(state, result, detail):
        trace.append(
            {
                "state": state,
                "result": result,
                "detail": detail,
                "account": account,
                "proxy_id": proxy_id,
            }
        )

    def finish(status, reason, alert):
        ledger["attempts"][attempt_id] = {
            "status": status,
            "reason": reason,
            "account": account,
            "proxy_id": proxy_id,
        }
        return {
            "ticket_id": ticket_id,
            "attempt_id": attempt_id,
            "status": status,
            "reason": reason,
            "repeated_charge": False,
            "alert": alert,
            "account": account,
            "proxy_id": proxy_id,
            "trace": trace,
        }

    rec("idle", "ok", "start")
    if quantity > limit:
        rec("failed", "stopped", "over_limit")
        return finish("failed", "over_limit", True)

    queue = outcomes.get("queue", "ok")
    rec("queued", queue, "waiting_room")
    if queue != "ok":
        rec("idle", "stopped", "queue_expired")
        return finish("idle", "queue_expired", False)

    cart = outcomes.get("cart", "ok")
    rec("cart_held", cart, "reserve")
    if cart != "ok":
        rec("failed", "stopped", "cart_released")
        return finish("failed", "cart_expired", True)

    captcha = outcomes.get("captcha", "ok")
    rec("captcha_required", captcha, "stub")
    if captcha != "ok":
        rec("failed", "stopped", "captcha_stopped")
        return finish("failed", "captcha_stopped", True)

    rec("paying", "started", "one_stub_charge")
    proxy = outcomes.get("proxy", "ok")
    if proxy != "ok":
        rec("unknown", "stopped", "proxy_died")
        return finish("unknown", "proxy_died", True)

    pay = outcomes.get("pay", "ok")
    rec("paying", pay, "stub_result")
    if pay == "unknown":
        rec("unknown", "stopped", "no_response")
        return finish("unknown", "no_response", True)
    if pay != "ok":
        rec("failed", "stopped", "declined")
        return finish("failed", "declined", True)

    rec("bought", "ok", "stub_paid")
    return finish("bought", "stub_paid", False)
