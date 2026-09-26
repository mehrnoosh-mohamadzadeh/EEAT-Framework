"""
تست‌های واحد utils/wayback.py — با mock کردن requests.get، چون این
تست‌ها نباید به شبکه‌ی واقعی (archive.org) وابسته باشند.
"""

import datetime
from unittest.mock import patch, Mock

from utils.wayback import get_capture_history, estimate_last_content_change


def _mock_response(json_data, status_ok=True):
    mock_resp = Mock()
    mock_resp.json.return_value = json_data
    if status_ok:
        mock_resp.raise_for_status = Mock()
    else:
        mock_resp.raise_for_status = Mock(side_effect=Exception("HTTP error"))
    return mock_resp


class TestGetCaptureHistory:

    def test_parses_valid_cdx_response(self):
        cdx_json = [
            ["timestamp", "digest", "statuscode"],
            ["20230101000000", "AAA", "200"],
            ["20240101000000", "BBB", "200"],
        ]
        with patch("utils.wayback.requests.get", return_value=_mock_response(cdx_json)):
            history = get_capture_history("https://example.com")
        assert history == [
            {"timestamp": "20230101000000", "digest": "AAA"},
            {"timestamp": "20240101000000", "digest": "BBB"},
        ]

    def test_returns_empty_list_on_network_error(self):
        with patch("utils.wayback.requests.get", side_effect=Exception("boom")):
            history = get_capture_history("https://example.com")
        assert history == []

    def test_returns_empty_list_when_no_captures(self):
        with patch("utils.wayback.requests.get", return_value=_mock_response([["timestamp", "digest", "statuscode"]])):
            history = get_capture_history("https://example.com")
        assert history == []


class TestEstimateLastContentChange:

    def test_finds_earliest_timestamp_of_current_content(self):
        """
        سه کراول: دو تای اول محتوای قدیمی (digest=A)، دو تای بعدی محتوای
        فعلی (digest=B). باید تاریخ اولین باری که digest=B ظاهر شده را
        برگرداند (یعنی تخمین «آخرین تغییر واقعی»)، نه آخرین کراول مطلق.
        """
        cdx_json = [
            ["timestamp", "digest", "statuscode"],
            ["20200101000000", "A", "200"],
            ["20210101000000", "A", "200"],
            ["20220601000000", "B", "200"],
            ["20230101000000", "B", "200"],
            ["20240101000000", "B", "200"],
        ]
        with patch("utils.wayback.requests.get", return_value=_mock_response(cdx_json)):
            result = estimate_last_content_change("https://example.com")
        assert result == datetime.date(2022, 6, 1)

    def test_returns_first_capture_when_content_never_changed(self):
        """اگر digest هیچ‌وقت عوض نشده، یعنی محتوا از همان اول ثابت بوده؛ تاریخ اولین کراول برگردانده می‌شود."""
        cdx_json = [
            ["timestamp", "digest", "statuscode"],
            ["20200101000000", "SAME", "200"],
            ["20240101000000", "SAME", "200"],
        ]
        with patch("utils.wayback.requests.get", return_value=_mock_response(cdx_json)):
            result = estimate_last_content_change("https://example.com")
        assert result == datetime.date(2020, 1, 1)

    def test_returns_none_when_no_history(self):
        with patch("utils.wayback.requests.get", side_effect=Exception("no network")):
            result = estimate_last_content_change("https://example.com")
        assert result is None
