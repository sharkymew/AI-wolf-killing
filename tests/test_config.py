import os
import tempfile
import unittest
import yaml

from src.utils.config import load_config, get_active_models, count_players


class ConfigTests(unittest.TestCase):
    def _write_config(self, data):
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True)
        return path

    def test_missing_api_key_raises_for_non_mock(self):
        data = {
            "models": [
                {
                    "name": "M1",
                    "provider": "openai",
                    "model": "gpt-4o-mini"
                }
            ],
            "game": {
                "roles": {
                    "werewolf": 1,
                    "witch": 0,
                    "seer": 0,
                    "hunter": 0,
                    "villager": 0
                }
            }
        }
        path = self._write_config(data)
        with self.assertRaises(ValueError):
            load_config(path)

    def test_missing_api_key_allowed_for_mock(self):
        data = {
            "models": [
                {
                    "name": "Mock1",
                    "provider": "mock",
                    "model": "mock-model"
                }
            ],
            "game": {
                "roles": {
                    "werewolf": 1,
                    "witch": 0,
                    "seer": 0,
                    "hunter": 0,
                    "villager": 0
                }
            }
        }
        path = self._write_config(data)
        config = load_config(path)
        self.assertEqual(len(get_active_models(config.models)), 1)
        self.assertEqual(count_players(config.game.roles), 1)

    def test_auto_disable_extra_models(self):
        data = {
            "models": [
                {
                    "name": "Mock1",
                    "provider": "mock",
                    "model": "mock-model"
                },
                {
                    "name": "Mock2",
                    "provider": "mock",
                    "model": "mock-model"
                },
                {
                    "name": "Mock3",
                    "provider": "mock",
                    "model": "mock-model"
                }
            ],
            "game": {
                "roles": {
                    "werewolf": 1,
                    "witch": 0,
                    "seer": 0,
                    "hunter": 0,
                    "villager": 1
                }
            }
        }
        path = self._write_config(data)
        config = load_config(path)
        active = get_active_models(config.models)
        self.assertEqual(len(active), 2)


if __name__ == "__main__":
    unittest.main()
