import unittest

from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.server.game_server import app, resolve_server_config_path


class ServerSecurityTests(unittest.TestCase):
    def test_websocket_rejects_untrusted_origin(self):
        client = TestClient(app)

        with self.assertRaises(WebSocketDisconnect) as ctx:
            with client.websocket_connect(
                "/ws",
                headers={"origin": "https://evil.example"},
            ):
                pass

        self.assertEqual(ctx.exception.code, 1008)

    def test_websocket_accepts_local_frontend_origin(self):
        client = TestClient(app)

        with client.websocket_connect(
            "/ws",
            headers={"origin": "http://localhost:5173"},
        ):
            pass

    def test_websocket_config_path_is_limited_to_config_dir(self):
        resolved = resolve_server_config_path("config/test_config.yaml")
        self.assertEqual(resolved.name, "test_config.yaml")
        self.assertEqual(resolved.parent.name, "config")

        with self.assertRaises(ValueError):
            resolve_server_config_path("../.env")

        with self.assertRaises(ValueError):
            resolve_server_config_path("/tmp/game_config.yaml")

        with self.assertRaises(ValueError):
            resolve_server_config_path("game_config.json")


if __name__ == "__main__":
    unittest.main()
