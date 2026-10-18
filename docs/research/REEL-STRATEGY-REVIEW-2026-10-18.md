# Reel strategies: source checks and reproducible tests

Reviewed October 18, 2026. Public data; one bounded reviewer; sequential,
single-threaded replay. No subscription, live order or production rule change.
The attachment is a prior conversation, not verified strategy evidence.

## Findings

| Claim or method | What was actually verified | Verdict |
|---|---|---|
| Nicholas Fischer's five bots and $72,074 in 23 days | Original reel and author handle; no complete public rules, code or broker reconciliation | Profit claim unverified; no faithful backtest possible |
| “0DTE” | Original caption reads **“1DTE Python Bots”** | Pasted summary incorrect on expiration |
| KO/PEP statistical arbitrage | Frozen, independently specified daily pairs rule, 2006–2025 | Approximately flat at baseline costs; not a candidate for deployment |
| Heston/volatility mispricing | Named model family; no complete contract-selection/execution rule | Requires option quotes and an explicit fitted forecast; no results claimed |
| Fama–French five-factor residual | Attribution formula, not a causal stock-selection algorithm | Retrospective residuals cannot be treated as known future alpha |
| Insider cluster buys | Public SEC ownership datasets and filing-date fields available | Feasible research lane; the creator's score is not yet sufficiently specified |
| Our options candidate | Explicit SPY call-spread protocol; tested quote/cost kernel | Research specification only; no historical options profitability measurement |

## Original-source investigation

