# Security

This repo contains personal trading infrastructure that will eventually hold API keys, a Kalshi RSA private key, and (if Phase 5 passes) access to a live-money account. Treat it accordingly.

## What's in scope

- `*.pem`, `*.key` — Kalshi RSA keys
- `.env` — all API keys (Kalshi, Anthropic, OpenAI, Odds API, etc.)
- `data/` — may contain trade history and P&L
- `trade_log/`, `costs/llm.csv` — private
- `secrets/` — any local credential files

## Rules

1. **Never commit `.env`, `*.pem`, or anything under `secrets/`.** `.gitignore` enforces this; review `git status` before every commit.
2. **Rotate any key that touches git history**, even in a private repo. Private ≠ safe; GitHub employees, future collaborators, and leaked access tokens all see history.
3. **Store the Kalshi private key with file permissions `0600`.** `chmod 600 secrets/kalshi.pem`.
4. **Use distinct API keys for dev and prod.** Kalshi demo environment keys are separate — never mix.
5. **Set a monthly budget cap in the Anthropic console** as a last-resort circuit breaker for the v2 agent.
6. **On the Windows PC**, run the ingest / paper-trader under a dedicated non-admin Windows user with minimum file access. Don't run as the same user that logs into Steam or personal email.
7. **Egress allowlist** the agent's outbound connections (Windows Firewall or WSL2 iptables). See CLAUDE.md §10.
8. **Backups** encrypted at rest (`restic` or `rclone crypt`). Test restore quarterly.

## If you suspect a credential exposure

1. Rotate the key immediately in the issuing console (Kalshi, Anthropic, etc.).
2. Audit recent API usage for unauthorized calls.
3. If `git` history contains the secret, rewrite with `git filter-repo` or BFG Repo-Cleaner; force-push; notify any collaborators.
4. Rotate the key *again* if force-pushes are not honored by your hosting provider.

## Reporting

This is a personal repo; there is no external reporting channel. For any security concern, open a local note in `docs/security/` and address before continuing work.
