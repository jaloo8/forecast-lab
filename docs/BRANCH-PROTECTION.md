# Branch Protection — recommended setup

GitHub keeps nudging you to enable this. Here's the solo-dev-friendly configuration that prevents "I just pushed straight to main at 11pm" mistakes without blocking you on yourself.

## Where to click

1. Go to **`https://github.com/jaloo8/forecast-lab/settings/branches`** (Repo → Settings → Branches in the sidebar)
2. Under **Branch protection rules**, click **Add classic branch protection rule** (or **Add ruleset** if GitHub steers you there)
3. **Branch name pattern:** `main`
4. Configure exactly these toggles ⤵

## The settings

| Setting | Value | Why |
|---|---|---|
| ✅ Require a pull request before merging | ON | Blocks accidental direct pushes to main |
| &nbsp;&nbsp;↳ Require approvals | **0** | You'd block yourself — leave at 0 |
| &nbsp;&nbsp;↳ Dismiss stale PR approvals when new commits are pushed | OFF | Irrelevant at 0 approvals |
| &nbsp;&nbsp;↳ Require review from Code Owners | OFF (for now) | Will turn on if collaborators added |
| ✅ Require status checks to pass before merging | ON | Forces CI green before merge |
| &nbsp;&nbsp;↳ Require branches to be up to date before merging | ON | Prevents merging on top of stale main |
| &nbsp;&nbsp;↳ Status checks that are required: | `check` | The CI job in `.github/workflows/ci.yml` |
| ✅ Require conversation resolution before merging | ON | Cheap insurance |
| ⬜ Require signed commits | OFF | Overkill for solo; you can add later |
| ⬜ Require linear history | OFF | We squash-merge anyway |
| ⬜ Require deployments to succeed | OFF | No deployment yet |
| ⬜ Lock branch | OFF | Need to be able to push PRs |
| ⬜ Do not allow bypassing the above settings | **ON** | Includes admins — closes the "I'll just admin-override" loophole |
| ⬜ Restrict who can push to matching branches | OFF | You're the only one |
| ⬜ Allow force pushes | OFF | Force-pushes to main are how history dies |
| ⬜ Allow deletions | OFF | Deleting main would be very bad |

## After clicking Save

Test it with a deliberate violation:

```bash
# Try to push directly to main (should be rejected)
echo "test" >> README.md
git add README.md && git commit -m "test direct push"
git push origin main
# Expected: "remote: error: GH006: Protected branch update failed"

# Roll it back
git reset --hard HEAD~1
```

If you see the GH006 rejection, protection is live. The PR workflow we've been using all session continues to work — branch + commit + PR, CI runs, you merge.

## The "Do not allow bypassing" toggle is the important one

By default, repo admins can bypass branch protection. Since you're the admin on a solo repo, that toggle is the only thing standing between "we have rules" and "rules are decorative." Leave it ON.

## When to revisit

- **If you add a collaborator:** turn on "Require approvals: 1"
- **If you ever take outside money / want enterprise hygiene:** turn on signed commits + CODEOWNERS-required reviews
- **If CI takes >5 min** and you start being tempted to skip it: that's the time to optimize CI, not weaken protection

## Emergency override

If you ever need to bypass protection in a real emergency (very rare), you can disable the rule, do the thing, re-enable. **Doing this without writing a postmortem note is how this discipline dies** — at minimum, leave a note in `docs/security/` describing what you did and why.
