# Ticket sourcing and resale, one working slice

This folder is a design for the whole loop, plus code that walks the loop with stubbed answers. Nothing here calls a ticket site or charges a card.

Run the tests from a fresh clone:

```bash
python run_tests.py
```

That installs pytest from `requirements.txt` and runs `pytest`. The core file `reconcile.py` uses the standard library only.

Python 3.12 is the syntax target. On 6 Oct 2026 this PC had 3.13.3 and did not have 3.12. The tests ran on 3.13.3.

```
demo_loop.py          prints the whole stubbed loop
discover.py           the saved sample event, no network call
purchase.py           queue, cart, captcha, pay, proxy, account
pricing.py            brief fee math
listing.py            one create per ticket and platform
reconcile.py          de-list when one platform sells
tests/
run_tests.py
requirements.txt
pytest.ini
README.md
QUESTIONS.md
DECISIONS.md
AI_USAGE.md
VIDEO_SCRIPT.md
practice/             local only, gitignored, seeded bugs for rehearsal
```

Show the loop:

```bash
python demo_loop.py
```

## The sample event

Fetched 6 Oct 2026.

| Field | Value |
| --- | --- |
| Event | Steven Wilson |
| Date | Wed 28 Oct 2026, 18:45 |
| Venue | Royal Albert Hall, London |
| Primary sections | On the rendered event page, 7 Oct 2026: map labels Gallery, Second Tier, Grand Tier, Loggia, East Choir, West Choir. Offers named WCHOIR and ECHOIR. |
| Primary price | Seated £53.50 in WCHOIR rows 7 and 8. Verified resale £63.13 in ECHOIR row 4 and WCHOIR row 4. |
| Primary availability | The list heading said 2 results, with the quantity filter left at 2 tickets. Four offers were visible. This is not a count of every seat in the hall. |
| Limit that was on the page | A max of 6 tickets per person and per household. Tickets over 6 will be cancelled. Under 14s must be with an adult over 18. |
| Source | https://www.ticketmaster.co.uk/steven-wilson-london-28-10-2026/event/1F00644DBDE34D01 |
| Fetch date | 7 Oct 2026 |

A check on 7 Oct 2026 of https://needaticket.co.uk/events/steven-wilson-london-london-royal-albert-hall said prices were checked at 13:25 that day: 49 StubHub listings, 12 sections, cheapest Second Tier Box 9 from £75. That is resale stock, not Ticketmaster primary stock. The page's own "21 days until the event" matches 7 Oct to 28 Oct.

An earlier search excerpt of the StubHub UK page had no "prices as of" time, including a Second Tier Box 9 ask of £150.00. That figure is `[Unverified]` as a price for 7 Oct. The £75 line above is the one with a check time.

https://www.royalalberthall.com/tickets/events/2026/steven-wilson returned a bot wall ("Pardon Our Interruption") on 6 Oct 2026. It was not retried.

## How the de-list works, in plain words

A ticket is one seat. It is listed on more than one resale site. A sale message says which site sold it and when (`sold_at`, an integer millisecond timestamp).

`reconcile` looks at the messages against the ticket we already know. It does not talk to the network.

- A message id we have already applied is ignored. Sending the same message again changes nothing.
- If the seat is not listed yet, the message is rejected. We do not mark it sold from a `sourced` or `bought` row.
- If it is listed, one message wins. The earlier timestamp wins. If the timestamps match, viagogo beats stubhub, stubhub beats twickets, and a named site beats an unknown name. If that is still a tie, the smaller event id string wins. That last step is ordinary string order, so ids should be fixed width if you care about numeric order. `e10` sorts before `e2`.
- The winner produces `mark_sold`. Every other active listing produces `delist`. Every losing message produces `cancel_order`.
- If the seat is already sold or delivered, a new message is too late. We cancel that order. If that site's listing is still active, we de-list it too. We do not move the win to the late message, even when its timestamp is earlier. The first committed buyer may already have paid.

`cas_transition` is the only way the state moves. The version has to match, and the state may only move one step: sourced, then bought, then listed, then sold, then delivered. A wrong version or a skipped step is refused and the row stays as it was.

