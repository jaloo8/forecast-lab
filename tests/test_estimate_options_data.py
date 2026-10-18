import json
import runpy
import sys
from pathlib import Path

import httpx
import pytest

import kq.clients.databento_metadata as module
from kq.clients.databento_metadata import MetadataClient

KEY = "db-" + "x" * 29


def test_command_uses_only_free_cost_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json=2.25)

    monkeypatch.setattr(
        module,
        "MetadataClient",
        lambda key: MetadataClient(key, transport=httpx.MockTransport(handle)),
    )
    credentials = tmp_path / "key.env"
    credentials.write_text("DATABENTO_API_KEY=" + KEY)
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            [
                dict(
                    name="pilot",
                    dataset="OPRA.PILLAR",
                    schema="cmbp-1",
                    symbols=["SPY.OPT"],
                    stype_in="parent",
                    start="2026-10-15T00:00:00Z",
                    end="2026-10-16T00:00:00Z",
                )
            ]
        )
    )
    output = tmp_path / "receipt.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "estimate",
            "--credentials",
            str(credentials),
            "--plan",
            str(plan),
            "--output",
            str(output),
        ],
    )
    runpy.run_path(
        str(Path(__file__).parents[1] / "scripts/estimate_options_data.py"), run_name="__main__"
    )
    receipt = json.loads(output.read_text())
    assert receipt["data_jobs_submitted"] == 0
    assert receipt["estimates"][0]["estimated_usd"] == "2.25"
    assert KEY not in output.read_text()
    assert seen == ["/v0/metadata.get_cost"]
    with pytest.raises(FileExistsError):
        runpy.run_path(
            str(Path(__file__).parents[1] / "scripts/estimate_options_data.py"),
            run_name="__main__",
        )
    assert seen == ["/v0/metadata.get_cost"]
    invalid_plan = json.loads(plan.read_text())
    invalid_plan[0]["symbols"] = "SPY"
    plan.write_text(json.dumps(invalid_plan))
    monkeypatch.setattr(sys, "argv", [*sys.argv[:-1], str(tmp_path / "invalid.json")])
    with pytest.raises(ValueError, match="symbols"):
        runpy.run_path(
            str(Path(__file__).parents[1] / "scripts/estimate_options_data.py"),
            run_name="__main__",
        )
    assert seen == ["/v0/metadata.get_cost"]
