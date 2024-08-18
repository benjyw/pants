# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.backend.python.util_rules.pex_cli import PexCli
from pants.core.util_rules.external_tool import (
    DownloadedExternalTool,
    download_external_tool,
)
from pants.engine.platform import Platform
from pants.engine.rules import collect_rules, rule
from pants.util.meta import classproperty


class PexSubsystem(PexCli):

    default_version = "v2.16.2"
    default_url_template = (
        "https://github.com/pex-tool/pex/releases/download/{version}/pex"
    )
    version_constraints = ">=2.16.2"

    @classproperty
    def default_known_versions(cls):
        return [
            "|".join(
                (
                    cls.default_version,
                    plat,
                    "f2ec29dda754c71a8b662e3b4a9071aef269a9991ae920666567669472dcd556",
                    "4284448",
                )
            )
            for plat in ["macos_arm64", "macos_x86_64", "linux_x86_64", "linux_arm64"]
        ]


class Pex3(DownloadedExternalTool):
    """The Pex 3 binary."""


@rule
async def download_pex3(pex3_subsystem: PexSubsystem, platform: Platform) -> Pex3:
    downloaded_pex = await download_external_tool(pex3_subsystem.get_request(platform))
    return Pex3(digest=downloaded_pex.digest, exe=downloaded_pex.exe)


def rules():
    return collect_rules()