`commit_sales` holds a lock, runs `reconcile`, and applies `mark_sold` only if the version still matches. The other actions go to an outbox. `flush_outbox` asks a fake adapter to de-list or cancel. A timeout stays in the outbox. The third failure writes an alert and stops.

Tradeoff: the lock makes two threads produce one winner, which is what we want. A real HTTP call should happen after the lock is released, or a slow site blocks every other ticket. This test keeps the fake call inside the lock so the tests do not flap. The gap is still real. See point 6.

## 1. Source discovery

Ranked ways to learn that an event exists and what it costs. None of these were called from this repo.

### Official Discovery API

Docs: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/

An event search can filter by keyword, country, venue, and date. The event payload includes the name, the start time, the venue, a Ticketmaster URL, price ranges with a min and a max, sale windows, and a static seat-map image URL. Getting one event returns the venue, the attraction, and the purchase URL.

It does not return the unsold seats. A min/max range is not a section, a row, or a count of what is left.

Default quota on that page: 5000 calls a day, 5 requests a second, and paging stops at the 1000th item (`size * page < 1000`).

The call needs an API key. This repo does not have one. `[Assumption: there is no written permission to use a key against UK inventory for resale.]`

### Partner inventory

https://developer.ticketmaster.com/products-and-docs/apis/partner/ says the Partner API is not open. It is for companies that already have a distribution deal.

The availability endpoint is marked for channel partners only: https://developer.ticketmaster.com/products-and-docs/apis/partner/availability/

That response is the one that includes section, row, seats, face value, and fees. We cannot call it. The docs also say a client that reserves seats and then walks away should `DELETE` the cart, because a reserve can finish in the background and hold stock. That is partner behaviour, not something this test does.

### The public event page

The Steven Wilson URL above is a normal browser page. Fetching the HTML on 6 Oct 2026 returned the title, the date, the venue, and the 6-ticket rule. It did not return sections, prices, or a stock count. Those sit behind the page's own scripts.

Reading that page with a script is banned by the terms cited below. This design does not do it.

### Partner feeds

A feed from a promoter or from Ticketmaster under a contract would be the clean source: event, date, venue, and whatever stock the contract includes. `[Assumption: no such feed is in hand.]` If the feed has no seat map, we still do not have seat-level availability. Say so on the row instead of filling the gap.

### Queue and anti-bot, without attacking the site

The queue is a state a person waits in. The software records "queued" and stops. It does not refresh the waiting room, rotate identities, or solve a check.

The Royal Albert Hall URL above answered with a bot wall on the first fetch. There was no second try.

If a partner key exists later, stay inside the published Discovery quota. On HTTP 429, stop. Do not add parallel workers to "catch up".

### Legal and ToS risk

This is the part that should stop a checkout bot even if the rest of the design is tidy.

**Automated buying past the limit is a criminal offence.** The Breaching of Limits on Ticket Sales Regulations 2018, made under section 106 of the Digital Economy Act 2017: https://www.legislation.gov.uk/uksi/2018/735

They apply when UK event tickets are on sale online and the offer limits how many a purchaser may buy. It is an offence to use software designed to enable or facilitate any part of that purchase, with intent to get tickets over the limit, with a view to financial gain. It does not matter if the software runs outside the UK. In England and Wales the penalty is a fine. In Scotland the fine is capped at £50,000.

The Steven Wilson page states a limit of 6 per person and per household. Software whose job is to get more than 6 for resale sits on the wording of regulation 3.

**Ticketmaster's own terms ban the automation this loop would need.**

Terms of use, https://www.ticketmaster.co.uk/legal : no robot, spider, or automatic device to monitor or copy pages without prior written permission. No device or routine that interferes with the site. No unreasonable load. They may cancel an order and bar a person they believe is using automated means to place orders, or whose order exceeds the stated limit. Unauthorised automated use is described as something they will investigate, including civil and criminal routes.

Purchase policy, https://www.ticketmaster.co.uk/legal/purchase.html (page dated 20 May 2026 in the fetch):

- Clause 4.10: it is prohibited to obtain items through an unauthorised robot, spider, or other automated device. Orders they reasonably suspect can be cancelled without notice.
- Clause 8.3: you are not entitled to purchase tickets as a trader in the course of business in order to resell them for profit, unless Ticketmaster and the event partner have given formal written permission in advance. Suspected breach can get the tickets cancelled without notice.
- Clause 8.4: resale can also be banned by law or by the event partner, and that is grounds for cancellation.

