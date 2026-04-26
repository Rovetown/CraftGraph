"""Update checker for CraftGraph.

Stub implementation: the UI and settings persistence are fully wired,
but the actual network check against GitHub Releases is not yet
implemented. ``check_for_update()`` always returns ``None``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UpdateResult:
    """Describes an available update."""

    version: str
    url: str


def check_for_update(current_version: str) -> UpdateResult | None:
    """Check whether a newer CraftGraph version is available.

    Returns an :class:`UpdateResult` when an update exists, or ``None``
    when the current version is up-to-date (or the check cannot be
    performed).

    .. note::

        This is a **stub**. The actual implementation will query the
        GitHub Releases API. For now it always returns ``None``.
    """
    # TODO(post-release): implement GitHub Releases API check
    # 1. GET https://api.github.com/repos/<owner>/<repo>/releases/latest
    # 2. Compare response tag_name against current_version
    # 3. Return UpdateResult(version=tag_name, url=html_url) if newer
    logger.debug("update check stub called (v%s) -- always returns None", current_version)
    return None
