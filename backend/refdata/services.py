"""Glue between Django and the pipeline. The pipeline does the work; these
functions record what happened in PostgreSQL."""
from __future__ import annotations

import traceback

from django.db import transaction
from django.utils import timezone

from pipeline import duckdb_build, runner, verify
from pipeline.common.raw import RawFileMissing

from .models import DuckDBBuild, LoadRun, SourceFile, VerifyRun


def load_table(table: str, periods: list[str] | None = None) -> LoadRun:
    run = LoadRun.objects.create(table=table, periods=periods or [])
    try:
        result = runner.run_table(table, periods=periods)
    except RawFileMissing as e:
        run.status, run.error = LoadRun.Status.SKIPPED, str(e)
    except Exception as e:  # noqa: BLE001 — record every failure
        run.status, run.error = LoadRun.Status.FAILED, f"{e}\n\n{traceback.format_exc()}"
    else:
        with transaction.atomic():
            run.status = LoadRun.Status.SUCCESS
            run.rows, run.output_path = result.rows, result.output
            run.seconds, run.warnings = result.seconds, result.warnings
            run.manifest = result.to_json()
            srcs = []
            for s in result.sources:
                sf, _ = SourceFile.objects.update_or_create(
                    table=table, path=s.file, sha256=s.sha256,
                    defaults={"period": s.period, "size_bytes": s.size_bytes,
                              "page_url": s.page or "", "members": s.members})
                srcs.append(sf)
            run.save()
            run.sources.set(srcs)
    run.finished_at = timezone.now()
    run.save()
    return run


def build_duckdb() -> DuckDBBuild:
    s = duckdb_build.build()
    return DuckDBBuild.objects.create(path=s["path"], size_bytes=s["size_bytes"], seconds=s["seconds"],
                                      tables=s["tables"], objects_created=s["objects_created"],
                                      objects_skipped=s["objects_skipped"])


def verify_step1(rehash: bool = True) -> tuple[VerifyRun, str]:
    rep = verify.run(rehash=rehash)
    path = verify.write(rep)
    c = rep.counts
    from dataclasses import asdict
    vr = VerifyRun.objects.create(passed=c["PASS"], failed=c["FAIL"], not_run=c["NOT RUN"],
                                  checks=[asdict(x) for x in rep.checks], tables=rep.tables,
                                  report_markdown=verify.to_markdown(rep))
    return vr, str(path)
