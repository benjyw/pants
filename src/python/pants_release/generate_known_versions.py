#!/usr/bin/env python3
# Copyright 2026 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

"""Generate known_versions_default data for ExternalBinary classes by scraping GitHub releases.

Usage:
    python src/python/pants_release/generate_known_versions.py --project uv --min-version 0.5.0
"""

import argparse
import json
import logging
from urllib.request import Request, urlopen

GITHUB_API_URL = "https://api.github.com/repos/{repo}/releases"

KNOWN_PROJECTS = {
    "uv": {
        "path": "src/python/pants/backend_ng/python/uv_known_versions.json",
        "repo": "astral-sh/uv",
        "platforms": {
            "linux_x86_64": "uv-x86_64-unknown-linux-gnu.tar.gz",
            "linux_arm64": "uv-aarch64-unknown-linux-gnu.tar.gz",
            "macos_arm64": "uv-aarch64-apple-darwin.tar.gz",
        },
    },
}


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string like '0.4.22' or 'v1.2.3' into a tuple for comparison."""
    if version_str.startswith("v"):
        version_str = version_str[1:]
    # We should have already filtered out prereleases, so it's OK to choke on non-numeric parts.
    return tuple(int(x) for x in version_str.split("."))


def fetch_json(url: str) -> dict:
    request = Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", "pants-known-versions-generator")
    with urlopen(request) as response:
        return dict(json.loads(response.read().decode()))


def get_all_releases(repo: str, min_version: str) -> list[dict]:
    """Fetch all releases from GitHub API that are >= min_version."""
    releases: list[dict] = []
    page = 1
    per_page = 100
    base_url = GITHUB_API_URL.format(repo=repo)
    min_version_tuple = parse_version(min_version)

    while True:
        url = f"{base_url}?per_page={per_page}&page={page}"
        logging.info(f"Fetching releases page {page}...")
        page_releases = fetch_json(url)

        if not page_releases:
            break

        for release in page_releases:
            tag = release.get("tag_name", "")
            if release.get("prerelease") or release.get("draft"):
                continue
            if parse_version(tag) < min_version_tuple:
                # Releases are sorted newest-first, so we can stop here.
                return releases

            releases.append(release)

        page += 1

    return releases


def process_release(release: dict, platform_to_asset: dict[str, str]) -> tuple[str, dict | None]:
    """Process a single release and return version and platform data."""
    tag = release["tag_name"]
    version = tag.lstrip("v")
    assets = {asset["name"]: asset for asset in release.get("assets", [])}

    platform_data = {}
    for platform, asset_name in platform_to_asset.items():
        if asset_name not in assets:
            logging.warning(f"{asset_name} not found for {version}. Skipping.")
            continue

        asset = assets[asset_name]
        digest = asset.get("digest", "")
        if not digest.startswith("sha256:"):
            logging.warning(f"No sha256 digest for {asset_name} in {version}. Skipping.")
            continue

        sha256 = digest.removeprefix("sha256:")
        platform_data[platform] = {
            "url": asset["browser_download_url"],
            "sha256": sha256,
            "size": asset["size"],
        }

    return version, platform_data


def generate_known_versions(
    repo: str,
    platform_to_asset: dict[str, str],
    min_version: str,
) -> dict:
    releases = get_all_releases(repo, min_version)
    logging.info(f"Found {len(releases)} releases >= {min_version}")

    known_versions = {}
    for release in releases:
        version, platform_data = process_release(release, platform_to_asset)
        if platform_data:
            known_versions[version] = platform_data

    sorted_versions = sorted(
        known_versions.keys(),
        key=lambda v: parse_version(v),
        reverse=True,
    )

    return {v: known_versions[v] for v in sorted_versions}


def main():
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s]: %(message)s")
    parser = argparse.ArgumentParser(
        description="Generate known_versions data for ExternalBinary classes."
    )
    parser.add_argument(
        "--project",
        required=True,
        choices=list(KNOWN_PROJECTS.keys()),
        help="Project to generate versions for",
    )
    parser.add_argument(
        "--min-version",
        required=True,
        help="Minimum version to include (e.g., 0.5.0)",
    )

    args = parser.parse_args()

    project = KNOWN_PROJECTS[args.project]
    known_versions = generate_known_versions(
        project["repo"],
        project["platforms"],
        args.min_version,
    )
    output_path = project["path"]
    with open(output_path, "w") as f:
        json.dump(known_versions, f, indent=2)
        f.write("\n")
    logging.info(f"Wrote {len(known_versions)} versions to {output_path}")


if __name__ == "__main__":
    main()
