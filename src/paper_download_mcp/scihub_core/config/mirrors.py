"""
Mirror configuration and management for Sci-Hub CLI.
"""

import os
from enum import Enum


def _parse_env_mirrors(value: str) -> list[str]:
    """Parse comma- or space-separated list of Sci-Hub mirror URLs from an env var.

    Each entry is normalised to start with ``https://``. Empty entries are skipped.
    """
    raw = [m.strip() for m in value.replace(",", " ").split()]
    out: list[str] = []
    for m in raw:
        if not m:
            continue
        if not m.startswith(("http://", "https://")):
            m = "https://" + m
        out.append(m.rstrip("/"))
    return out


# Read user-provided mirror override at import time. Both ``SCIHUB_MIRRORS`` (plural,
# preferred) and ``SCIHUB_MIRROR`` (singular, alias) are honoured so it composes well
# with how other tools — e.g. ``paper-find-mcp`` — name the same setting.
_ENV_MIRRORS = _parse_env_mirrors(
    os.getenv("SCIHUB_MIRRORS") or os.getenv("SCIHUB_MIRROR") or ""
)


class MirrorTier(Enum):
    """Mirror difficulty tiers."""

    EASY = "easy"
    HARD = "hard"


class MirrorConfig:
    """Configuration for Sci-Hub mirrors organized by difficulty."""

    # Mirror configuration by tier. EASY = modern (preferred); HARD = legacy
    # (fallback). Modern mirrors are reachable on most networks; legacy mirrors
    # are reachable on certain VPNs where the modern set is blocked. Canonical
    # meta-list: https://sci-hub.red/mirrors
    MIRROR_TIERS = {
        MirrorTier.EASY: [  # Modern (preferred)
            "https://sci-hub.red",
            "https://sci-hub.su",
            "https://sci-hub.st",
            "https://sci-hub.box",
            "https://sci-hub.ru",
        ],
        MirrorTier.HARD: [  # Legacy (fallback); may serve 403 / Cloudflare challenge
            "https://sci-hub.mk",
            "https://sci-hub.ren",
            "https://sci-hub.vg",
            "https://sci-hub.ee",
        ],
    }

    @classmethod
    def get_mirrors_by_tier(cls, tier: MirrorTier) -> list[str]:
        """Get mirrors for a specific tier."""
        # When the user has overridden the mirror list, treat all of them as EASY
        # (no built-in tier classification for arbitrary user-supplied hosts).
        if _ENV_MIRRORS:
            return list(_ENV_MIRRORS) if tier is MirrorTier.EASY else []
        return cls.MIRROR_TIERS.get(tier, [])

    @classmethod
    def get_all_mirrors(cls) -> list[str]:
        """Get all mirrors ordered by difficulty (easy first)."""
        if _ENV_MIRRORS:
            return list(_ENV_MIRRORS)
        return cls.MIRROR_TIERS[MirrorTier.EASY] + cls.MIRROR_TIERS[MirrorTier.HARD]

    @classmethod
    def get_easy_mirrors(cls) -> list[str]:
        """Get only easy mirrors."""
        if _ENV_MIRRORS:
            return list(_ENV_MIRRORS)
        return cls.MIRROR_TIERS[MirrorTier.EASY]

    @classmethod
    def get_hard_mirrors(cls) -> list[str]:
        """Get only hard mirrors."""
        if _ENV_MIRRORS:
            return []
        return cls.MIRROR_TIERS[MirrorTier.HARD]

    @classmethod
    def is_hard_mirror(cls, mirror_url: str) -> bool:
        """Check if a mirror is in the hard tier."""
        if _ENV_MIRRORS:
            return False
        return mirror_url in cls.MIRROR_TIERS[MirrorTier.HARD]


# Default mirror configuration
DEFAULT_MIRRORS = MirrorConfig.get_all_mirrors()
