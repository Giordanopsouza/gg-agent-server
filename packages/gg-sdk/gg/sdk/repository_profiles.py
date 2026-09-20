"""Operator-configured repository bootstrap and check commands.

Profiles are loaded at process startup from a JSON file. Task submission never
accepts arbitrary commands or secrets; only repository names that have a profile
may run when profiles are configured.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_MAX_COMMAND_OUTPUT_BYTES = 1_048_576


class RepositoryProfile(BaseModel):
    """Bounded setup and verification commands for one allowlisted repository."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repository: str
    bootstrap_command: str = Field(min_length=1, max_length=512)
    check_command: str = Field(min_length=1, max_length=512)
    default_base_ref: str = Field(default="main", min_length=1, max_length=200)
    max_bootstrap_output_bytes: int = Field(
        default=DEFAULT_MAX_COMMAND_OUTPUT_BYTES, ge=1024, le=10_485_760
    )
    max_check_output_bytes: int = Field(
        default=DEFAULT_MAX_COMMAND_OUTPUT_BYTES, ge=1024, le=10_485_760
    )


def load_repository_profiles(path: str | Path) -> tuple[RepositoryProfile, ...]:
    """Load and validate profiles from a JSON array file."""

    raw = Path(path).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("repository profiles file must contain a JSON array")
    profiles: list[RepositoryProfile] = []
    seen: set[str] = set()
    for item in payload:
        profile = RepositoryProfile.model_validate(item)
        if profile.repository in seen:
            raise ValueError(
                f"duplicate repository profile for {profile.repository!r}"
            )
        seen.add(profile.repository)
        profiles.append(profile)
    return tuple(profiles)


def profiles_by_repository(
    profiles: tuple[RepositoryProfile, ...],
) -> dict[str, RepositoryProfile]:
    return {profile.repository: profile for profile in profiles}


__all__ = [
    "DEFAULT_MAX_COMMAND_OUTPUT_BYTES",
    "RepositoryProfile",
    "load_repository_profiles",
    "profiles_by_repository",
]
