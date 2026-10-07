# Ticket sourcing and resale

This folder designs the loop and runs it with stubbed answers. Nothing here calls a ticket site or charges a card.

```bash
python demo_loop.py
python -m pytest -q
```

```
demo_loop.py     prints the loop
discover.py      saved sample event, no network call
purchase.py      queue, cart, checkout, captcha, pay
pricing.py       fee math from the brief
listing.py       one create per ticket and platform
reconcile.py     de-list when one platform sells
tests/test_reconcile.py
README.md
```

`reconcile.py` is the piece built for real. It uses the standard library only.

## Sample event

Checked 7 Oct 2026. https://www.ticketmaster.co.uk/steven-wilson-london-28-10-2026/event/1F00644DBDE34D01

| Field | Value |
| --- | --- |
| Event | Steven Wilson |
| Date | Wed 28 Oct 2026, 18:45 |
| Venue | Royal Albert Hall, London |
| Sections | Map labels Gallery, Second Tier, Grand Tier, Loggia, East Choir, West Choir. Offers named WCHOIR and ECHOIR. |
| Price | Seated £53.50, WCHOIR rows 7 and 8. Verified resale £63.13, ECHOIR row 4 and WCHOIR row 4. |
| Availability | Quantity filter was 2. Heading said 2 results. Four offers were on the list. Not every seat in the hall. |
| Limit | 6 tickets per person and per household. Under 14s with an adult over 18. |

The first HTML fetch did not include the ticket list. The page script draws it after load. The numbers above are from that rendered list.

Resale, not the Ticketmaster box office: https://needaticket.co.uk/events/steven-wilson-london-london-royal-albert-hall checked 13:25 on 7 Oct 2026. 49 StubHub listings, 12 sections, cheapest Second Tier Box 9 from £75.

## How a sale is reconciled

One seat, listed on more than one site. A sale message has a platform and `sold_at` (integer milliseconds).

`reconcile` does not use the network.

- A message id already applied is ignored.
- If the seat is not listed yet, the sale is rejected.
- If it is listed, the earlier timestamp wins. If the times match, viagogo beats stubhub, stubhub beats twickets. If that is still a tie, the smaller event id string wins.
- The winner is `mark_sold`. Other active listings are `delist`. Losing messages are `cancel_order`.
- If the seat is already sold or delivered, the new message is cancelled. A still-active listing on that platform is de-listed. The win does not move.

`cas_transition` is the only state change. The version must match. The state moves one step: sourced, bought, listed, sold, delivered.

`commit_sales` holds a lock, then applies `mark_sold` only if the version still matches. De-list and cancel go to an outbox. `flush_outbox` calls a fake adapter. A timeout stays pending. The third failure raises an alert and stops.

Two threads can both see the seat as listed. The lock makes the second thread read it only after the first has set `sold`, so the second sale is cancelled.

The gap is not zero. After we mark sold, and before the other site accepts the de-list, that site can still sell. The next sale message cancels that order and de-lists if the listing is still active.

## 1. Source discovery

Three ways to learn an event, none of them called from this repo.

Discovery API, https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/ : name, start time, venue, purchase URL, price min and max, sale windows, a static seat-map image. It does not return unsold seats. Default quota: 5000 calls a day, 5 per second, paging stops at the 1000th item. Needs an API key. This repo has none.

Partner availability API, https://developer.ticketmaster.com/products-and-docs/apis/partner/availability/ : section, row, seats, face value, fees. The Partner API is not open. https://developer.ticketmaster.com/products-and-docs/apis/partner/ It is for companies that already have a distribution deal. A client that reserves and walks away should `DELETE` the cart, because a reserve can finish in the background and hold stock.

The public event page is what supplied the sample above.

Queue: record `queued` and stop. Do not refresh the waiting room or rotate identities to skip it. If a partner key exists later, stay inside the published quota. On HTTP 429, stop.

## 2. Simulated purchase

`purchase.py` walks queue, cart, checkout, captcha, and pay. Each step takes a stub result (`ok` or a failure name). No socket, no reserve, no charge. A second call with the same attempt id after `unknown`, `bought`, or `failed` returns `already_finished` and does not charge again.

| State | Stubbed failure |
| --- | --- |
| queued | Queue expired. Back to idle. Do not refresh. |
| cart_held | Hold expired. Release. Stop. |
| captcha_required | Stop and alert. Do not send it to a solver. |
| paying | Proxy died or no response. Status `unknown`. Do not charge again. |
| failed | Payment declined, or the account is flagged. No listing. Alert. |
| bought | Stubbed paid order. |

## 3. Resale platforms

The 12% and 9% figures in point 5 are the brief. Viagogo and StubHub do not publish one seller percent. The fee is shown when you list.