Ticket Exchange policy, https://www.ticketmaster.co.uk/legal/ticket-exchange-policy.html : you may not list resale tickets that were obtained with an unauthorised robot or other automated software (clause 4.3(d) in the fetch).

**Resale information duties that already exist.** Consumer Rights Act 2015, section 90: https://www.legislation.gov.uk/ukpga/2015/15/section/90

A person who resells a UK event ticket through a secondary ticketing facility, and the operator of that facility, must give the buyer, before they are bound: the seat or standing area (including area, block, row, seat, and any unique ticket number), restrictions on who may use the ticket, and the face value. Some sellers also have to say if they are the platform, its staff, or the organiser.

**The face-value cap is not something this pass found as an in-force statute.** On 19 Nov 2025 the government announced plans to make resale above the original cost illegal, to cap platform service fees, and to stop people reselling more tickets than they were allowed to buy: https://www.gov.uk/government/news/government-bans-ticket-touting-to-protect-fans-from-rip-off-prices

The headline says "bans". The body says the government has announced plans. A Guardian report on 26 Sep 2026 says the department is still drafting and that the measure was not in that year's King's Speech as a bill ready to pass: https://www.theguardian.com/business/2026/sep/26/work-intensifying-uk-laws-stamp-out-concert-ticket-touts

A Mixmag report on 30 Sep 2026 quotes a minister saying the draft bill is being brought quicker than first intended: https://mixmag.net/read/uk-culture-minister-promises-quick-introduction-of-proposed-ticket-touting-ban-news

`[Unverified]` whether any of that became law between 30 Sep 2026 and 6 Oct 2026. This repo does not treat a price cap as current law. It also does not treat "the bill is not passed" as permission to bot an on-sale. The 2018 regulations and the Ticketmaster clauses above are already in force.

What is risky, in short: a script that really checks out, beating the 6-ticket rule, buying as a business to resell without written permission, and scraping the site after the terms said not to. What this repo runs: a local stub of those steps, and fake sale messages through the de-list. No ticket site is called.

## 2. Simulated purchase

`purchase.py` walks queue, cart, captcha, and pay on this machine. You pass a stub result for each step (`ok`, or a failure name). The function writes a trace and a final status. It does not open a socket, reserve a seat, or charge a card. A second call with the same attempt id, after `unknown`, `bought`, or `failed`, returns `already_finished` and an empty trace.

`python demo_loop.py` runs one bought path and two failure paths. The states below are what those lines mean.

| State | What it means | Stubbed failure |
| --- | --- | --- |
| idle | No attempt | |
| queued | A person or a partner session is in a waiting room | Queue expired. Back to idle. Do not refresh it. |
| cart_held | Seats are reserved | Hold expired. Release the cart if a partner API requires it. Stop. |
| captcha_required | The site wants a check | Do not send it to a solving service. Stop and alert a person. |
| paying | A charge is in flight | Proxy died or the response never came. Mark the attempt `unknown`. Do not charge again. A person looks at the account before anyone retries. |
| bought | The platform shows a paid order | Move the ticket from bought to listed only after the seat id is known. |
| failed | The site refused the order and no charge is outstanding | Do not list. Alert with the attempt id. |

Accounts, proxies, and CAPTCHA show up here as states, not as a bypass kit. Points 7 and 8 say what does not scale.

## 3. Resale platform research

Fee percents are not invented. Both large sites say the sell fee moves and show it at listing time.

