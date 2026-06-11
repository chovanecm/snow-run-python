import http.cookiejar
import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import Mock, patch

keyring_stub = types.SimpleNamespace(
    get_password=lambda *a, **kw: None,
    set_password=lambda *a, **kw: None,
    delete_password=lambda *a, **kw: None,
)
sys.modules.setdefault("keyring", keyring_stub)

from snow_cli.client import ScriptTokenError, ServiceNowClient
from snow_cli.config import Config


def _make_config(tmp_dir, instance="dev.example.com", user="admin", password="pass"):
    return Config(
        instance=instance,
        user=user,
        password=password,
        cookie_file=Path(tmp_dir) / "cookies.txt",
        tmp_dir=Path(tmp_dir),
    )


class RestSessionTests(unittest.TestCase):
    def test_rest_session_has_basic_auth_pre_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
        self.assertEqual(client._rest.auth, ("admin", "pass"))

    def test_rest_session_has_accept_json_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
        self.assertEqual(client._rest.headers.get("Accept"), "application/json")

    def test_scraping_session_is_none_before_first_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
        self.assertIsNone(client._scraping)

    def test_rest_get_calls_rest_session_with_correct_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
            mock_resp = Mock()
            with patch.object(client._rest, "get", return_value=mock_resp) as mock_get:
                result = client.rest_get("/api/now/table/incident", params={"sysparm_limit": "10"})
        mock_get.assert_called_once_with(
            "https://dev.example.com/api/now/table/incident",
            params={"sysparm_limit": "10"},
            headers={},
        )
        self.assertIs(result, mock_resp)


class ScrapingSessionTests(unittest.TestCase):
    def test_scraping_session_created_on_first_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
            with patch.object(client, "_save_cookies"):
                with patch.object(client, "_get_scraping_session") as mock_init:
                    mock_session = Mock()
                    mock_session.get.return_value = Mock()
                    mock_init.return_value = mock_session
                    client.scraping_get("/login.do")
            mock_init.assert_called_once()

    def test_corrupted_cookie_file_prints_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            cookie_file = Path(tmp) / "cookies.txt"
            cookie_file.write_text("not a valid cookie jar file")
            config = Config(
                instance="dev.example.com",
                user="admin",
                password="pass",
                cookie_file=cookie_file,
            )
            client = ServiceNowClient(config)
            buf = io.StringIO()
            with redirect_stderr(buf):
                client._get_scraping_session()
        self.assertIn("Warning", buf.getvalue())

    def test_missing_cookie_file_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Config(
                instance="dev.example.com",
                user="admin",
                password="pass",
                cookie_file=Path(tmp) / "nonexistent.txt",
            )
            client = ServiceNowClient(config)
            client._get_scraping_session()  # must not raise

    def test_none_cookie_file_does_not_raise(self):
        config = Config(instance="dev.example.com", user="admin", password="pass")
        client = ServiceNowClient(config)
        client._get_scraping_session()  # must not raise


class TokenExtractionTests(unittest.TestCase):
    def test_extract_token_returns_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
        token = client._extract_token('value="abc123def"', r'value="([a-zA-Z0-9]+)"')
        self.assertEqual(token, "abc123def")

    def test_extract_token_returns_none_when_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
        self.assertIsNone(client._extract_token("no match here", r'value="([a-zA-Z0-9]+)"'))

    def test_get_script_token_raises_script_token_error_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
            mock_response = Mock()
            mock_response.text = "<html>no token here</html>"
            with patch.object(client, "scraping_get", return_value=mock_response):
                with self.assertRaises(ScriptTokenError):
                    client.get_script_token()

    def test_get_login_token_raises_value_error_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
            mock_response = Mock()
            mock_response.text = "<html>no token here</html>"
            with patch.object(client, "scraping_get", return_value=mock_response):
                with self.assertRaises(ValueError):
                    client.get_login_token()

    def test_get_elevate_token_raises_value_error_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ServiceNowClient(_make_config(tmp))
            mock_response = Mock()
            mock_response.text = "<html>no token here</html>"
            with patch.object(client, "scraping_get", return_value=mock_response):
                with self.assertRaises(ValueError):
                    client.get_elevate_token()


if __name__ == "__main__":
    unittest.main()
