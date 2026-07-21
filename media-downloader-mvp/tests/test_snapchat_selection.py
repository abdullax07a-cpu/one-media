from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.config import Settings
from app.services.media_service import MediaService, _select_snapchat_format


class FakeYoutubeDL:
    def __init__(self, _: dict, info: dict) -> None:
        self.info = info

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def extract_info(self, _: str, download: bool) -> dict:
        return self.info


class SnapchatSelectionTests(unittest.TestCase):
    def test_selects_one_clean_video_candidate(self) -> None:
        info = {"formats": [{
            "format_id": "clean",
            "url": "https://bolt-gcdn.sc-cdn.net/z/video.mp4",
            "ext": "mp4",
            "vcodec": "h264",
            "acodec": "aac",
            "height": 1080,
        }]}
        self.assertEqual(_select_snapchat_format(info), "clean")

    def test_ranks_multiple_candidates_by_source_then_quality(self) -> None:
        info = {"formats": [
            {
                "format_id": "external-high",
                "url": "https://media.example/video.mp4",
                "ext": "mp4",
                "vcodec": "h264",
                "height": 2160,
            },
            {
                "format_id": "cdn-low",
                "url": "https://cf-st.sc-cdn.net/d/video.mp4",
                "ext": "mp4",
                "vcodec": "h264",
                "height": 720,
            },
            {
                "format_id": "cdn-high",
                "url": "https://bolt-gcdn.sc-cdn.net/z/video.mp4",
                "ext": "mp4",
                "vcodec": "h264",
                "height": 1080,
            },
        ]}
        self.assertEqual(_select_snapchat_format(info), "cdn-high")

    def test_accepts_direct_mp4_with_partial_metadata(self) -> None:
        info = {
            "url": "https://bolt-gcdn.sc-cdn.net/z/video.mp4",
            "ext": "mp4",
            "width": 540,
            "height": 960,
        }
        self.assertEqual(_select_snapchat_format(info), "0")

    def test_keeps_valid_working_video_as_uncertain_fallback(self) -> None:
        info = {"formats": [{
            "format_id": "0",
            "url": "https://bolt-gcdn.sc-cdn.net/z/video.27.IRZXSOY?mo=unknown",
            "ext": "mp4",
            "width": 540,
            "height": 960,
        }]}
        self.assertEqual(_select_snapchat_format(info), "0")

    def test_never_selects_image_or_audio_candidate(self) -> None:
        info = {"formats": [
            {
                "format_id": "poster",
                "url": "https://bolt-gcdn.sc-cdn.net/z/poster.jpg",
                "ext": "jpg",
                "width": 1080,
                "height": 1920,
            },
            {
                "format_id": "audio",
                "url": "https://bolt-gcdn.sc-cdn.net/z/audio.m4a",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "aac",
            },
            {
                "format_id": "video",
                "url": "https://bolt-gcdn.sc-cdn.net/z/video.mp4",
                "ext": "mp4",
                "vcodec": "h264",
            },
        ]}
        self.assertEqual(_select_snapchat_format(info), "video")

    def test_inspection_offers_direct_snapchat_mp4_without_vcodec_metadata(self) -> None:
        info = {
            "id": "spotlight-id",
            "extractor_key": "SnapchatSpotlight",
            "url": "https://bolt-gcdn.sc-cdn.net/z/video.27.IRZXSOY",
            "ext": "mp4",
            "width": 540,
            "height": 960,
            "duration": 10,
        }
        service = MediaService(Settings())
        with patch(
            "app.services.media_service.yt_dlp.YoutubeDL",
            side_effect=lambda options: FakeYoutubeDL(options, info),
        ):
            result = service._inspect_sync("https://www.snapchat.com/spotlight/spotlight-id")

        self.assertEqual(result["media_kind"], "video")
        self.assertEqual(len(result["formats"]), 1)
        self.assertEqual(result["formats"][0].extension, "mp4")
        self.assertTrue(result["formats"][0].has_video)


if __name__ == "__main__":
    unittest.main()