| | Viagogo | StubHub | Twickets |
| --- | --- | --- | --- |
| Seller fee | No fixed percent. Listing is free. A sell fee is taken when it sells, and it may change with supply and marketing cost. https://support.viagogo.co.uk/articles/61000276841-viagogos-fees-to-sell-tickets | No set percentage. It moves with price, time to the event, and supply. The payout screen shows the fee. https://support.stubhub.com/articles/61000276392-stubhubs-ticket-fees | A per-ticket resale fee may be charged and is told during listing. Not a single published percent. https://www.twickets.live/en/terms/ticketingpolicyforsellers |
| What the seller may charge | Not restated here. The fee page above does not set a face-value cap. | The public buy page says prices are set by sellers and may be above face value. https://support.stubhub.com/articles/61000276392-stubhubs-fees-to-buy-and-sell-tickets | Face value or less, plus booking fees the seller actually paid, capped at 20% of face except where Twickets knows the original booking fee was higher, plus the stated delivery cost. Same policy URL, ticket resale prices clause. |
| Payout | Typically within 8 business days after the event. https://support.viagogo.com/articles/61000276591 | StubHub UK: within 5 to 8 business days after the event, by PayPal or direct deposit. https://support.stubhub.co.uk/en/support/solutions/articles/80000618604-how-do-i-get-paid-for-my-stubhub-sale- | Escrow: they aim for 5 to 8 days after the event, and they may hold payment for a complaint or a chargeback. PayPal: the buyer pays the seller's PayPal and Twickets pulls its fee. The fetched page does not state a PayPal delay. Same policy URL. |
| Audience | `[Assumption: larger UK resale audience than Twickets.]` No traffic number was fetched, so this is not scored as a fact. | Same assumption, same limit. | `[Assumption: smaller, fan-to-fan.]` |
| Seller rules that change this design | Not fully read. Do not assume dual listing is allowed just because this file did not find a ban. | A missed delivery can cost 100% of the ticket price or the cost of a replacement, whichever is greater. Same fee article. | Must be 18, must not sell in the course of a trade or for someone else, and must not offer the same tickets anywhere else while they are listed on Twickets. Failed delivery is a full refund plus a possible admin fee of 15% of face. |
| Delivery | `[Unverified]` in this pass. The fee page ties the fee to delivering as promised. | Same. UK payout article assumes the tickets are delivered and the event happens. | Buyer picks one of the methods the seller offered. The seller cannot swap the method. Time is of the essence. |
| API | Introduction at https://developer.viagogo.net/ : search, buy, and list, OAuth2, `api.viagogo.net`. This pass did not read a listing-idempotency page on that host. | Inventory API: https://developer.stubhub.com/api-reference/inventory . Creating a listing: https://developer.stubhub.com/docs/guides/creating-a-listing/ . They recommend `external_id`. A repeat create with the same id deletes the old listing and makes a new one. That is a replace, not a no-op. | No public seller API turned up in this search. |

Scoring, 1 to 5, only where a source supports it. Audience is left blank on purpose.

| | Fee clarity | Payout speed | Fit for listing one seat on two sites | API we could call without a guess |
| --- | --- | --- | --- | --- |
| Viagogo | 2. The fee exists and is disclosed at listing, and there is no stable percent to code against. | 2. About 8 business days after the event, not at sale time. | `[Unverified]` | 4. A public list API exists. Access and terms of that API were not fully read. |
| StubHub | 2. Same shape as Viagogo. | 2. 5 to 8 business days after the event on the UK help page. | 3. Dual listing was not banned in the pages read. The replace-on-same-`external_id` behaviour has to be handled or a retry will wipe a live listing. | 4. Documented create-listing call. |
| Twickets | 3. The seller price cap is written down. The platform's own resale fee is not a fixed percent. | 3. Escrow is 5 to 8 days after the event. PayPal may be sooner, and the page did not say. | 1. Exclusivity plus the trader ban. A business should not be on this site, and a dual list breaks the exclusivity clause even for a fan. | 1. No public seller API found. |

First slice under the assumption in `QUESTIONS.md`: Viagogo and StubHub. Twickets is in the tiebreak list so a message from that name still has a defined order. It is not a listing target.

## 4. Listing

One canonical ticket is one seat: `ticket_id`.

Each platform gets an adapter with the same three jobs: list, de-list, cancel. `listing.py` does the local create. `FakePlatform` in `reconcile.py` de-lists and cancels, and it can return `ok`, `timeout`, or `fail` from a script. Neither one calls a site.

The idempotency key we store is `ticket_id` plus the platform name. `create_listing` refuses a second create for that key. StubHub's documented `external_id` behaviour replaces an existing listing, so a blind retry is how you delete a good listing and make a second one. The local key is what makes the create happen once.

A sale on one site does not edit the other site's listing inside `reconcile`. It appends a `delist` action. The outbox is what actually calls the adapter, and a repeated de-list for the same ticket and platform is stored once.

