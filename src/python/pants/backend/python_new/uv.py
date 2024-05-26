# Copyright 2024 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from pants.core.util_rules.external_tool import (
    DownloadedExternalTool,
    TemplatedExternalTool,
    download_external_tool,
)
from pants.engine.platform import Platform
from pants.engine.rules import collect_rules, rule
from pants.util.meta import classproperty


class UVSubsystem(TemplatedExternalTool):
    options_scope = "uv"
    name = "uv"
    help = "The UV package installer and resolver (https://github.com/astral-sh/uv)."

    default_version = "0.2.3"
    default_url_platform_mapping = {
        "macos_x86_64": "x86_64-apple-darwin",
        "macos_arm64": "aarch64-apple-darwin",
        "linux_x86_64": "x86_64-unknown-linux-gnu.tar.gz",
        "linux_arm64": "aarch64-unknown-linux-musl.tar.gz",
    }
    default_url_template = (
        "https://github.com/astral-sh/uv/releases/download/{version}/uv-{platform}.tar.gz"
    )
    version_constraints = "==0.2.3"

    @classproperty
    def default_known_versions(cls):
        return [
            "0.2.3|macos_x86_64|79c28e2121d4299a2190ab0c8f149d676a6d623a4396c86cda947a9280f494a8|11939920",
            "0.2.3|macos_arm64 |20e466f87ebeda26da0fff5306ad998375fe1e27d2514e4b4f5711f9fad6bcee|11688945",
            "0.2.3|linux_x86_64|d94b9f679b3718ed0f62eee1126f02f1552301b7dc473a7dc3727f20b889e057|12980930",
            "0.2.3|linux_arm64 |8574f4d4c56b87eb0e9041f984d8e79d98c53d2183533c2196f8a6dd16944929|12302546",
        ]


class UV(DownloadedExternalTool):
    """The UV binary."""


@rule
async def download_uv(uv_subsystem: UVSubsystem, platform: Platform) -> UV:
    downloaded_uv = await download_external_tool(uv_subsystem.get_request(platform))
    return UV(digest=downloaded_uv.digest, exe=downloaded_uv.exe)


def rules():
    return collect_rules()
