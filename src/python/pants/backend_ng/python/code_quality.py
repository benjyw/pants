# Copyright 2026 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from dataclasses import dataclass
from pants.backend_ng.python.uv import UvProcessResult
from pants.engine.collection import Collection
from pants.engine.engine_aware import EngineAwareReturnType
from pants.util.logging import LogLevel


@dataclass(frozen=True)
class CodeQualityResult(EngineAwareReturnType):
    uv_result: UvProcessResult

    def exit_code(self) -> int:
        return self.uv_result.exit_code

    def message(self) -> str | None:
        return self.uv_result.message()

    def level(self) -> LogLevel | None:
        if self.exit_code() != 0:
            return LogLevel.ERROR
        return LogLevel.INFO

    def cacheable(self) -> bool:
        return False  # Always render


class CodeQualityResults(Collection[CodeQualityResult]):
    def exit_code(self) -> int:
        for result in reversed(self):
            if (ec := result.exit_code()):
                return ec
        return 0
