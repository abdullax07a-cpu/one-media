from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.services.media_service import _select_clean_snapchat_format


class SnapchatSelectionTests(unittest.TestCase):
    def test_rejects_spotlight_sharing_variant(self) -> None:
        info = {
            "formats": [{
                "format_id": "0",
                "url": "https://bolt-gcdn.sc-cdn.net/z/media.27.IRZXSOY?mo=SpotlightSharing",
                "width": 540,
                "height": 960,
                "vcodec": "h264",
            }]
        }

        with self.assertRaises(HTTPException) as context:
            _select_clean_snapchat_format(info)

        self.assertEqual(context.exception.status_code, 422)
        self.assertIn("clean original", context.exception.detail)

    def test_selects_highest_quality_clean_cdn_format(self) -> None:
        info = {
            "formats": [
                {
                    "format_id": "clean-low",
                    "url": "https://cf-st.sc-cdn.net/d/media.1.IRZXSOY",
                    "width": 540,
                    "height": 960,
                    "tbr": 800,
                    "vcodec": "h264",
                },
                {
                    "format_id": "share-high",
                    "url": "https://bolt-gcdn.sc-cdn.net/z/media.27.IRZXSOY",
                    "width": 1080,
                    "height": 1920,
                    "tbr": 4000,
                    "vcodec": "h264",
                },
                {
                    "format_id": "clean-high",
                    "url": "https://bolt-gcdn.sc-cdn.net/z/media.1.IRZXSOY",
                    "width": 1080,
                    "height": 1920,
                    "tbr": 3000,
                    "vcodec": "h264",
                },
            ]
        }

        self.assertEqual(_select_clean_snapchat_format(info), "clean-high")


if __name__ == "__main__":
    unittest.main()