The [original Fischer reel](https://www.instagram.com/reel/DeCk2UugeNF/)
was accessible in the in-app browser after the text fetch failed. The handle
was `nickafischer`; the caption was **“1DTE Python Bots.”** The creator's public
comment directs readers to a Discord feed of trade outcomes. No complete
entry, exit, sizing, account capital or execution specification was visible.
Opening the profile encountered a sign-up/login prompt; no account was used,
comment sent or Discord joined. Searches for the reel ID, exact profit amount,
name variants, handle and GitHub did not locate matching public source code.
This is a bounded negative search, not proof that private rules do not exist.

The pasted [Contra project link](https://contra.com/p/XZ3WmUes-developed-an-automated-options-trading)
did not load directly. The [author portfolio](https://contra.com/raj_kumar_yw9i4nfi/work)
describes a Deriv API project; it does not substantiate the five ETF bots.
The $72,074 claim is not audited here. Profit alone, without starting equity,
positions, deposits and costs, cannot establish a return or reproducible edge.

[Ray Fu's original guide](https://www.raycfu.com/guides/ai-trading-strategies-gpt-6-astra)
names pairs/OU, Heston, factor attribution and insider buying. It offers a
strategy-generation workflow, not a complete fixed trading rule for each.
Our KO/PEP implementation fills those gaps with disclosed assumptions. It is
not the creator's code, a fitted OU process or a replication of a broad-universe
published pairs study. An agent count or backtest acceptance threshold is not
independent evidence that the resulting system works.

## Pairs replay: all results, not just the best case

Frozen [protocol](REEL-PAIRS-PROTOCOL-2026-10-18.md) SHA-256:
`5fb678e6d5ef86cfd7eb58c0273d6e063b58beab6a030012c8e114db5c69a405`.
Hashed October 18 Yahoo captures, 2005 warm-up and exactly 5,031 evaluated
sessions, January 2006–December 2025. No pair or threshold search after results.
One rule crossed with nine cost assumptions; 36 completed trades per case.
Initial virtual equity $1,000. Fees apply to each leg at entry and exit; short
borrow accrues by actual calendar days. Cash earns zero; terminal liquidation
is charged. These are research assumptions, not reconstructed broker fills.

| Cost per traded leg | Annual borrow | Final equity | Annualized return | Max drawdown |
|---:|---:|---:|---:|---:|
| 10 bp | 0% | $1,068.91 | +0.334% | 8.44% |
| 10 bp | 3% | **$1,000.45** | **+0.00225%** | **9.13%** |
| 10 bp | 10% | $856.86 | −0.769% | 18.02% |
| 25 bp | 0% | $1,011.67 | +0.058% | 9.00% |
| 25 bp | 3% | $946.78 | −0.273% | 12.15% |
| 25 bp | 10% | $810.70 | −1.044% | 21.85% |
| 50 bp | 0% | $922.83 | −0.401% | 13.61% |
| 50 bp | 3% | $863.50 | −0.731% | 17.52% |
| 50 bp | 10% | $739.09 | −1.500% | 28.58% |

Baseline costs consumed $37.77 and borrow $68.13; 47.22% of trades won.
Its **45-cent total profit is over twenty years**, not per day or on A8's
actual paper ledger. Baseline-cost control: initially 50% SPY / 50% cash,
unrebalanced, ended $4,439.18 (+7.74% annualized, 31.09% max drawdown).
SPY's portfolio weight grows over time; this is not a constant-risk match or
a causal estimate of stock-selection alpha. Full annual outcomes are retained.

Limitations: current adjusted prices proxy distributions and can be restated;
historical borrows, recalls, margin and executable bid/ask are absent. KO/PEP
are current survivors named in a contemporary guide. This already-researched
history is not a sealed holdout. The result rejects this implementation as a
useful net-edge candidate; it does not disprove all pairs trading.

## Validation, server reproduction and artifacts

A reviewer found that precomputed signals could retain a fictitious position
after a forced risk exit. The regression failed before the fix; decisions now
use actual account state after fills. Review found no further material defect
in the scoped pairs engine. The historical path had no forced risk exits, and
its metrics were unchanged after the correction. Both versions are retained.

Thirty-eight focused tests passed locally and on A8: accounting hand checks,
calendar borrow, short-loss stress, next-open fills, future-data perturbations,
risk-exit/reentry, capture integrity and option-quote rejection. Ruff and mypy
passed for the new modules. This is focused verification, not a fresh full-repo
suite or a proof of future profits. The options tests use synthetic quotes.

A8 reproduced **33/33 result files byte-for-byte**, at 17:06 UTC October 18.
The ten paper-account database hashes were unchanged before/after. The archive
was 508,842 bytes. This was an isolated research execution, not a scheduler,
weather or live-trading deployment; it does not prove unattended health.

- Local private evidence: `data/reel-study-20261018-v2/` (metrics, annual results,
  orders, trades, daily ledgers, tests and `cross-host-verification.json`).
- A8 research stage: `C:/Users/jloo1/Documents/stock-paper-lab-20260928/data/equities/strategy-lab/audit-20261018/reel-stage`.
- Archive SHA-256: `53e2c85138dd84a40441f7cf4a1e2bd2e1245de41244cf32d7cd32e7cdd3a263`.
- Reproduce: `uv run python scripts/run_reel_pairs_study.py --capture data/audit-20261018 --output data/reel-study-new --protocol docs/research/REEL-PAIRS-PROTOCOL-2026-10-18.md`.
- Next options work: [independent candidate and data requirements](OPTIONS-CANDIDATE-2026-10-18.md).

## Research beyond the reels

[Gatev, Goetzmann and Rouwenhorst](https://repec.som.yale.edu/icfpub/publications/2573.pdf)
use historical formation and subsequent trading windows for pairs. Their
selection universe and normalized-price-distance method differ from our
single rolling-log-ratio example; their published returns are not ours.
[Cohen, Malloy and Pomorski](https://www.nber.org/papers/w16454) distinguish
routine and opportunistic insiders; only the accessible abstract was verified.
It does not validate a generic five-day cluster score.

[SEC ownership data](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets)
are public from 2006. The [schema](https://www.sec.gov/files/insider_transactions_readme.pdf)
includes filing dates and amendments. A replay must trade after public filing,
not the underlying insider transaction date. Exact dissemination timing and
corrected filings require further provenance work; no insider returns computed.

[Kenneth French's data library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
is a public factor reference. [Beckmeyer, Branger and Gayda](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4404704)
report losses for aggregate retail 0DTE activity; that is not a finding about
Fischer's 1DTE bots. [Cboe quote data](https://datashop.cboe.com/option-quote-intervals)
documents suitable historical option fields but is paid. No subscription or
profit guarantee follows from its existence.
