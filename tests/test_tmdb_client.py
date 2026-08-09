import unittest
from threading import Thread, local
from unittest.mock import Mock, call, patch

import requests

from app.tmdb import client as client_module
from app.tmdb.client import TmdbClient, get_default_client


class TmdbClientTests(unittest.TestCase):
    def test_resolves_and_reuses_token_only_when_first_request_is_made(self):
        response = Mock()
        response.json.return_value = {"id": 42}
        session = Mock()
        session.get.return_value = response

        with patch.object(
            client_module,
            "require_env",
            return_value="lazy-token",
        ) as require_env_mock:
            client = TmdbClient(session=session)
            require_env_mock.assert_not_called()

            first = client.get_json("/movie/42")
            second = client.get_json("movie/42", params={"page": 2})

        self.assertEqual(first, {"id": 42})
        self.assertEqual(second, {"id": 42})
        require_env_mock.assert_called_once_with("TMDB_READ_ACCESS_TOKEN")
        self.assertEqual(response.raise_for_status.call_count, 2)
        self.assertEqual(response.json.call_count, 2)
        self.assertEqual(
            session.get.call_args_list,
            [
                call(
                    "https://api.themoviedb.org/3/movie/42",
                    headers={
                        "accept": "application/json",
                        "Authorization": "Bearer lazy-token",
                    },
                    params={"language": "en-US"},
                    timeout=15,
                ),
                call(
                    "https://api.themoviedb.org/3/movie/42",
                    headers={
                        "accept": "application/json",
                        "Authorization": "Bearer lazy-token",
                    },
                    params={"page": 2},
                    timeout=15,
                ),
            ],
        )

    def test_explicit_configuration_and_session_are_used(self):
        response = Mock()
        response.json.return_value = {"results": []}
        session = Mock()
        session.get.return_value = response

        with patch.object(client_module, "require_env") as require_env_mock:
            client = TmdbClient(
                token="provided-token",
                language="pt-BR",
                session=session,
                base_url="https://example.test/api/",
                timeout=3,
            )
            result = client.get_json("search/movie")

        self.assertEqual(result, {"results": []})
        require_env_mock.assert_not_called()
        session.get.assert_called_once_with(
            "https://example.test/api/search/movie",
            headers={
                "accept": "application/json",
                "Authorization": "Bearer provided-token",
            },
            params={"language": "pt-BR"},
            timeout=3,
        )

    def test_http_errors_are_not_hidden(self):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("failed")
        session = Mock()
        session.get.return_value = response
        client = TmdbClient(token="token", session=session)

        with self.assertRaisesRegex(requests.HTTPError, "failed"):
            client.get_json("movie/42")

        response.json.assert_not_called()

    def test_default_client_creation_does_not_resolve_token(self):
        with patch.object(
            client_module,
            "_default_client_state",
            local(),
        ), patch.object(
            client_module,
            "require_env",
        ) as require_env_mock:
            first = get_default_client()
            second = get_default_client()

        self.assertIs(first, second)
        require_env_mock.assert_not_called()

    def test_default_client_session_is_isolated_per_thread(self):
        worker_clients = []

        def collect_worker_clients():
            worker_clients.extend([
                get_default_client(),
                get_default_client(),
            ])

        with patch.object(
            client_module,
            "_default_client_state",
            local(),
        ):
            main_client = get_default_client()
            worker = Thread(target=collect_worker_clients)
            worker.start()
            worker.join()

        self.assertIs(worker_clients[0], worker_clients[1])
        self.assertIsNot(main_client, worker_clients[0])


if __name__ == "__main__":
    unittest.main()
