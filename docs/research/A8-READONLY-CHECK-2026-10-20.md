# A8 read-only connection check — October 20, 2026

**A8 was unreachable from this workstation using the documented SSH
connection.** One attempt began at **17:02:59.621 UTC** and returned exit
code **255** after **10.094 seconds**:

```text
ssh: connect to host 100.108.199.57 port 22: Connection timed out
```

The target came from the existing
[Stock Paper Lab connection recipe](../STOCK-PAPER-LAB.md)
at lines 110–119, not a guessed host. The check used `BatchMode=yes`,
`ConnectTimeout=10`, `ConnectionAttempts=1` and
`StrictHostKeyChecking=yes`; password/interactive authentication, agent
forwarding and automatic host-key updates were disabled. No tunnel was
opened and no alternate endpoint or second connection was tried.

The timeout occurred before authentication or remote command execution.
Consequently **hostname/remote UTC, deployed Git commit, current snapshot
and ledger timestamps, stored scheduler audit, and the documented
`\StockPaperLab\Dashboard` task's status/history were not observed**.
The October 18 health report remains dated historical evidence; it is not
current verification. The desktop `stock-paper-pilot` heartbeat and the
server dashboard task are separate mechanisms.

No credential-file contents were read by this review. No installer,
scheduler configuration, lease, order, account, remote file or registry
was changed. The preparation registry remains disabled; this failed probe
cannot satisfy activation readiness.

The precise blocker is connectivity to the documented host's SSH port.
This attempt does not distinguish an unavailable network/VPN route,
powered-off host, stopped SSH service or firewall behavior. Restore the
expected A8 network reachability before a later explicitly bounded
inspection; no network repair or retry was performed here.

The [machine receipt](evidence/2026-10-20-a8-paper/live-preflight.json)
preserves local timing, options, exit status and the not-observed fields.
