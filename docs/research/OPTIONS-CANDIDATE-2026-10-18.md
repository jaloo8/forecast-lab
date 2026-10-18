# Independent options candidate — specification, not a profitable bot

Owner authorized public research and our own experiment if the reel's rules
cannot be found. The original reel caption actually says **1DTE**, not 0DTE.
This candidate is ours and does not reproduce Nicholas Fischer's system.
No options returns have been observed or used to tune this specification.

## Fixed experiment

- SPY only; bullish opening-range breakout; no universe search or AI score.
- Full regular sessions only. Opening range = 09:30–09:45 New York time.
  Use the first completed one-minute close strictly above its high from
  09:46 through 11:00. One opportunity per session; no re-entry.
- At the next minute boundary, choose standard calls expiring the next
  **calendar** day. If that expiration was not listed, skip. Do not manufacture
  daily expirations for historical years when they did not exist.
- Buy the listed strike nearest the signal close (tie: lower strike), sell
  the same expiration's call exactly $1 above it. Require both contracts in
  the contemporaneous chain. One spread, multiplier 100, no naked legs.
- Enter using long ask and short bid, with $0.01 adverse slippage per leg;
  charge $0.65 per contract per side. These are research assumptions, not a
  change to production costs. No midpoint fills or rebates.
- Separate $10,000 virtual ledger. Skip if entry debit plus entry fees and
  the $1.30 exit-fee reserve exceeds $100 or available cash. No leverage,
  fractional contracts, compounding size, or daily-profit lock.
- Exit at the next minute boundary after a completed underlying close below
  the opening-range low, or at 15:30, whichever comes first. Sell long at bid
  and buy short at ask, with the same slippage and fees. No overnight holding
  by design; failed exits remain unresolved, never silently marked at zero.
- Quotes must be non-crossed, finite, positive, timestamped no later than
  execution, at most five seconds old, and within one second of each other.
  Required displayed size >= one contract. Post-signal entry quotes only.
  These conditions still do not guarantee an actual atomic spread fill.

## Implementation boundary and evidence needed

`src/kq/equities/option_spread.py` implements the small quote/contract/cashflow
kernel, with synthetic arithmetic and rejection tests. It is **not** the
opening-range signal engine, a broker adapter, a historical options backtest,
or a production bot. No historical options performance is reported.

Required next inputs: original minute SPY bars, dated listed chains, both-leg
historical bid/ask and sizes, exchange sessions/early closes, and contract
adjustment/exercise metadata. Missing execution quotes make a candidate day
unscorable; they must not become an advantageous skipped trade. Retain missing
days and coverage alongside all outcomes. Test no-fill and extra-slippage
scenarios, and compare the same directional signal in SPY shares before
claiming options add value. Keep all dates in chronological development and
untouched evaluation blocks; cluster uncertainty by session and count variants.

## Why this is research, not a recommendation

[QuantConnect's published implementation](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/p1)
provides reproducible opening-range stock logic and links the Zarattini,
Barbon and Aziz study. Its stock-universe results do not validate this SPY
call-spread adaptation. Our 15-minute window, entry cutoff, contract choice
and time exit are explicit hypotheses, not optimized findings.

[Cboe's historical quote product](https://datashop.cboe.com/option-quote-intervals)
documents the relevant contract/quote fields and historical availability;
it is paid, and no purchase is authorized or made. Today's free chain cannot
reconstruct expired historical execution prices. Public stock bars alone are
insufficient. A subscription would buy evidence, not assured profits.

[OIC exercise guidance](https://www.optionseducation.org/referencelibrary/faq/options-exercise)
explains why exercise and assignment cannot be ignored for ETF options. The
planned same-day exit reduces exposure but does not guarantee a fill or remove
assignment risk. A live-capable implementation would require lifecycle handling.
