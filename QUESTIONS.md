# Questions before a real build

Do not send this file. It is for review first.

Each question has the default this test build already uses. A different answer changes the code or the listing rules.

## Volume

How many tickets a day, and how many in the first minute of an on-sale?

[Assumption: 30 purchases a day, with a burst of about 5 at once. One operator. This is not a farm of thousands of accounts.]

Why it matters: a burst of 5 can share one process and one lock. A burst of hundreds needs a queue and separate workers, and it is also where the bot offence below gets easier to commit.

## Target margin

The brief fixes a hard floor at 8% after fees, and uses about 12% on platform A and 9% on platform B. What net margin should a listing aim for before that floor?

[Assumption: aim for 15% after the platform fee. Do not list under 8%. The 12% and 9% figures are the brief's inputs. They are not a published Viagogo or StubHub rate. See README point 5.]

Why it matters: the list price is `cost * (1 + margin) / (1 - fee)`. 15% and 8% produce different prices. A target under 8% cannot be met, so nothing would be listed.

## Which platforms

Which marketplaces are in the first slice, and is the same seat allowed on more than one of them at the same time?

[Assumption: Viagogo and StubHub only. Twickets stays in the research and in the tiebreak table, and is not listed on, because its seller policy forbids trade sellers and forbids listing the same tickets anywhere else while they are on Twickets. Tiebreak order if two sales share a timestamp: viagogo, then stubhub, then twickets, then any other name.]

Why it matters: the de-list module is only useful if two listings can exist. Twickets' own rule says they must not.

## Delivery constraints

Mobile transfer, PDF, or post? Who must deliver, and by when? What is a "sold" event: a paid order, or an unpaid hold?

[Assumption: UK events, mobile transfer, seller completes it before the platform cutoff. No paper post in this slice. "Sold" means the platform confirmed a paid order. An unpaid hold does not de-list anything. One canonical ticket is one seat. Two seats are two ticket ids.]

Why it matters: a hold that de-lists the other site will kill a listing that never got paid. A pair sold as one listing needs a different id scheme.

## Other questions

### Partner access

Is there a written Ticketmaster partner or affiliate agreement, and a Discovery API key, that this work is allowed to use?

[Assumption: no. This repo has no key. Seat-level stock is treated as unavailable.]

### Currency and rounding

GBP, and do we round the list price up to the next penny?

[Assumption: GBP. Round up to the next penny. Rounding down can push a floor price under 8%.]

### A late event with an earlier timestamp

If platform B reports a sale timestamped before the sale we already committed on platform A, do we unwind A?

[Assumption: no. Once the ticket version has moved to sold, the first committed sale stands. The late event is cancelled. Rewinding a buyer who already paid is the worse failure.]

### Face-value cap

The November 2025 government announcement is still being described as draft legislation in September 2026 reporting. Should list prices stay at face plus unavoidable fees anyway?

[Assumption: this test does not list anything for sale. The pricing section is arithmetic only. A real listing above face needs a yes after someone checks the statute on that day.]

### Repricing step and cooldown

How far under a competitor, and how often may the price move?

[Assumption: £1.00 under the competitor, and at most one change per listing per 15 minutes. Never through the 8% floor.]

### De-list keeps failing

After the other platform rejects the de-list, who picks up the phone?

[Assumption: three tries, then an alert. The ticket stays sold. A person removes the leftover listing by hand. The code does not keep looping.]

### Buyer accounts

Is the purchase made by a named person inside the published ticket limit, or by some other arrangement?

[Assumption: one real person, inside the limit printed on the event. The software does not try to exceed that limit. See README point 1 and point 7.]
