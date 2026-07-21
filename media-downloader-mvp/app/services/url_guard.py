from __future__ import annotations

import ipaddress
import socket
from urllib.parse import unquote, urlparse

from fastapi import HTTPException, status


BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
}

STORY_HOSTS = {
    "facebook.com",
    "fb.com",
    "instagram.com",
    "snapchat.com",
    "tiktok.com",
    "youtube.com",
}


def is_story_url(raw_url: str) -> bool:
    parsed = urlparse(raw_url.strip())
    host = (parsed.hostname or "").lower().strip(".")
    if not any(host == domain or host.endswith(f".{domain}") for domain in STORY_HOSTS):
        return False

    path_segments = {
        segment
        for segment in unquote(parsed.path).lower().split("/")
        if segment
    }
    return bool(path_segments & {"story", "stories"})


def is_snapchat_spotlight_url(raw_url: str) -> bool:
    parsed = urlparse(raw_url.strip())
    host = (parsed.hostname or "").lower().strip(".")
    if not (host == "snapchat.com" or host.endswith(".snapchat.com")):
        return False

    path_segments = [
        segment
        for segment in unquote(parsed.path).lower().split("/")
        if segment
    ]
    return bool(path_segments) and (path_segments[0] == "t" or "spotlight" in path_segments)


def validate_public_url(raw_url: str) -> str:
    url = raw_url.strip()
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only http and https URLs are supported.",
        )

    host = (parsed.hostname or "").lower().strip(".")
    if not host or host in BLOCKED_HOSTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or blocked hostname.",
        )

    if is_story_url(url):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Story downloads are not supported.",
        )

    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The hostname could not be resolved.",
        ) from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Local or private-network URLs are blocked.",
            )

    return url
