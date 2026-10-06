# Decisions

## De-list on sold, not a scraper and not a proxy router

The brief allows three modules. This repo builds cross-platform de-list when one sale lands.

Alternatives: a source scraper with backoff, or a proxy router.

Why: the graded risk in the loop is selling the same seat twice. The scraper would have to hit a live ticket site, which this test forbids. The proxy router is mostly policy text. The de-list function can be pure, tested, and small enough to debug live with no model in the room.

## Python, standard library in the core, pytest for tests

Alternatives: Go or TypeScript.

Why: the follow-up is a person reading one file and finding a seeded bug. A straight Python function is the shortest path. The syntax stays valid on Python 3.12. This machine does not have 3.12 installed (`py -0p` on 6 Oct 2026 showed 3.13 and a uv 3.11). Tests ran on Python 3.13.3. No 3.13-only syntax.

## One file for the core

Alternative: a package with adapters, domain, and storage split apart.

Why: the live debug has to stay linear. `reconcile.py` is the whole runtime. Tests live in `tests/`.

## In-memory book, not SQLite

Alternative: SQLite for the log, the ticket row, and the outbox.

Why: a database would be more honest about crashes, and it is the right store for a later version. It is also more code to read under a timer. The README point 9 describes the tables. The module keeps the same three piles in memory: `log`, the ticket dict, and `outbox`.

## Tiebreak inside one batch, no rewind after commit

Inside one `reconcile` call, the earlier `sold_at` wins. If those are equal, the platform order is viagogo, then stubhub, then twickets, then any other name. If those are also equal, the smaller `event_id` string wins.

Alternative: first event in the list wins, or the later timestamp wins because it is "more recent".

Why: two messages in one tick need a rule that does not depend on which packet was read first. After `commit_sales` has moved the version to sold, a late message does not steal the sale. The buyer on the committed platform may already have paid.

## Idempotency is the event id, and de-list retries live in the outbox

Alternative: retry by replaying the sale into `reconcile`.

Why: replay after a successful commit must do nothing. A failed de-list is not a new sale. It stays in the outbox until it succeeds or the third failure raises an alert.

## StubHub `external_id` is not a safe no-op

The StubHub listing guide says a second create with the same `external_id` deletes the old listing and creates a new one. Our key is `ticket_id` plus the platform name, and a second create is refused locally before any HTTP call. This repo does not call them.

## Fee percentages in the pricing section come from the brief

Alternative: pick a blog's "typical 10%" and treat it as fact.

Why: the Viagogo and StubHub help pages say the sell fee changes and do not publish one percent. Inventing one would fail the source rule. The worked examples use 12% and 9% and say so.

## Twickets is researched and not listed on

Alternative: list the same seat on Twickets and Viagogo together.

Why: the Twickets seller policy says a seller must not be acting in the course of a trade, and must not offer the same tickets elsewhere while they are listed there. A business listing on two sites breaks both lines.

## The lock is held for the decision, and the fake adapter runs inside it

Alternative: call the adapter after releasing the lock, which is what a real HTTP client should do.

Why: the fake adapter returns a scripted string. Holding the lock makes the tests deterministic. The README says a real HTTP de-list goes out after the commit, which is why the other site can still sell in the gap.

## Three attempts, then stop

Alternative: retry with backoff forever.

Why: a dead listing will not heal because the loop is tighter. Three failures write an alert and leave the ticket sold. A person finishes the de-list.

## This folder is its own repo

Alternative: put the work inside the personal notes repo.

Why: that repo has unrelated private material. This folder is the thing that can be zipped or cloned on its own.

## Purchase stays a drawing

Alternative: a second module that walks a checkout.

Why: the brief says the buy step is simulated, and one module only. Checkout states are in the README. There is no client for them.
