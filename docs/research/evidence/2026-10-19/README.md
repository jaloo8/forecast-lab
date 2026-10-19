# Published October 19 evidence

This directory is a curated GitHub handoff. It contains aggregate research results, review records and hashes, not raw market payloads or a complete machine backup. Copies are byte-identical to their cited local artifacts; `manifest.json` records source and published hashes. The generated validation/private-input metadata has its own hashes. Historical paths inside receipts describe their original provenance; use the repository-root `HANDOFF.md` for portable commands.

- `screen.json`: 24 fixed stock/cost cases, complete-year returns and the failed annual-floor screen. Original simulation capital and other limits remain explicit.
- `benchmark-screen.json`, `independent-check.json`, `receipts.json`, `methodology-receipts.json`: public benchmark calculations, independent cross-check and source retrieval/hash records. The raw Cboe histories and documents are not copied here.
- `independent-calculation-receipt.json`: second calculation of the stock and benchmark results; this is a saved historical check, not another new replay.
- `review-coverage.json`: original checkout reading scope/ranges/hashes, including the lockfile and encrypted-secret exceptions.
- `tradermonty-review-receipt.json`: pinned third-party commit, 43 distinct files, exact actual-read ranges and source hashes; 37 full and six partial reads totaling 12,742 lines. It records a targeted static review, not an entire-repository audit.
- `validation.json`: historical full-suite/targeted receipts and the current 13-test focused check. Test success is software evidence, not profitable execution.
- `branch-cleanup/`: 120 branch decisions, six reviewer reports, exact-tip and equivalent-patch proofs, read-coverage mappings, dry-run/deletion/readback receipts and backup verification metadata. No raw Git bundle, patches or executable cleanup script is included. Original bundle recovery remains owner-local. The cleanup's statement “one remote branch” is a dated observation before publishing this new active handoff branch.
- `private-inputs.json`: the private cache/wrapper and related-workspace transfer requirements. No key or paid download is needed to inspect these results or run source-only tests.

The full branch review records intentionally retain failures and superseded research evidence. Paths to a local review packet do not claim that the raw packet is included here. Git source revisions, original hashes, included read ranges and explicit limitations remain available for inspection.

To verify the copied evidence from this repository root, run the following with Python 3.12. It only reads files:

```python
import hashlib
import json
from pathlib import Path

base = Path("docs/research/evidence/2026-10-19")
manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
for row in manifest["source_copies"]:
    assert hashlib.sha256((base / row["path"]).read_bytes()).hexdigest() == row["published_sha256"]
for row in manifest["generated_files"]:
    assert hashlib.sha256((base / row["path"]).read_bytes()).hexdigest() == row["sha256"]
print("Published evidence hashes match")
```

The bounded `.gitattributes` rule preserves this evidence directory byte-for-byte across operating systems. Historical source worktree hashes in `validation.json` describe the original Windows bytes; source text may have normalized line endings in Git, so use the publication commit to identify the portable source version.

The source-only code and proposed workflow are on the handoff branch. A fresh clone cannot reproduce private/raw inputs that are deliberately excluded. Transfer those inputs privately and validate their original manifests before running a new frozen replay.