## 5. Pricing

Platform A fee 12% and platform B fee 9% are the brief's numbers. They are not the Viagogo or StubHub rates. Those sites do not publish a single percent. See point 3.

```
payout = list_price * (1 - fee_rate)
margin = (payout - cost) / cost
target_price = cost * (1 + target_margin) / (1 - fee_rate)
floor_price  = cost * (1 + 0.08) / (1 - fee_rate)
```

Round the price up to the next penny. Rounding down can miss the floor. `pricing.py` is that formula. The tests lock the pennies in the table below.

`[Assumption: the fee is a fraction of the seller's list price, taken off the payout. Target margin is 15%. Cost in the examples is £100.00 and is not the Steven Wilson face value, which we do not have.]`

Worked, cost £100.00.

| | Raw price | Rounded up | Payout | Margin |
| --- | --- | --- | --- | --- |
| A target 15%, fee 12% | 115 / 0.88 = 130.6818... | 130.69 | 115.0072 | 15.0072% |
| A one penny under that | | 130.68 | 114.9984 | 14.9984% |
| A floor 8%, fee 12% | 108 / 0.88 = 122.7272... | 122.73 | 108.0024 | 8.0024% |
| A one penny under the floor | | 122.72 | 107.9936 | 7.9936%, do not list |
| B target 15%, fee 9% | 115 / 0.91 = 126.3736... | 126.38 | 115.0058 | 15.0058% |
| B floor 8%, fee 9% | 108 / 0.91 = 118.6813... | 118.69 | 108.0079 | 8.0079% |

Undercut, platform B, floor price 118.69, step £1.00.

- Competitor at 125.00. Candidate 124.00. Payout 124 * 0.91 = 112.84. Margin 12.84%. That clears 8%, so 124.00 is allowed.
- Competitor at 118.00. Candidate 117.00. Payout 106.47. Margin 6.47%. Under the floor. Do not list. Do not follow them down.

`[Assumption: at most one price change on a listing every 15 minutes, so two sites do not chase each other in a loop.]`

Repricing runs when a competitor quote changes or our cost changes. It never emits a list action if the rounded price fails the 8% check.

## 6. Inventory lifecycle

States, in order: sourced, bought, listed, sold, delivered. `cas_transition` refuses any other jump and any write whose `expected_version` is stale. The version increments by one on a successful write.

A sale on one platform de-lists the others by writing outbox rows in the same locked section as the state change. In a real database those rows would be the same transaction as the version bump. Here they are two lists on one object, updated under one lock. A crash between them is possible because there is no disk. That limit is stated on purpose. See point 9.

The race inside one process: two threads call `commit_sales` with two different sales. The lock makes the second thread read the ticket only after the first thread has set `sold` and stored the winner's event id. The second thread therefore takes the already-sold path and emits `cancel_order`. The test `test_threads_allow_one_sale` covers that.

The tiebreak covers two sales passed into one `reconcile` call. Timestamp first, then platform order, then event id. That rule does not reopen a sale that is already committed.

The window is not zero. After we have marked sold, and before the other site has accepted the de-list, that site can still sell. `flush_outbox` can also fail. The repair is the next sale message: `reconcile` sees `sold`, cancels the new order, and de-lists that platform if the listing is still `active`. Three failed attempts raise `gave_up` and stop. A person cancels the leftover by hand. We do not pretend the other buyer never existed.

## 7. Accounts

What a real programme needs, and what this design will not scale by cheating.

Seller side: PayPal or a bank account. For a UK event, StubHub asks for a 6-digit sort code as consecutive digits, with no spaces or hyphens: https://support.stubhub.co.uk/en/support/solutions/articles/80000618604-how-do-i-get-paid-for-my-stubhub-sale- . Some sellers are then asked to pass Hyperwallet KYC before a payout: https://support.stubhub.co.uk/en/support/solutions/articles/80000619698-changes-to-the-payment-services-agreement-for-sellers-of-european-and-uk-events

That KYC is per person. It does not become faster because you open more email addresses.

Buyer side: the Steven Wilson limit is 6 per person and per household. The 2018 regulations make software that is meant to beat a limit, for gain, an offence. Ticketmaster also says a trader buying to resell for profit needs prior written permission, or the tickets can be cancelled.

