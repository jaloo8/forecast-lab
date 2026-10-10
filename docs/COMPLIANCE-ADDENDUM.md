# COMPLIANCE-ADDENDUM.md

**Status:** Supersedes Section A-Compliance of Research Pass 2 where in conflict.
**Date:** 2026-04-22
**Reason:** The Pass 2 compliance section overreached. It treated "NVIDIA employee" as equivalent to "possesses MNPI on the entire semiconductor and hyperscaler supply chain" and proposed a broad default blacklist. That is not the correct legal frame, and it does not match the project described — a signal pipeline built from public sources (web scraping, Twitter/Reddit, news articles, earnings calls, SEC filings, public forecasts).

This addendum corrects the frame. It is still not legal advice. Review with NVIDIA Legal/HR and a personal securities attorney before any material real-money activity or any commercialization.

---

## The correct legal frame

Insider trading liability under Rule 10b-5 requires that a trade be made **on the basis of** material non-public information. The test is whether the specific trade was informed by specific non-public information, not whether the trader happens to hold a job where they theoretically could know things.

Three consequences follow:

1. **Using public data is a defense, not a risk.** A trade built on Goldman capex research, TSMC monthly revenue disclosures, SEC filings, earnings call transcripts, and scraped news is not insider trading, regardless of employer. Millions of tech employees trade tech stocks using public information legally every day.

2. **The restriction is ticker-specific and information-specific, not occupation-wide.** If you specifically know a non-public fact about Company X from your NVIDIA work, you cannot trade Company X until the information is public. You can still trade Company Y even if Company Y is in the same industry, unless you also hold MNPI about Company Y.

3. **Substitute securities doctrine applies narrowly, not broadly.** It catches cases where a trader specifically uses NVIDIA-internal information to trade a proxy (e.g., learning of a canceled NVIDIA product launch and shorting a competitor the next day). It does not catch cases where a trader holds general industry knowledge and trades on public information.

## What this means for the project as described

The project is: web-scraped public signals (Twitter, Reddit, news, weather, SEC, earnings calls) synthesized by an LLM into Kalshi prediction-market and equity signals. That is a lawful research and trading activity.

**Kalshi weather + NBA markets.** Zero insider-trading exposure. CFTC event contracts are not securities and the 10b-5 framework does not apply. No personal trade restrictions beyond ordinary CFTC anti-manipulation law, which is a non-issue for outcome markets you have no influence over.

**Equities research using public data.** Lawful. Standard operating procedure for any employee with a brokerage account. The guardrails below replace the Pass 2 blacklist.

## Corrected guardrails

**A. The NVDA rule.** Do not trade NVDA on any non-public information. For NVDA specifically, the conservative posture — given the volume of internal information you touch daily — is to trade NVDA only through NVIDIA's sanctioned channels (ESPP, 10b5-1 plans for RSUs) rather than on a discretionary basis. This is the one ticker where the "you have MNPI most of the time" presumption is approximately correct.

**B. The specific-knowledge rule.** For any ticker other than NVDA: if on a given day you specifically know a non-public material fact about that company from your NVIDIA work, do not trade it until that information becomes public (press release, filing, earnings call) or becomes stale. Stale means the information no longer moves the market. Most product or customer information goes stale within a quarter; roadmap information can take longer.

**C. The evidence trail rule.** For every signal you act on with real money, log `(source_urls[], retrieved_at, generated_at, model_or_method, reasoning)`. You should be able to show, for any trade, exactly which public sources informed it. This is good engineering hygiene independent of compliance and it is also your defense if anything is ever questioned.

**D. The blackout rule.** NVIDIA publishes a quarterly blackout calendar for Designated Individuals. Even if you are not on the Designated list, observe the same calendar voluntarily for NVDA. It is free insurance and removes the single highest-probability edge case where your knowledge of approaching earnings intersects with a personal trade.

**E. The household rule.** Rules B and D apply to trades by your spouse, minor children, and anyone whose trading is attributable to you under NVIDIA's policy. This is not a theoretical risk; it is the most common way compliance issues actually surface.

**F. The tipping rule.** Do not discuss specific non-public information from work with anyone who trades, including in casual conversation. This is the rule most likely to be broken accidentally.

## What is explicitly NOT restricted

The following are ordinary, lawful activities for an NVIDIA employee and were incorrectly flagged in Pass 2:

- Trading AMD, INTC, TSM, ASML, AMAT, LRCX, KLAC, MU, WDC, AVGO, MRVL, QCOM, ARM, MSFT, GOOGL, AMZN, META, ORCL, or any semiconductor / hyperscaler / tech-adjacent ticker on the basis of publicly available research, when you do not possess specific MNPI about that ticker.
- Holding and trading SMH, SOXX, QQQ, SPY and similar index ETFs.
- Running an LLM-based research agent that ingests public data (news, filings, social media, earnings transcripts) and produces equity signals.
- Building a supply-chain graph from SEC 10-K disclosures and publicly disclosed customer relationships.
- Trading on the output of that agent, for tickers not subject to rules A or B above.
- Reading SemiAnalysis, The Information, Stratechery, Digitimes, and similar publications and using them as inputs.

The Pass 2 section that implied these were all suspect was wrong.

## What changes for v1

The original Kalshi v1 gate is unchanged. **Scope update, October 10, 2026:** owner-approved equities research and paper trading are now active, so the public-information and evidence-trail guidance here applies to that work today. See [the current playbook amendment](../CLAUDE.md#current-scope-amendment--owner-direction-october-10-2026). This documentation update does not authorize stock execution or commercialization and does not change any legal conclusion elsewhere in this addendum.

## What changes for commercialization

The subscription-product analysis in Pass 2 and the forthcoming Pass 3 is a separate layer. Selling signals while employed at NVIDIA remains a real set of considerations — outside-activities disclosure, possible CTA/RIA registration depending on product shape, restrictions on recommending trades in names where you hold specific MNPI. Those are business-structure questions for Pass 3 with a lawyer, not default blacklists.

The one commercialization rule that does survive from Pass 2: if you ever publish trading signals on a ticker about which you specifically possess MNPI at the time of publication, you can create tipper liability. The solution is not to blacklist tickers — it is to ensure signals are generated from public data with an auditable trail (rule C), and to not publish signals during personal windows when you hold MNPI on the specific name.

## Bottom line

Build the project you described. Scrape public data, synthesize it with LLMs, generate signals, trade personally on public information, research equities freely. Keep the evidence trail. Do not trade NVDA on internal knowledge and do not trade any specific ticker about which you specifically hold non-public information at that moment. Revisit subscription-product specifics when you get there.