| | Viagogo | StubHub | Twickets |
| --- | --- | --- | --- |
| Seller fee | No fixed percent. Free to list. Fee taken when it sells. https://support.viagogo.co.uk/articles/61000276841-viagogos-fees-to-sell-tickets | No set percentage. Shown on the payout screen. https://support.stubhub.com/articles/61000276392-stubhubs-ticket-fees | Told during listing. Not one published percent. https://www.twickets.live/en/terms/ticketingpolicyforsellers |
| Seller price | Not capped on that fee page. | Sellers set the price. It may be above face value. | Face value or less, plus booking fees actually paid, capped at 20% of face unless Twickets knows the original fee was higher, plus delivery cost. |
| Payout | About 8 business days after the event. https://support.viagogo.com/articles/61000276591 | UK: 5 to 8 business days after the event. https://support.stubhub.co.uk/en/support/solutions/articles/80000618604-how-do-i-get-paid-for-my-stubhub-sale- | Escrow: 5 to 8 days after the event. PayPal delay was not stated on the fetched page. |
| Seller rules | Dual-list rule was not in the pages read. | A missed delivery can cost 100% of the price or the replacement, whichever is greater. | Must be 18. Must not sell as a trade or for someone else. Must not offer the same tickets elsewhere while listed here. |
| API | https://developer.viagogo.net/ lists tickets. OAuth2. | https://developer.stubhub.com/docs/guides/creating-a-listing/ A repeat create with the same `external_id` deletes the old listing and creates a new one. | No public seller API found. |

First slice: Viagogo and StubHub. Twickets stays in the tiebreak order only. A business seller listing the same seat there and elsewhere breaks their exclusivity rule.

## 4. Listing

One seat is one `ticket_id`. The key is `ticket_id` plus the platform name. `create_listing` refuses a second create for that key. StubHub's `external_id` replaces the old listing, so a blind retry would wipe a live one. The local key stops the second create before any call.

`FakePlatform` de-lists and cancels from a script: `ok`, `timeout`, or `fail`. It does not call a site.

## 5. Pricing

```
payout = list_price * (1 - fee_rate)
margin = (payout - cost) / cost
```

Fee on A is 12%. Fee on B is 9%. Target margin 15%. Do not list under 8%. Round the list price up to the next penny. Cost in the examples is £100, not the Steven Wilson face value.

| | List price | Payout | Margin |
| --- | --- | --- | --- |
| A target | 130.69 | 115.0072 | 15.0072% |
| A floor | 122.73 | 108.0024 | 8.0024% |
| A at 122.72 | 122.72 | 107.9936 | 7.9936%, do not list |
| B target | 126.38 | 115.0058 | 15.0058% |
| B floor | 118.69 | 108.0079 | 8.0079% |

Undercut on B, step £1. Competitor at 125: list at 124, margin 12.84%. Competitor at 118: 117 is under 8%, do not list.

`[Assumption: at most one price change per listing every 15 minutes.]` Reprice when the competitor or our cost changes. Never list if the rounded price fails the 8% check.

## 6. Inventory lifecycle

States: sourced, bought, listed, sold, delivered. Only one step at a time, and only if `expected_version` matches. The version goes up by one.

A sale writes the de-list rows in the same locked section as the state change. In a database that would be one transaction. Here it is two lists on one object. A crash between them is possible because nothing is on disk.

Tiebreak inside one call: timestamp, then platform order, then event id. That does not reopen a sale already committed.

After `sold`, and before the other de-list succeeds, the other site can still sell. The next message cancels it. Three failed de-lists: alert `gave_up`, ticket stays `sold`, a person removes the leftover listing.

## 7. Accounts

Seller payout is PayPal or a bank account. StubHub UK asks for a 6-digit sort code with no spaces: https://support.stubhub.co.uk/en/support/solutions/articles/80000618604-how-do-i-get-paid-for-my-stubhub-sale- Some sellers must pass Hyperwallet KYC before a payout: https://support.stubhub.co.uk/en/support/solutions/articles/80000619698-changes-to-the-payment-services-agreement-for-sellers-of-european-and-uk-events KYC is per person.

Buyer side for this event: 6 tickets per person and per household. CAPTCHA, card checks, and device checks are not cleared by opening more accounts. This repo has no account pool. A flagged account stops. The code does not copy its card onto a new login.

## 8. Proxies

Datacenter addresses are cheap and get blocked first. Residential addresses are harder to block. Mobile addresses stay on one carrier longer and there are fewer of them.

A UK event should exit in the UK. Keep one address from the queue through the payment result. A new address in the middle drops the cart. Rotate only before a session starts, or when that address is already blocked. This repo has no proxy client.

## 9. No dashboard access

In memory, three piles:

- Append-only `log`. Old rows are not edited.
- Ticket row: id, state, version, listings, applied event ids, winner event id.
- Outbox: pending de-list and cancel. One de-list per ticket and platform.

Cannot do without their access:

- Their database of seats already bought, listed, or sold. An empty local dict will de-list the wrong thing.
- Which seller login, buyer login, card, and proxy address are allowed.
- Which shows, sections, margin, and platforms they actually use. The defaults used here are assumptions: 15% target margin, 8% floor, Viagogo and StubHub, one seat, a paid order counts as sold.
- Past payouts, so a real fee percent cannot be estimated. 12% and 9% stay the brief's numbers.
- Partner and seller API keys. There are none in this repo. Live stock and live de-list stay off.

A dashboard login does not supply those.

## 10. Failure handling

| Failure | What happens |
| --- | --- |
| Buy fails, no charge outstanding | `failed`. No listing. Alert. No second checkout. |
| Proxy dies while paying | `unknown`. Do not charge again. A person checks the account. |
| Account flagged | Stop that account. Alert. |
| De-list times out | Outbox row stays pending and is tried again. |
| Third de-list fails | Alert `gave_up`. Ticket stays `sold`. A person removes the listing. |
| Same sale message twice | Ignored. |
| Two sales in one call | One `mark_sold`, cancel and de-list the rest. |
| Sale after we already sold | Cancel, and de-list if that listing is still active. |

`book.alerts` is the list a person would read. Sending it to email needs their address.
