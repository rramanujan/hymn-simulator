import unittest
from unittest.mock import patch

from app import app


PROGRAM_A = """
load 3
write
halt
7
"""

PROGRAM_B = """
load 3
write
halt
9
"""

INFINITE_LOOP_PROGRAM = """
jump 0
"""


class SessionIsolationTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_sessions_are_isolated(self):
        res = self.client.post(
            "/api/load", json={"session": "user-a", "code": PROGRAM_A, "input": []}
        )
        self.assertEqual(res.status_code, 200)

        res = self.client.post(
            "/api/load", json={"session": "user-b", "code": PROGRAM_B, "input": []}
        )
        self.assertEqual(res.status_code, 200)

        run_a = self.client.post("/api/run", json={"session": "user-a"})
        run_b = self.client.post("/api/run", json={"session": "user-b"})
        data_a = run_a.get_json()
        data_b = run_b.get_json()

        self.assertEqual(run_a.status_code, 200)
        self.assertEqual(run_b.status_code, 200)
        self.assertEqual(data_a["output"], [7])
        self.assertEqual(data_b["output"], [9])

    def test_session_id_is_required(self):
        res = self.client.post("/api/load", json={"code": "halt", "input": []})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["error"], "Missing session ID")

    def test_run_times_out_for_infinite_loop(self):
        load = self.client.post(
            "/api/load",
            json={"session": "loop-user", "code": INFINITE_LOOP_PROGRAM, "input": []},
        )
        self.assertEqual(load.status_code, 200)

        with patch("app.EXECUTION_TIMEOUT_SECONDS", 0):
            run = self.client.post("/api/run", json={"session": "loop-user"})

        data = run.get_json()
        self.assertEqual(run.status_code, 200)
        self.assertIn("timed out", data["error"])
        self.assertFalse(data["halted"])


if __name__ == "__main__":
    unittest.main()
