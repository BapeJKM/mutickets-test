# Where a model was used

Date of this file: 6 Oct 2026.

The model was Cursor Grok 4.7. No other model wrote or edited this repo.

- The saved assignment was read so the build matched the brief. Private correspondence was not copied into any file here.
- Web search and page fetches on 6 Oct 2026 used Exa. The README cites the URLs that were actually returned. Anything the pages did not contain is marked `[Unverified]` or `[Assumption: ...]`.
- The same model wrote `QUESTIONS.md`, `DECISIONS.md`, `README.md`, `reconcile.py`, `tests/test_reconcile.py`, `run_tests.py`, and `VIDEO_SCRIPT.md`.
- The same model later added `discover.py`, `purchase.py`, `pricing.py`, `listing.py`, `demo_loop.py`, and `tests/test_loop.py` so the stubbed loop can be run in one command. Still no ticket-site client.
- On 7 Oct 2026 the rendered Ticketmaster event page was opened in a browser. With the quantity filter left at 2, the list showed WCHOIR rows 7 and 8 at 53.50 GBP and two verified resale rows at 63.13 GBP. The heading said 2 results. That is not a full hall count. The earlier HTML-only fetch had missed these prices because they are drawn by the page script.
- The humanizer checklist (no em dash, no en dash, no curly quotes, plain technical wording) was applied by that same model while writing. Nobody else rewrote the prose.
- Tests were executed locally with pytest. The pass count is whatever `python run_tests.py` prints. This file does not hard-code a number that might drift.
- Phase 3 reviewers, when they ran, are the same model family (`inherit`). Their findings are fixed in the files, not pasted here as a second copy of the code.

Not used: a Ticketmaster API key, a checkout script, a CAPTCHA solver, a proxy vendor, or a model call against a live ticket site.
