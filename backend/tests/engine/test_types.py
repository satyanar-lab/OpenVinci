"""Engine types — small, but enforce the contract every layer depends on."""

from __future__ import annotations

from engine import Fix, Issue, Location, Severity, ValidationReport


def test_location_renders_rfc6901_pointer():
    loc = Location("CanIf", ("networks", 0, "RxPdus", 2))
    assert loc.json_pointer() == "/networks/0/RxPdus/2"


def test_location_empty_path_is_root_pointer():
    assert Location("Com").json_pointer() == ""


def test_location_escapes_tilde_and_slash():
    loc = Location("Com", ("path/with~weird",))
    assert loc.json_pointer() == "/path~1with~0weird"


def test_report_partitions_by_severity():
    err = _issue(Severity.ERROR, "a")
    warn = _issue(Severity.WARNING, "b")
    info = _issue(Severity.INFO, "c")
    report = ValidationReport(issues=[err, warn, info])
    assert report.errors == [err]
    assert report.warnings == [warn]
    assert not report.ok


def test_report_ok_when_no_errors():
    report = ValidationReport(issues=[_issue(Severity.WARNING, "soft")])
    assert report.ok


def test_report_filters_by_rule_id():
    a = _issue(Severity.ERROR, "a", rule="x.one")
    b = _issue(Severity.ERROR, "b", rule="x.two")
    report = ValidationReport(issues=[a, b])
    assert report.by_rule("x.one") == [a]


def test_fix_serializable_via_dataclass_asdict():
    from dataclasses import asdict

    fix = Fix(
        description="add it",
        patches={"CanIf": [{"op": "add", "path": "/foo", "value": 1}]},
    )
    payload = asdict(fix)
    assert payload["description"] == "add it"
    assert payload["patches"]["CanIf"][0]["op"] == "add"


def _issue(severity: Severity, message: str, *, rule: str = "test.rule") -> Issue:
    return Issue(rule=rule, severity=severity, message=message, location=Location("Com"))
