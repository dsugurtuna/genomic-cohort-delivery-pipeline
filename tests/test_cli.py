"""Tests for the cohort-delivery CLI and __main__ module."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cohort_delivery import __version__
from cohort_delivery.cli import main


def test_cli_run_and_verify_roundtrip(fake_plink, batches, tmp_path, capsys):
    cfg_path = tmp_path / "pipeline.json"
    staging = tmp_path / "staging"
    cfg_path.write_text(
        json.dumps(
            {
                "project_id": "CLI01",
                "cohort_file": batches["cohort"],
                "exclusion_files": [batches["exclusions"]],
                "batch_prefixes": batches["prefixes"],
                "work_dir": str(tmp_path / "work"),
                "delivery_dir": str(tmp_path / "delivery"),
                "staging_root": str(staging),
                "plink_exec": fake_plink,
                "transfer_method": "copy",
            }
        ),
        encoding="utf-8",
    )

    rc = main(["run", "--config", str(cfg_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Filtered: 5 -> 4 samples" in out
    assert "Merged: 4 samples, 2 variants (excluded conflicts: 1)" in out
    assert "verified=True" in out

    staged_dirs = list(staging.iterdir())
    assert len(staged_dirs) == 1
    staged = staged_dirs[0]

    assert main(["verify", str(staged)]) == 0
    verify_out = capsys.readouterr().out
    assert "OK: verified" in verify_out

    # Tampering causes fail-closed exit code 1.
    (staged / "CONFLICT_VARIANTS.txt").write_text("tampered\n")
    assert main(["verify", str(staged)]) == 1
    err = capsys.readouterr().err
    assert "CONFLICT_VARIANTS.txt" in err


def test_cli_verify_fails_on_missing_directory(tmp_path, capsys):
    rc = main(["verify", str(tmp_path / "missing")])
    assert rc == 1
    assert "Error:" in capsys.readouterr().err


def test_cli_run_rejects_unknown_config_keys(tmp_path, capsys):
    cfg = tmp_path / "bad.json"
    cfg.write_text(json.dumps({"cohort_file": "x", "bogus": 1}), encoding="utf-8")
    rc = main(["run", "--config", str(cfg)])
    assert rc == 1
    assert "Unknown config keys" in capsys.readouterr().err


def test_module_entrypoint_version():
    src_dir = str(Path(__file__).resolve().parent.parent / "src")
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{existing}" if existing else src_dir
    proc = subprocess.run(
        [sys.executable, "-m", "cohort_delivery", "--version"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0
    assert __version__ in proc.stdout
