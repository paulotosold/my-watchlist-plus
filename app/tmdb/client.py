"""Small HTTP client for TMDB API requests."""

from threading import local

import requests

from app.config import TMDB_LANGUAGE, require_env


TMDB_API_BASE_URL = "https://api.themoviedb.org/3"
TMDB_REQUEST_TIMEOUT = 15


class TmdbClient:
    """Fetch JSON from TMDB with lazily resolved authentication."""

    def __init__(
        self,
        *,
        token=None,
        language=TMDB_LANGUAGE,
        session=None,
        base_url=TMDB_API_BASE_URL,
        timeout=TMDB_REQUEST_TIMEOUT,
    ):
        self._token = token or None
        self.language = language
        self.session = session if session is not None else requests.Session()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_json(self, endpoint, params=None):
        """Return a decoded TMDB response, raising for HTTP failures."""
        response = self.session.get(
            f"{self.base_url}/{endpoint.lstrip('/')}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self._get_token()}",
            },
            params=params or {"language": self.language},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _get_token(self):
        if self._token is None:
            self._token = require_env("TMDB_READ_ACCESS_TOKEN")

        return self._token


_default_client_state = local()


def get_default_client():
    """Return a thread-local client without resolving credentials yet."""
    client = getattr(_default_client_state, "client", None)

    if client is None:
        client = TmdbClient()
        _default_client_state.client = client

    return client
