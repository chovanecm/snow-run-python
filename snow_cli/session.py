"""ServiceNow session management with cookie persistence"""
import re
import http.cookiejar
from pathlib import Path
from typing import Optional
import requests
from requests.cookies import RequestsCookieJar


class SnowSession:
    """Manages HTTP session with ServiceNow including cookie persistence"""

    def __init__(self, instance: str, cookie_file: Path):
        self.instance = instance
        self.base_url = f"https://{instance}"
        self.cookie_file = cookie_file
        self.session = requests.Session()
        self._load_cookies()

    def _load_cookies(self):
        """Load cookies from file if it exists"""
        if self.cookie_file.exists():
            try:
                cookie_jar = http.cookiejar.MozillaCookieJar(str(self.cookie_file))
                cookie_jar.load(ignore_discard=True, ignore_expires=True)

                # Convert to RequestsCookieJar
                for cookie in cookie_jar:
                    self.session.cookies.set_cookie(cookie)
            except Exception as e:
                # If cookie file is corrupted, ignore and start fresh
                pass

    def _save_cookies(self):
        """Save cookies to file"""
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert requests cookies to MozillaCookieJar format
        cookie_jar = http.cookiejar.MozillaCookieJar(str(self.cookie_file))
        for cookie in self.session.cookies:
            cookie_jar.set_cookie(cookie)

        cookie_jar.save(ignore_discard=True, ignore_expires=True)
        self.cookie_file.chmod(0o600)

    def get(self, path: str, **kwargs) -> requests.Response:
        """Perform GET request and save cookies"""
        response = self.session.get(f"{self.base_url}{path}", **kwargs)
        self._save_cookies()
        return response

    def post(self, path: str, **kwargs) -> requests.Response:
        """Perform POST request and save cookies"""
        response = self.session.post(f"{self.base_url}{path}", **kwargs)
        self._save_cookies()
        return response

    def extract_token(self, html: str, pattern: str) -> Optional[str]:
        """Extract security token from HTML response"""
        match = re.search(pattern, html)
        return match.group(1) if match else None

    def get_login_token(self) -> str:
        """Get login token (sysparm_ck) from ServiceNow"""
        response = self.get("/login.do")
        token = self.extract_token(
            response.text,
            r'sysparm_ck[^>]*value="([a-zA-Z0-9_]+)"'
        )
        if not token:
            raise ValueError(
                f"Could not obtain login token from {self.instance}"
            )
        return token

    def get_script_token(self) -> str:
        """Get script execution token (sysparm_ck) from sys.scripts.do"""
        response = self.get("/sys.scripts.do")
        token = self.extract_token(
            response.text,
            r'sysparm_ck[^>]*value="([a-zA-Z0-9_]+)"'
        )
        if not token:
            raise ValueError(
                f"Cannot get security token for {self.instance}. "
                "Try logging in again (snow login)"
            )
        return token

    def get_elevate_token(self) -> str:
        """Get role elevation token (g_ck) from navpage.do"""
        response = self.get("/navpage.do")
        token = self.extract_token(
            response.text,
            r"g_ck = '([a-zA-Z0-9_]+)'"
        )
        if not token:
            raise ValueError(
                "Could not obtain authentication token to elevate privileges"
            )
        return token