CAPTCHA. Payment-card checks. Device checks. None of these are a queue you clear with more accounts. A solving service, a bought identity, or a stack of warmed accounts is not a legitimate scale plan. One flagged card tends to flag the next account that uses it. The code in this repo has no account pool and will not grow one.

What can grow without that: a partner contract with stock and a seller API, and purchases a named person makes inside the printed limit.

`[Assumption: this test has neither the partner contract nor a decision that a named person will buy inside the limit. The purchase stays stubbed.]`

## 8. Proxies

Types, and why you would touch them at all.

- Datacenter addresses are cheap and are the first thing a ticket site blocks. They are a poor match for a checkout session.
- Residential addresses are harder to block. Using them to buy tickets is often against the proxy vendor's own terms. This design does not recommend it.
- Mobile addresses stick to one carrier for longer and there are fewer of them.

Geo: a UK event should exit in the UK. A foreign address on a UK on-sale is a mismatch, and it is also not a tool for getting a second quota of tickets.

Sticky: keep one address from the waiting room through the payment result. A new address in the middle looks like a new session and drops the cart.

Rotate: only before a session starts, when that address is already blocked, or after a person has finished with a flagged account. Do not rotate in order to dodge the per-person limit. That is the same conduct as point 7.

This repo contains no proxy client.

## 9. No dashboard access

Own data, three piles. The module keeps them in memory. A later version would put them in our database, not in anybody else's admin site.

- Append-only `log`. `commit_sales` appends the state change. `flush_outbox` appends `ok` or `gave_up`. Old rows are not edited. `test_log_appends_and_keeps_old_rows` checks that.
- Ticket row. One dict: id, state, version, listings, applied event ids, winner event id. The version is the compare-and-swap.
- Outbox. Pending de-list and cancel actions. A de-list for the same ticket and platform is stored once. Failed rows leave the outbox only after success or after the third failure, and the log keeps the outcome.

What cannot be done without MUtickets access, and why. This is not a soft gap. The function cannot see data it was not given.

- Their internal database. We do not know which seats they already bought, listed, or sold. A local dict starts empty. Running `reconcile` against an empty guess will de-list the wrong thing or miss a sale that only exists in their database.
- The account pool and the proxy pool. There is nowhere to read which seller login, buyer login, card, or address is allowed to be used. Point 7 and point 8 stay on paper until that exists.
- Their risk rules. Which shows they refuse, which sections they refuse, which margin they actually want, which platforms are contracted. `QUESTIONS.md` is the list. The defaults are labelled assumptions, not their policy.
- Sales history. Payout in point 3 is after the event, and the fee is disclosed per listing. Without their past payouts we cannot estimate a real fee percent. The 12% and 9% figures stay the brief's inputs.
- Partner and seller API approvals. Discovery, Partner, Viagogo, and StubHub all want a key or an OAuth client. There is no key in this repo. Listing, live stock, and live de-list cannot be switched on.
- A dashboard login would not fix the items above by itself. A login is not a schema, not a contract, and not a permission to automate Ticketmaster.

## 10. Failure handling

| Failure | What happens |
| --- | --- |
| Buy fails and no charge is outstanding | State `failed`. No listing. Alert with the attempt id. No automatic second checkout. |
| Proxy dies while `paying` | State `unknown`. Do not retry the charge. A person checks the order history. Two charges are worse than a slow answer. |
| Account flagged | Stop that account. Do not copy its card onto a new login in code. Alert. |
| De-list or cancel times out | The outbox row stays pending. `flush_outbox` tries again. |
| The third attempt still fails | Status `failed`, an alert `gave_up`, the ticket stays `sold`, the listing stays `active` on that platform. A person removes it. The loop stops. |
| The same sale message arrives twice | `applied_event_ids` makes the second `reconcile` return nothing. |
| Two sales in one call | Tiebreak, one `mark_sold`, cancel and de-list the rest. |
| A sale arrives after we already sold | Cancel, and de-list if that listing is still active. |

There is no pager integration. `book.alerts` is the list a person would read. Wiring it to email or Telegram needs their destination, which is one of the gaps in point 9.

## What I still need answered

`QUESTIONS.md`. Nothing in that file was sent anywhere. The build above uses the defaults written next to each question.
