"""Bounded, opt-out GitHub release checks; source checkouts are never replaced."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from version import APP_VERSION, RELEASES_URL, REPOSITORY

API_ROOT = f"https://api.github.com/repos/{REPOSITORY}/releases"
MAX_RESPONSE = 256 * 1024
CHECK_INTERVAL = timedelta(days=1)
_SEMVER = re.compile(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
                     r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
                     r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z")


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text):
        match = _SEMVER.fullmatch(text) if isinstance(text, str) else None
        if not match:
            raise ValueError("Release tag is not a valid SemVer version")
        parts = tuple(match[4].split(".")) if match[4] else ()
        if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in parts):
            raise ValueError("Numeric prerelease identifiers cannot have leading zeroes")
        return cls(int(match[1]), int(match[2]), int(match[3]), parts)

    def __lt__(self, other):
        if not isinstance(other, Version): return NotImplemented
        core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if core != other_core: return core < other_core
        if not self.prerelease: return False
        if not other.prerelease: return True
        for left, right in zip(self.prerelease, other.prerelease):
            if left == right: continue
            a, b = left.isdigit(), right.isdigit()
            if a != b: return a
            return int(left) < int(right) if a else left < right
        return len(self.prerelease) < len(other.prerelease)


@dataclass(frozen=True)
class Release:
    version: Version
    tag: str
    url: str
    notes: str
    prerelease: bool


def parse_release(data):
    if not isinstance(data, dict) or data.get("draft") is not False or type(data.get("prerelease")) is not bool:
        raise ValueError("Release metadata is incomplete or draft")
    tag = data.get("tag_name")
    version = Version.parse(tag)
    url = data.get("html_url")
    parsed = urlparse(url) if isinstance(url, str) else None
    if (parsed is None or parsed.scheme != "https" or parsed.netloc != "github.com" or
            parsed.path != f"/{REPOSITORY}/releases/tag/{tag}" or parsed.query or parsed.fragment):
        raise ValueError("Release URL does not match the official repository")
    if bool(version.prerelease) != data["prerelease"]:
        raise ValueError("Prerelease flag disagrees with the version tag")
    body = data.get("body") or ""
    if not isinstance(body, str): raise ValueError("Release notes must be text")
    return Release(version, tag, url, body[:4000], data["prerelease"])


def fetch_release(*, include_prerelease=False, opener=urlopen):
    endpoint = API_ROOT + ("?per_page=30" if include_prerelease else "/latest")
    request = Request(endpoint, headers={"Accept": "application/vnd.github+json",
                                         "User-Agent": f"LogicSpace/{APP_VERSION}"})
    try:
        with opener(request, timeout=3) as response:
            payload = response.read(MAX_RESPONSE + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise ValueError(f"Cannot check GitHub Releases: {error}") from error
    if len(payload) > MAX_RESPONSE:
        raise ValueError("GitHub Releases response is too large")
    try: data = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError("GitHub Releases returned invalid JSON") from error
    if include_prerelease:
        if not isinstance(data, list): raise ValueError("GitHub Releases list is invalid")
        releases = []
        for item in data:
            try: releases.append(parse_release(item))
            except ValueError: continue
        if not releases: raise ValueError("No valid published GitHub release is available")
        return max(releases, key=lambda item: item.version)
    return parse_release(data)


class UpdateSettings:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path.home() / ".local/share/logicspace/updater.json"

    def load(self):
        defaults = {"version": 1, "auto_check": True, "include_prerelease": False,
                    "last_checked": None}
        if not self.path.exists(): return defaults
        try: data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError(f"Update settings are damaged: {error}") from error
        if (not isinstance(data, dict) or data.get("version") != 1 or
                type(data.get("auto_check")) is not bool or
                type(data.get("include_prerelease")) is not bool or
                data.get("last_checked") is not None and not isinstance(data["last_checked"], str)):
            raise ValueError("Invalid update settings")
        return {key: data[key] for key in defaults}

    def save(self, data):
        if (not isinstance(data, dict) or data.get("version") != 1 or
                type(data.get("auto_check")) is not bool or
                type(data.get("include_prerelease")) is not bool or
                data.get("last_checked") is not None and not isinstance(data["last_checked"], str)):
            raise ValueError("Invalid update settings")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".updater-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(data, stream)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name): os.unlink(name)

    def due(self, now=None):
        settings = self.load()
        if not settings["auto_check"]: return False
        if settings["last_checked"] is None: return True
        now = now or datetime.now(timezone.utc)
        try: previous = datetime.fromisoformat(settings["last_checked"])
        except ValueError: return True
        if previous.tzinfo is None: return True
        if previous > now: return True
        return now - previous >= CHECK_INTERVAL

    def checked(self, now=None):
        settings = self.load()
        settings["last_checked"] = (now or datetime.now(timezone.utc)).isoformat()
        self.save(settings)


def find_update(*, include_prerelease=False, current=APP_VERSION, fetch=fetch_release):
    release = fetch(include_prerelease=include_prerelease)
    if release.prerelease and not include_prerelease: return None
    return release if Version.parse(current) < release.version else None


def update_destination(release):
    """Source-checkout policy: only the official release page, never code execution."""
    if not isinstance(release, Release): raise ValueError("Invalid release")
    checked = parse_release({"draft": False, "prerelease": release.prerelease,
                             "tag_name": release.tag, "html_url": release.url,
                             "body": release.notes})
    if checked.version != release.version:
        raise ValueError("Release version does not match its tag")
    return release.url


AUTO_INSTALL_SUPPORTED = False
