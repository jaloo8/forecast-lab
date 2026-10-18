# Protecting main: verified state and recommended setup

## Verified October 10, 2026

`jaloo8/forecast-lab` is private. GitHub reports `main` as **unprotected** (`protected: false`). The authenticated account has repository admin access, but both the branch-protection and repository-rulesets endpoints return HTTP 403: "Upgrade to GitHub Pro or make this repository public to enable this feature."

This is a plan limitation, not missing push credentials. No settings, visibility or subscription were changed. Keep the repository private. Protection for private repositories requires an eligible paid plan, as described in [GitHub's protected-branch documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

## Why it is useful here

A protected main branch gives research changes a stable integration boundary. It can require a pull request and passing checks, prevent accidental history rewrites/deletion, and apply the same rules to agents and human pushes. This matters as studies, operational paper ledgers and multiple development branches coexist.

It does not validate a financial hypothesis, deploy code, back up local data, or prove that secrets are absent. It supplements human review and the existing paper/live safeguards.

Until GitHub enforcement is available, continue the current convention: feature branches, reviewed pull requests, passing CI and explicit human review before merging. This is a working agreement; GitHub currently does not enforce it on `main`.

## Recommended solo-owner configuration

If the owner chooses an eligible plan, configure a rule for `main` under [repository branch settings](https://github.com/jaloo8/forecast-lab/settings/branches). The recommendation is not a record of enabled settings.

| Setting | Recommendation | Reason |
| --- | --- | --- |
| Require a pull request | On | Make the change and its checks reviewable before integration |
| Require approving reviews | Off while there is no second reviewer | The author cannot approve their own PR; review the diff personally before merging |
| Require status checks | On | Block integration when verification fails |
| Required checks | `check (ubuntu-latest)`, `check (windows-latest)`, `security` | Actual check names observed on PR #204 and defined by the CI matrix/security job |
| Require branch up to date | On | Recheck integration against the current base |
| Require conversation resolution | On | Address review threads before merging |
| Include administrators / disallow bypass | On | Enforce the rule for the account doing the work |
| Allow force pushes | Off | Preserve main history |
| Allow deletions | Off | Preserve the stable branch |
| Signed commits, deployments, merge queue | Leave unrequired initially | Add only when the associated workflow exists |

Reconfirm check names from a recent successful PR before configuring them; a required name that never runs can block every merge. Stacked research PRs should integrate from the bottom up, with CI rechecked after changing their base. Add one required independent approval when a second reviewer is available. Do not confuse zero required GitHub approvals with permission to skip the project's human review rule.

## Verify without changing main

Read the saved rule/settings and inspect a recent PR's merge requirements. From an authenticated GitHub CLI, these are read-only checks:

```sh
gh api repos/jaloo8/forecast-lab/branches/main --jq '{name, protected}'
gh api repos/jaloo8/forecast-lab/branches/main/protection
gh api repos/jaloo8/forecast-lab/rulesets
```

A `protected: true` response alone is insufficient: verify required checks, PR requirements and admin enforcement in the effective settings too. An API error is not successful verification. Do not test protection by pushing a deliberate violation to `main`, and do not use a hard reset to undo such a test.

If an owner-approved emergency requires temporarily changing a rule, record the reason and restore/recheck enforcement afterward. A repository administrator can change policy; protection reduces accidental bypass, not the administrator's ultimate control.
