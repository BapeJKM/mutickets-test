# Five-minute walkthrough

Record with the repo open. The outline is the order, not a script to read word for word.

## 0:00 Design in one minute

Say what the folder is: a design for sourcing a UK ticket and reselling it, plus one working piece. The working piece stops a second sale. The buy step is a drawing. No live purchase, no calls to Ticketmaster or a resale site.

Point at `README.md` and say the ten sections follow the brief in order.

## 0:45 The sample event and the legal line

Open the sample table. Steven Wilson, 28 Oct 2026, 18:45, Royal Albert Hall. The primary page gave the date, the venue, and a limit of 6 tickets per person and per household. It did not give sections, a primary price, or a stock count. Those cells say so.

Then the legal subsection. The 2018 regulations: software used to beat a sales limit for gain is an offence. Ticketmaster's terms ban unauthorised robots and ban traders buying to resell for profit without written permission. The 2025 face-value announcement was still being described as a draft in late September 2026. Do not call it current law, and do not treat that as a reason to automate checkout.

## 2:00 The module

Open `reconcile.py` from the top.

- `sale_beats`: earlier timestamp, then viagogo before stubhub before twickets, then the event id string.
- `reconcile`: ignore a message id we have seen, reject a sale if the seat is not listed, pick one winner, emit de-list and cancel for the rest. If the seat is already sold, cancel the new one.
- `cas_transition`: version must match, and the state only moves one step.
- `commit_sales`: the lock, then the version check, then the outbox.
- `flush_outbox`: three failures, then an alert, then stop.

Say the gap out loud: the other site can still sell until the de-list is accepted. The next message cancels that order. The window is not zero.

## 3:20 Tests

From the repo root, run `python run_tests.py`.

Name four cases while it runs: two sales at the same time, the same message twice, a later message with an earlier timestamp after we already sold, and two threads. Mention the seeded random test uses a fixed seed and does not use Hypothesis.

## 4:10 Decisions and the honest limits

Open `DECISIONS.md` for the module choice and the "no rewind" rule.

Open README point 9. Say what you cannot see without their database, their account pool, their risk rules, their sales history, and a real API approval. Do not fill those with guesses.

`QUESTIONS.md` stays unsent until you have read it. The defaults in that file are what the numbers in the README use, including the 12% and 9% fees from the brief. Those percents are not on the Viagogo or StubHub help pages.

## 4:40 Stop

Say the video is the walkthrough. The code is the de-list. The purchase was not built. Questions are in `QUESTIONS.md`.
