from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.services.url_guard import is_snapchat_spotlight_url, is_story_url


STORY_MESSAGE = "Story downloads are not supported."
PRIVATE_MESSAGE = "This content is private or requires login and cannot be downloaded."
SNAPCHAT_AUTH_MESSAGE = "This Snapchat content requires authorization and cannot be downloaded."
SNAPCHAT_UNSUPPORTED_MESSAGE = (
    "This public Snapchat Spotlight URL is currently unsupported by the media extractor."
)

PRIVATE_AVAILABILITY = {
    "authentication_required",
    "cookie_required",
    "followers_only",
    "friends_only",
    "login_required",
    "members_only",
    "private",
    "needs_auth",
    "subscriber_only",
    "premium_only",
    "paid",
}

PRIVATE_ERROR_MARKERS = (
    "private",
    "login required",
    "sign in",
    "log in",
    "cookies",
    "followers only",
    "followers-only",
    "friends only",
    "friends-only",
    "permission denied",
    "not authorized",
    "authentication required",
    "requires authentication",
    "requires login",
    "cookie required",
)

STORY_ERROR_MARKERS = (
    "ephemeral content",
    "instagram story",
    "facebook story",
    "this story",
)

STORY_METADATA_FIELDS = (
    "content_kind",
    "content_type",
    "media_type",
    "type",
)

SNAPCHAT_AUTH_ERROR_MARKERS = (
    "authentication required",
    "authorization required",
    "cookie required",
    "friends only",
    "friends-only",
    "login required",
    "log in to",
    "not authorized",
    "requires authentication",
    "requires authorization",
    "requires login",
    "sign in to",
    "this content is private",
)

PRIVATE_METADATA_FLAGS = (
    "authentication_required",
    "cookie_required",
    "is_private",
    "login_required",
    "needs_auth",
    "requires_authentication",
    "requires_cookies",
    "requires_login",
)


def _is_story_metadata(info: dict[str, Any], source_url: str | None = None) -> bool:
    if any(info.get(key) is True for key in ("is_ephemeral", "is_status", "is_story")):
        return True

    if info.get("story_id") not in (None, ""):
        return True

    extractor = str(info.get("extractor_key") or info.get("extractor") or "").lower()
    if extractor.endswith(("story", "stories")):
        return True

    if any(
        is_story_url(str(info.get(key) or ""))
        for key in ("original_url", "webpage_url")
    ):
        return True

    # Some public Spotlight extractors use "story" as a generic media taxonomy.
    # The explicit Spotlight URL and checks above are more authoritative.
    if source_url and is_snapchat_spotlight_url(source_url):
        return False

    for key in STORY_METADATA_FIELDS:
        value = str(info.get(key) or "").lower().replace("-", "_").replace(" ", "_")
        if set(value.split("_")) & {"ephemeral", "status", "stories", "story"}:
            return True

    return False


def reject_story_metadata(info: dict[str, Any], source_url: str | None = None) -> None:
    candidates = [info]
    candidates.extend(
        entry
        for entry in info.get("entries") or []
        if isinstance(entry, dict)
    )
    if any(_is_story_metadata(candidate, source_url) for candidate in candidates):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=STORY_MESSAGE,
        )


def reject_private_metadata(info: dict[str, Any]) -> None:
    availability = str(info.get("availability") or "").lower()
    if availability in PRIVATE_AVAILABILITY or any(
        info.get(key) is True for key in PRIVATE_METADATA_FLAGS
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PRIVATE_MESSAGE,
        )


def is_snapchat_authentication_error(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return any(marker in lowered for marker in SNAPCHAT_AUTH_ERROR_MARKERS)


def translate_extractor_error(exc: Exception, url: str | None = None) -> HTTPException:
    message = str(exc)
    lowered = message.lower()

    if url and is_snapchat_spotlight_url(url):
        if is_snapchat_authentication_error(exc):
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=SNAPCHAT_AUTH_MESSAGE,
            )
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=SNAPCHAT_UNSUPPORTED_MESSAGE,
        )

    if any(marker in lowered for marker in STORY_ERROR_MARKERS):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=STORY_MESSAGE,
        )

    if any(marker in lowered for marker in PRIVATE_ERROR_MARKERS):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PRIVATE_MESSAGE,
        )

    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="This public URL is unsupported or temporarily unavailable.",
    )
