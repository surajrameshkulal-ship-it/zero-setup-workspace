from __future__ import annotations
from types import SimpleNamespace

from app.models.rule import Severity
from app.services.architecture_checker import ArchitectureRuleChecker
from app.services.types import ChangedFile


def test_architecture_checker_detects_forbidden_import() -> None:
    rule = SimpleNamespace(
        id="arch-1",
        name="API cannot import persistence directly",
        description="API handlers should call services instead of repositories.",
        source_path_pattern="backend/app/api/**/*.py",
        forbidden_import_pattern=r"app\.models",
        severity=Severity.HIGH,
        is_active=True,
    )
    files = [
        ChangedFile(
            path="backend/app/api/v1/scans.py",
            status="modified",
            patch="",
            additions=1,
            deletions=0,
            content="from app.models.scan import PullRequestScan\n",
        )
    ]

    violations = ArchitectureRuleChecker().check(files, [rule])

    assert len(violations) == 1
    assert violations[0]["category"] == "architecture"
    assert violations[0]["line"] == 1

