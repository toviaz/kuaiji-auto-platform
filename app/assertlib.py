from __future__ import annotations

import re

from .models import Assertion, CaseResult


class Checks:
    """软断言：失败不立刻抛，汇总到 CaseResult。"""

    def __init__(self, result: CaseResult):
        self.result = result

    def _add(self, name: str, passed: bool, expected: str, actual: str, detail: str = "") -> bool:
        self.result.add(
            Assertion(
                name=name,
                passed=passed,
                expected=str(expected),
                actual=str(actual),
                detail=detail or ("" if passed else f"{name} 不满足"),
            )
        )
        return passed

    def truthy(self, name: str, cond: bool, detail: str = "") -> bool:
        return self._add(name, bool(cond), "true", str(bool(cond)), detail)

    def equals(self, name: str, actual, expected) -> bool:
        return self._add(name, actual == expected, str(expected), str(actual))

    def contains(self, name: str, haystack: str, needle: str) -> bool:
        text = haystack or ""
        return self._add(name, needle in text, f"包含 {needle!r}", text[:200])

    def contains_any(self, name: str, haystack: str, needles: list[str]) -> bool:
        text = haystack or ""
        ok = any(n in text for n in needles)
        return self._add(name, ok, f"包含任一 {needles}", text[:200])

    def match(self, name: str, text: str, pattern: str) -> bool:
        ok = bool(re.search(pattern, text or ""))
        return self._add(name, ok, pattern, (text or "")[:200])

    def ge(self, name: str, actual: int, expected: int) -> bool:
        return self._add(name, actual >= expected, f">= {expected}", str(actual))
