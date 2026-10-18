# Two owner-supplied repositories: relevance review

Checked October 18, 2026. Read-only repository/document review; no installation,
subscription, account connection, code reuse, security certification or deployment.

## Awesome Systematic Trading

[The repository](https://github.com/paperswithbacktest/awesome-systematic-trading)
is useful as a research index: papers, backtesting/risk libraries and data tools.
Its strategy table explicitly selects strong replications, uses different
historical windows and reports Sharpe **gross of trading costs**. Ranking those
numbers is not a fair prospective strategy comparison; multiple-testing and
selection effects remain. The host's results have not been independently audited
here. Some linked datasets/code require account unlocks or payment.

Our proposed use: add candidates to a small, frozen research queue. Start with
trend/momentum, reversal and diversification/risk allocation; prefer hypotheses
supported by data already cached. For each, follow the original paper, record
publication date and all tested variants, replicate net of costs on matching
calendars, then evaluate post-publication and chronological holdout performance.
Do not merge strategies merely because each has a favorable selected backtest.
No change to the current frozen SPY options candidate follows from this index.

## Agents Office

[The README](https://github.com/ajsahni/agents-office) describes a local 3D office
for routing tasks to Claude-connected agents. It is a beta agent workspace,
not a trading engine or proof of strategy quality. Its dependency manifest uses
Node 20+, Three.js/esbuild and optional Anthropic integration. No runtime or
resource benchmark was performed here.

The [license](https://github.com/ajsahni/agents-office/blob/main/LICENSE) includes
additional restrictions on rebranding and adapting it to display/front another
system or product, requiring written permission for excluded uses. Do not copy
or integrate it as Forecast Lab's dashboard without resolving that permission.

An independently implemented interface could use the general office idea:
four labelled areas for data collection, research, paper trading and monitoring.
Each must show real job timestamps, freshness, progress and failures; animation
must never imply work is occurring. Keep realized P&L, open exposure, costs and
missing-data coverage prominent, with an accessible compact list on phones.
These are UI design proposals, not a request to start dozens of live agents.

Next priority stays validated data and reproducible backtests. An optional
original dashboard can follow once its operational status sources are reliable.
