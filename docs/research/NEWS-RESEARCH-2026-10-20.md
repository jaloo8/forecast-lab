# News research: actual collection pilot, October 20, 2026

Three free official feeds were fetched once at **15:48:53–15:48:54 UTC**.
The collector archived **55 observations, 51 exact content versions and four
duplicate rows**. Forty-two observations passed the timestamp and URL gates;
13 were retained but blocked because their NVIDIA blog links are outside the
initial newsroom-host allowlist. This is an actual data-collection run, with
**zero model calls, paid data calls, orders or P&L calculations**.

The [fetch receipt](evidence/2026-10-20-long-history/news-fetch-receipt.json)
contains per-feed counts, raw input hashes, observation hash, observed times and
limitations. Raw feed bytes, headlines, the immutable journal and the exact
collector used are private under `data/news-event-pilot-20261020/run-v1/`.
These files are ignored by Git. The publication dates asserted by this snapshot
span April 29–October 20, 2026; they do not establish that our system possessed
those items before this collection.

## What the primary research supports

The following are source reviews, **not replications**. The separate
[source record](evidence/2026-10-20-long-history/news-source-review.json)
states which sections were inspected; no entire-paper reading claim is made.

| Original research | Finding relevant to this project | Practical boundary |
| --- | --- | --- |
| [Tetlock (2007), *Giving Content to Investor Sentiment*](https://www.uts.edu.au/globalassets/sites/default/files/adg_cons2015_tetlock-journal-of-finance-2007.pdf) | Quantifies pessimism in a daily WSJ column during 1984–1999 and examines subsequent returns and volume. Its hypothetical strategy uses prior-year thresholds. | Predictive association does not identify the cause of each price move. The hypothetical long/short strategy ignores margin/capital requirements and explicitly notes costs that could erase its return. It is not a validated $1,000 long-only strategy. |
| [Engelberg and Parsons, original October 2009 manuscript; published 2011](https://conference.nber.org/confer/2009/BEF09/Engelberg_Parsons.pdf) | Compares local investors exposed to different newspaper coverage of the same earnings event; weather disruptions help distinguish media transmission from underlying information. | Evidence concerns media's effect on local trading activity. It does not give this pilot a causal estimate of price direction, a modern online-news replication, or a profitable execution policy. |
| [Lopez-Lira and Tang, v6 (2025)](https://arxiv.org/html/2304.07619v6) | Studies post-model-cutoff headlines, with CRSP, RavenPack and TAQ linkage. It separates initial reactions from subsequent drift. | The roughly 90% initial-reaction hit rate is expressly **non-tradable**. The reported overnight long/short strategy becomes unprofitable at 20 basis points round-trip. Its data, short positions and costs differ from our constraints. |
| [Glasserman and Lin (2023)](https://arxiv.org/abs/2309.17322) | Investigates outcome knowledge and company-identity effects in LLM headline scoring; compares original and anonymized headlines. | A timestamp on an old article cannot remove a current model's later knowledge. Anonymization is a diagnostic, not proof that all leakage has disappeared. Our stronger initial approach is to record future observations before any outcomes are measured. |

These papers provide mechanisms worth investigating: information diffusion,
attention, delayed reaction and text measurement. None establishes 10–20% profit
in every calendar year. A chart showing news beside a price move would still
leave earnings surprises, rates, market-wide shocks and other simultaneous
information as alternative explanations.

## Implemented collection and time rules

[`scripts/news_event_pilot.py`](../../scripts/news_event_pilot.py) is a standalone
one-shot script. It uses the existing `httpx` dependency and a fixed list:

| Feed | Observations | Result |
| --- | ---: | --- |
| [Federal Reserve: all press releases](https://www.federalreserve.gov/feeds/press_all.xml) | 20 | HTTP 200 |
| [Federal Reserve: monetary policy](https://www.federalreserve.gov/feeds/press_monetary.xml) | 15 | HTTP 200 |
| [NVIDIA newsroom](https://nvidianews.nvidia.com/releases.xml) | 20 | HTTP 200; 13 cross-host blog links blocked |

The [Fed's official feed directory](https://www.federalreserve.gov/feeds/feeds.htm)
documents these feeds. NVIDIA describes its RSS service as free for individual
information use and restricts it to non-commercial use on its
[RSS terms page](https://www.nvidia.com/en-us/about-nvidia/rss/). This pilot is
personal research; it publishes aggregates and hashes, not a redistributed news
corpus. Expanding use requires revisiting source terms.

The script makes exactly three GET attempts, with no redirects or retries, a
20-second HTTP timeout, a 2 MiB decoded-body limit per feed and a 500-item limit.
It accepts UTF-8 XML, rejects entity declarations and refuses an existing output
directory. It never follows item links or executes source text. A failed source
gets a receipt; other sources can still complete.

Each observation has these distinct fields:

- `published_at`: source-asserted publication time, with the original date string.
  Missing or timezone-naive dates remain unknown; Atom `updated` is not silently
  substituted for publication.
- `retrieved_at`: local UTC time when that response finished arriving.
- `first_seen_at`: this collector's first actual observation of that exact
  content version. It initially equals retrieval, regardless of the article's
  age. A hash-checked prior journal can retain an earlier observation time.
- `event_id`: hash of the item URL. `content_hash`: hash of URL, normalized
  title/summary and original publication string. Revised content creates another
  version. This catches exact duplicates, not every syndicated or paraphrased
  story.
- Source URL, source item ID, explicit entity-link status, classifier version and
  validation issues. Source attribution identifies the Fed or NVIDIA; it does
  **not** infer that every mentioned company is NVIDIA or assign a trading ticker.
  `security_id` remains null.

An as-of query must pass all quality checks and have publication, first-seen and
the selected record's retrieval at or before the query time. Use the earlier
immutable snapshot when querying an earlier time. A later copy is not backdated
just because its content hash matches. Local timestamps and hashes provide an
audit trail, not external timestamp attestation.

The classifier currently recognizes only descriptive monetary-policy and
earnings mentions. It leaves other releases unclassified. It produces no
positive/negative investment judgement, surprise estimate or probability.

## Bounded agents and next research stage

The initial implementation is deterministic code, not six autonomous LLM traders.
The useful division of work is a sequence of reviewable artifacts:

| Role | Versioned output | Required boundary |
| --- | --- | --- |
| Scout | `news-observation-v1`, raw hashes and retrieval receipt | Fixed source list; source text is untrusted data; no tools suggested by articles |
| Entity linker | Proposed `news-entity-v1` with security IDs and mapping evidence | Effective-dated mapping, multiple-entity and unresolved states; never guess from a short ticker token |
| Event classifier | Current `release-keywords-v1`; optional future frozen model output | Quote evidence, uncertainty and prompt/model version; no probability without calibration |
| Critic | Proposed `news-review-v1` keyed to exact upstream hashes | Duplicate/revision, timestamp, contradiction and outcome-leakage checks; explicit rejection reasons |
| Accountant | Proposed `news-evaluation-v1` | Deterministic prices, cash, costs and account constraints; include all rejected trials |
| Coordinator | Proposed `news-run-v1` finite manifest | Enforce input versions and stopping rules; cannot alter a failed trial or grant execution authority |

Only observation, source attribution, descriptive tags and their validation are
implemented here. The remaining handoffs are a design proposal. Several agents
agreeing is not independent evidence if they share the same source or model.
Use models only for a specific measured bottleneck after deterministic controls
exist. The current pilot's funded-model budget is **zero**; no daemon or scheduled
collection has been started.

The next useful finite experiment is a prospective **data-quality cohort**:
explicitly invoked snapshots over a fixed period, retained failures, and a
randomly selected manual entity/timestamp audit. Before evaluating returns,
register the security universe, exact event rules, sample cutoff, entry delay,
fixed one-/five-session horizons and family-level multiple-testing treatment.
Join only prices available after the observed event and retain unmatched events.
Market-adjusted event returns can measure association; claiming causation
requires a separate identification design.

Any later trading experiment must be long-only/no borrowing, start from $1,000,
include cash and buy-and-hold controls, costs and integer-share feasibility,
and preserve every trial. Neither a historical model scoring old headlines nor
this small current RSS snapshot supplies a historical news backtest. This pilot
does not alter A8 or authorize broker submission.

## Run and verification

From the repository root, choose a **new** ignored output directory:

```powershell
.venv/Scripts/python.exe scripts/news_event_pilot.py --output data/news-event-pilot-next/run-v1
```

To retain exact-version first observation times on a later explicit run, add:

```powershell
--previous data/news-event-pilot-20261020/run-v1
```

The focused test file exercises artificial RSS/Atom data, time separation,
revision identity, cross-feed duplicates, unsafe URLs, missing dates,
oversized/entity XML, mocked HTTP failures, immutable output and prior-journal
hash/chronology guards. The [validation receipt](evidence/2026-10-20-long-history/news-validation.json)
records actual check commands and scope. These are collector tests, not
simulations or additional strategies.

Independent review found two parser edge cases, now covered by regressions:
non-feed XML roots containing apparent feed items, and UTC conversion overflow
for extreme dates. The final focused suite has **26 passing tests**. Replaying
the three saved feed bodies with their original retrieval timestamps produced
all **55 original observations identically**, with no new network requests.
The validation receipt distinguishes the final source hash from the unchanged
collector hash in the actual fetch receipt.
