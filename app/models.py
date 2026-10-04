from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Assertion:
    name: str
    passed: bool
    expected: str = ""
    actual: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CaseResult:
    cid: str
    title: str
    status: str = "BLOCK"
    detail: str = ""
    started_at: str = ""
    ended_at: str = ""
    elapsed_ms: int = 0
    assertions: list[Assertion] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)

    def add(self, a: Assertion) -> Assertion:
        self.assertions.append(a)
        return a

    def finalize(self) -> "CaseResult":
        if self.status in ("SKIP", "MANUAL"):
            return self
        fails = [a for a in self.assertions if not a.passed]
        if fails:
            self.status = "FAIL"
            if not self.detail:
                self.detail = fails[0].detail or fails[0].name
        elif self.assertions:
            self.status = "PASS"
            if not self.detail:
                self.detail = f"{len(self.assertions)} 条断言通过"
        return self

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class RunReport:
    run_id: str
    suite: str
    serial: str
    aios: str
    apk: str
    locked: bool
    started_at: str
    ended_at: str = ""
    source: str = ""
    results: list[CaseResult] = field(default_factory=list)
    error: str = ""

    @property
    def summary(self) -> dict[str, int]:
        keys = ("PASS", "FAIL", "SKIP", "MANUAL", "BLOCK")
        return {k: sum(1 for r in self.results if r.status == k) for k in keys}

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "suite": self.suite,
            "serial": self.serial,
            "aios": self.aios,
            "apk": self.apk,
            "locked": self.locked,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "source": self.source,
            "error": self.error,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary,
        }
