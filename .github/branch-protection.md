# Branch protection + merge queue (WP-ENV-03 acceptance ⑥ ⑦ — MANUAL repo-admin step)

## The honest gap

WP-ENV-03 acceptance ⑥/⑦ want an **actual merge block**: a diff that violates
ownership, or a WP carrying a `FAIL_BLOCKING` gate, must be **refused merge** by the
platform. That refusal is a GitHub **branch-protection + merge-queue** setting, and
it can only be applied by a **repository admin** through the GitHub API/UI. It
**cannot** be configured from CI or from this repository's code.

**What is enforced in-repo (green, tested):** the CI checks and the local
ownership-diff gate (`.github/ownership_diff.py`) and gate-state reporter
(`.github/gate_report.py`). A violating diff makes the check **red**, and a
`FAIL_BLOCKING` gate makes `merge_decision` return blocked (see `tests/env03`).

**What is NOT enforced until an admin applies the config below:** the platform
turning that red check into a *merge refusal*. Until then a red check is advisory —
someone with merge rights could still merge past it. **Do not report the merge gate
as enforced; only the CI check exists in-repo.**

## Required steps for a repository admin

Apply on the default branch (`main`):

1. **Require a pull request before merging** (no direct pushes to `main`).
2. **Require status checks to pass** — mark every check below as *Required*:
   - `quality` (ci.yml)
   - `registry` (ci.yml)
   - `lint` (env.yml)
   - `invariant-static` (env.yml)
   - `ledger-verify` (env.yml)
   - `ownership-verify` (env.yml)
   - `pin-verify` (env.yml)
   - `contract-regress` (env.yml)
3. **Require branches to be up to date before merging.**
4. **Enable a merge queue** on `main` so required checks run against the exact merge
   commit, not a stale branch head.
5. **Include administrators** (do not let admins bypass the required checks).

### CLI form (admin credentials required — will 403 without repo-admin)

```bash
gh api -X PUT repos/:owner/:repo/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[checks][][context]=quality' \
  -f 'required_status_checks[checks][][context]=registry' \
  -f 'required_status_checks[checks][][context]=lint' \
  -f 'required_status_checks[checks][][context]=invariant-static' \
  -f 'required_status_checks[checks][][context]=ledger-verify' \
  -f 'required_status_checks[checks][][context]=ownership-verify' \
  -f 'required_status_checks[checks][][context]=pin-verify' \
  -f 'required_status_checks[checks][][context]=contract-regress' \
  -f 'enforce_admins=true' \
  -f 'required_pull_request_reviews[required_approving_review_count]=1' \
  -f 'restrictions='
# Merge queue is set under repo Settings → Branches → merge queue (or the GraphQL API).
```

The ownership-diff gate itself runs inside `ownership-verify`; wiring a per-PR
declared-WP into that job (so ⑥ blocks the exact PR) is the one piece that needs the
PR's declared WP, which a repo-admin workflow input supplies at merge-queue time.
