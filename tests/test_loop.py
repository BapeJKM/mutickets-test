from demo_loop import run_demo
from listing import create_listing
from pricing import margin_at, price_for_margin, undercut
from purchase import run_purchase


def ledger():
    return {"attempts": {}}


def test_purchase_happy_path_is_a_stub():
    result = run_purchase("t1", "a1", {}, ledger(), quantity=2, limit=6)
    assert result["status"] == "bought"
    assert result["reason"] == "stub_paid"
    assert result["repeated_charge"] is False
    states = [row["state"] for row in result["trace"]]
    assert states == [
        "idle",
        "queued",
        "cart_held",
        "captcha_required",
        "paying",
        "paying",
        "bought",
    ]
    assert len({row["proxy_id"] for row in result["trace"]}) == 1


def test_queue_cart_captcha_and_over_limit_stop():
    assert run_purchase("t1", "q", {"queue": "expired"}, ledger())["status"] == "idle"
    cart = run_purchase("t1", "c", {"cart": "expired"}, ledger())
    assert cart["status"] == "failed"
    assert cart["reason"] == "cart_expired"
    captcha = run_purchase("t1", "p", {"captcha": "fail"}, ledger())
    assert captcha["reason"] == "captcha_stopped"
    assert captcha["alert"] is True
    over = run_purchase("t1", "n", {}, ledger(), quantity=7, limit=6)
    assert over["reason"] == "over_limit"
    assert [row["state"] for row in over["trace"]] == ["idle", "failed"]


def test_proxy_death_is_not_charged_again():
    book = ledger()
    first = run_purchase("t1", "a3", {"proxy": "died"}, book)
    assert first["status"] == "unknown"
    second = run_purchase("t1", "a3", {"pay": "ok"}, book)
    assert second["reason"] == "already_finished"
    assert second["repeated_charge"] is False
    assert second["trace"] == []
    assert second["status"] == "unknown"


def test_prices_match_the_readme_examples():
    assert price_for_margin(100, 0.12, 0.15) == 130.69
    assert price_for_margin(100, 0.12, 0.08) == 122.73
    assert price_for_margin(100, 0.09, 0.15) == 126.38
    assert price_for_margin(100, 0.09, 0.08) == 118.69
    assert round(margin_at(100, 0.12, 122.72), 4) == 0.0799
    assert undercut(100, 0.09, 125.00) == 124.00
    assert undercut(100, 0.09, 118.00) is None


def test_listing_key_is_once():
    store = {}
    first = create_listing(store, "t1", "viagogo", 130.69)
    second = create_listing(store, "t1", "viagogo", 130.69)
    assert first["ok"] is True
    assert first["key"] == "t1:viagogo"
    assert second["ok"] is False
    assert second["reason"] == "already_listed"
    assert store["t1:viagogo"]["status"] == "active"


def test_demo_walks_source_buy_price_list_and_sale():
    text = "\n".join(run_demo())
    assert "1 source" in text
    assert "Steven Wilson" in text
    assert "status bought" in text
    assert "viagogo again already_listed" in text
    assert "action mark_sold platform viagogo" in text
    assert "action delist platform stubhub" in text
    assert "ticket state sold" in text
    assert "stubhub listing delisted" in text
    assert "queue idle queue_expired" in text
    assert "repeated_charge False" in text
