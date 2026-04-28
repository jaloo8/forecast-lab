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
2. **Never paste secrets into a chat, support ticket, screenshot, Slack/Discord/email, or any other interface that isn't your own terminal or editor.** This includes: AI assistants (Claude, ChatGPT, Cursor chat, Copilot chat), GitHub issues/PRs/comments, Stack Overflow questions, screen-share recordings. Any credential that lands in those places is **compromised** — rotate it immediately, no exceptions, even if the chat is "private." The reflex matters at zero stakes (demo) so it's automatic at high stakes (live).
3. **Rotate any key that touches git history**, even in a private repo. Private ≠ safe; GitHub employees, future collaborators, and leaked access tokens all see history.
4. **Store the Kalshi private key with file permissions `0600`.** `chmod 600 secrets/kalshi.pem`.
5. **Use distinct API keys for dev and prod.** Kalshi demo environment keys are separate — never mix.
6. **Set a monthly budget cap in the Anthropic console** as a last-resort circuit breaker for the v2 agent.
7. **On the Windows PC**, run the ingest / paper-trader under a dedicated non-admin Windows user with minimum file access. Don't run as the same user that logs into Steam or personal email.
8. **Egress allowlist** the agent's outbound connections (Windows Firewall or WSL2 iptables). See CLAUDE.md §10.
9. **Backups** encrypted at rest (`restic` or `rclone crypt`). Test restore quarterly.

## What you CAN paste into AI chats / tickets / etc.

When debugging with an AI assistant or filing a bug report, share:

- **Error messages and tracebacks** — `KalshiCredentialsError: KALSHI_API_KEY_ID is empty`, `HTTP 401 from https://demo-api.kalshi.co/...`, `FileNotFoundError: secrets/kalshi.pem`. None of these contain credentials.
- **The names** of env vars, file paths, or config keys — `KALSHI_API_KEY_ID`, `secrets/kalshi.pem`, `KALSHI_ENV=demo`. Names are public; values are not.
- **The shape** of `.env.example` — which is already in git and contains zero real values.

If you're ever unsure whether something is safe to paste: assume it isn't, redact, and ask first.

## If you suspect a credential exposure

1. Rotate the key immediately in the issuing console (Kalshi, Anthropic, etc.).
2. Audit recent API usage for unauthorized calls.
3. If `git` history contains the secret, rewrite with `git filter-repo` or BFG Repo-Cleaner; force-push; notify any collaborators.
4. If a chat / ticket / screenshot contains the secret, **delete the message** if the platform allows it (and remember the platform may still retain it server-side). Rotate regardless of deletion success.
5. Rotate the key *again* if force-pushes are not honored by your hosting provider.

## Reporting

This is a personal repo; there is no external reporting channel. For any security concern, open a local note in `docs/security/` and address before continuing work.
