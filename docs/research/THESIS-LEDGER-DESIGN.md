# Thesis Ledger — long-horizon thematic investing with the calibration loop (design, 2026-07-01)

Companion to [`STRATEGY-2026-07-01-SCALING.md`](STRATEGY-2026-07-01-SCALING.md)
§6 tier 3. Design only — implementation is a v2 lane that must never compete
with v1 operations for attention.

## 0. What this is (and is not)

**Is:** a disciplined process for 6–18-month thematic equity positions —
"memory-chip-explosion"-class calls — where each thesis is treated exactly
like a Kalshi market: a falsifiable claim, an evidence trail, a settlement
date, and an honest score. The operator's edges here are (1) time-arbitrage
(a 12-month holding period institutions structurally can't use), (2) supply-
chain fluency from an industry seat, (3) LLM-scale evidence synthesis,
(4) the calibration discipline this repo already enforces everywhere else.

**Is not:** a quant alpha bot (non-goal, permanently), a trading system, or
anything the research agent executes. The agent surfaces observations and
scores; a human makes every investment decision in a brokerage account.

**The template** (generalized from the memory case, where DRAM/NAND contract
pricing, sold-out HBM capacity, and capex guidance inflections were all
public months before the stocks ran): *find themes where a measurable
physical supply/demand imbalance shows up in public leading indicators
before consensus estimates catch up.* The candidates are always visible;
the hard parts are selection among plausible themes, sizing so misses are
survivable, and holding. Hindsight-bias warning is standing: for every theme
that ran, several equally-plausible ones didn't — which is why every thesis
is scored.

## 1. Ledger schema (one file per thesis, `theses/<slug>.md`)

```yaml
---
slug: example-theme
opened: YYYY-MM-DD
settles: YYYY-MM-DD            # 6-18 months out; scored at this date, period
claim: >                       # ONE falsifiable sentence with numbers
  <indicator> exceeds <level> by <date> AND <basket> outperforms QQQ by >= <X>pp.
mechanism: >                   # WHY, in one paragraph: the physical imbalance
leading_indicators:            # public, checkable, with sources
  - name: ...
    source_url: ...
    current_reading: ...       # value + retrieved_at, updated monthly
    confirm_level: ...         # pre-registered
    disconfirm_level: ...      # pre-registered — written at OPEN, not later
basket: [TICKER, TICKER]       # 2-4 names or an ETF; entry prices + dates
prob_estimate: 0.NN            # operator's calibrated probability at open
kill_criteria: ...             # exits before settlement (thesis broken != price down)
compliance_check: ...          # see §4; date checked
status: open | settled_yes | settled_no | killed
score: ...                     # filled at settlement only
---
<free-form evidence log, newest first; every entry has source_urls + retrieved_at>
```

Rules: the claim and disconfirm levels are immutable after open (append-only
log; edits = new thesis). `prob_estimate` makes every settlement Brier-scorable.
5–10 open theses max; no thesis >15–20% of the equity sleeve; long-only,
no leverage; sleeve = money not needed for 3+ years.

## 2. Agent cadence (Pass-2 machinery, extraction-only)

- **Monthly, per open thesis:** refresh each leading indicator (fetch, quote,
  cite), append to the log, flag confirm/disconfirm crossings. Never a
  recommendation — observations only (Pass-2 hard rule).
- **Quarterly, discovery sweep:** scan earnings transcripts / trade press /
  pricing sources for the template's signature phrases ("sold out through",
  "lead times extended to", "pricing actions", "capacity constrained") →
  emit CANDIDATE briefs (same schema, status `candidate`) for human triage.
- **At settlement:** score mechanically — did the claim's indicator leg and
  the basket-vs-QQQ leg each resolve? Brier update on `prob_estimate`;
  append to a `theses/SCOREBOARD.md` (the equity sleeve's reliability
  diagram, in effect).

LLM budget: dollars/month. All numeric outputs are *readings of sources*,
never model-generated estimates (Pass-1 rule applies unchanged).

## 3. Honest bars

- **Benchmark = QQQ** (the index the sleeve would otherwise hold). A thematic
  process that trails it is paying for entertainment — kill the sleeve if
  trailing after 6–8 settled theses.
- Expected shape of success: 1–2 big themes/yr with small losses elsewhere —
  index-plus-meaningful-alpha on the sleeve, not 10×.
- The scored track record is the product: after ~2 years of settlements the
  Brier/hit-rate data answers "does the operator have this skill?" — the
  same gate discipline as Phase 5, applied to a different asset class.

## 4. Compliance rail (per COMPLIANCE-ADDENDUM; not legal advice)

- Restrictions are **ticker-specific and information-specific**: general
  industry fluency (e.g., "HBM is the bottleneck") is legitimate edge; a
  material non-public fact about a *specific company* learned at work (e.g.,
  a supplier NVIDIA is about to sign/cut) blacklists that name until public.
  Every thesis records the check + date.
- NVDA itself: ESPP + 10b5-1 only; trading windows respected for any
  semiconductor-adjacent name per policy.
- Every settled thesis keeps its full evidence trail (`source_urls`,
  `retrieved_at`) — the same trail the signal table already requires.

## 5. Seed candidates — PROCESS EXAMPLES, NOT RECOMMENDATIONS

⚠️ Drafted from pre-2026 knowledge to exercise the template. The FIRST
discovery sweep must re-validate every indicator against current data before
any of these becomes an open thesis; expect some to be already-consensus (=
no edge) or already-run.

1. **Grid/power equipment for AI datacenters** — indicator shape: large-
   transformer & switchgear lead times (utility trade press), utility capex
   guidance, interconnection-queue stats vs Street estimates for T&D
   equipment makers.
2. **Advanced packaging / HBM follow-on beneficiaries** — indicator shape:
   CoWoS/packaging capacity bookings, OSAT capex inflections, HBM contract
   pricing — the *second-derivative* names after the memory move itself.
3. **Electrification-adjacent physical constraints** (copper/compute-cooling/
   optics) — indicator shape: commodity term structure, supplier order books,
   "sold out" language in transcripts.

Each seed enters as `candidate` and must pass: indicator measurable monthly
from public sources + Street-estimate lag demonstrable + basket with direct
revenue exposure + compliance check clean.

## 6. Build scope (when v2 opens)

Tiny by this repo's standards: `theses/` directory + schema validator +
`kq thesis score` (mechanical settlement) + two agent prompts (monthly
refresh, quarterly discovery) wired into the Pass-2 agent cadence. No
market data dependencies beyond fetching cited public sources. Explicitly
gated behind: v1 box operating ≥30 days and the Phase-A re-tests done.
