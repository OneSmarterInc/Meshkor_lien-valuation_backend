"""Django's own records about the reference data (stored in PostgreSQL).

The reference rows themselves are NOT here; they live in Parquet and in the
DuckDB tables. These models answer: which file was loaded, when, with what
hash, how many rows, and did verification pass.
"""
from django.db import models


class SourceFile(models.Model):
    """One original CMS download (Spec §3.2)."""
    table = models.CharField(max_length=64, db_index=True)
    period = models.CharField(max_length=64)
    path = models.CharField(max_length=512, help_text="relative to data/raw/")
    sha256 = models.CharField(max_length=64, db_index=True)
    size_bytes = models.BigIntegerField()
    page_url = models.URLField(max_length=500, blank=True)
    members = models.JSONField(default=list, blank=True)
    first_loaded_at = models.DateTimeField(auto_now_add=True)
    last_loaded_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["table", "path", "sha256"], name="uniq_source_file")]
        ordering = ["table", "period"]

    def __str__(self):
        return f"{self.table} {self.period} {self.path}"


class LoadRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running"
        SUCCESS = "success"
        SKIPPED = "skipped"    # no raw files yet
        FAILED = "failed"

    table = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    seconds = models.FloatField(null=True, blank=True)
    rows = models.BigIntegerField(null=True, blank=True)
    output_path = models.CharField(max_length=512, blank=True)
    periods = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    sources = models.ManyToManyField(SourceFile, blank=True, related_name="load_runs")
    manifest = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]
        get_latest_by = "started_at"

    def __str__(self):
        return f"{self.table} {self.status} {self.started_at:%Y-%m-%d %H:%M}"


class DuckDBBuild(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    path = models.CharField(max_length=512)
    size_bytes = models.BigIntegerField()
    seconds = models.FloatField()
    tables = models.JSONField(default=dict)
    objects_created = models.JSONField(default=list)
    objects_skipped = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = "created_at"


class VerifyRun(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    passed = models.IntegerField()
    failed = models.IntegerField()
    not_run = models.IntegerField()
    checks = models.JSONField(default=list)
    tables = models.JSONField(default=dict)
    report_markdown = models.TextField()

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = "created_at"

    def __str__(self):
        return f"verify {self.created_at:%Y-%m-%d %H:%M}: {self.passed} pass / {self.failed} fail"
