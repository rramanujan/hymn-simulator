import unittest
import threading
import time
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
        self.client_a = app.test_client()
        self.client_b = app.test_client()

    def test_sessions_are_isolated(self):
        res = self.client_a.post("/api/load", json={"code": PROGRAM_A, "input": []})
        self.assertEqual(res.status_code, 200)

        res = self.client_b.post("/api/load", json={"code": PROGRAM_B, "input": []})
        self.assertEqual(res.status_code, 200)

        run_a = self.client_a.post("/api/run", json={})
        run_b = self.client_b.post("/api/run", json={})
        data_a = run_a.get_json()
        data_b = run_b.get_json()

        self.assertEqual(run_a.status_code, 200)
        self.assertEqual(run_b.status_code, 200)
        self.assertEqual(data_a["output"], [7])
        self.assertEqual(data_b["output"], [9])

    def test_run_requires_loaded_program(self):
        res = self.client_a.post("/api/run", json={})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["error"], "No program loaded")

    def test_run_times_out_for_infinite_loop(self):
        load = self.client_a.post("/api/load", json={"code": INFINITE_LOOP_PROGRAM, "input": []})
        self.assertEqual(load.status_code, 200)

        with patch("app.EXECUTION_TIMEOUT_SECONDS", 0):
            run = self.client_a.post("/api/run", json={})

        data = run.get_json()
        self.assertEqual(run.status_code, 200)
        self.assertIn("timed out", data["error"])
        self.assertFalse(data["halted"])

    def test_same_session_requests_are_serialized(self):
        load = self.client_a.post("/api/load", json={"code": "halt", "input": []})
        self.assertEqual(load.status_code, 200)

        session_cookie = self.client_a.get_cookie("session")
        self.assertIsNotNone(session_cookie)
        self.client_b.set_cookie("session", session_cookie.value)

        results = {}

        def slow_run_all(*args, **kwargs):
            time.sleep(0.25)
            return 0

        def do_run():
            results["run"] = self.client_a.post("/api/run", json={})

        def do_register():
            start = time.monotonic()
            results["register"] = self.client_b.post(
                "/api/register", json={"register": "pc", "value": 0}
            )
            results["register_elapsed"] = time.monotonic() - start

        with patch("app.SteppableCPU.run_all", side_effect=slow_run_all):
            run_thread = threading.Thread(target=do_run)
            reg_thread = threading.Thread(target=do_register)

            run_thread.start()
            time.sleep(0.05)
            reg_thread.start()

            run_thread.join()
            reg_thread.join()

        self.assertEqual(results["run"].status_code, 200)
        self.assertEqual(results["register"].status_code, 200)
        self.assertGreaterEqual(results["register_elapsed"], 0.18)

    def test_different_sessions_do_not_block_each_other(self):
        load_a = self.client_a.post("/api/load", json={"code": "halt", "input": []})
        load_b = self.client_b.post("/api/load", json={"code": "halt", "input": []})
        self.assertEqual(load_a.status_code, 200)
        self.assertEqual(load_b.status_code, 200)

        results = {}

        def slow_run_all(*args, **kwargs):
            time.sleep(0.25)
            return 0

        def do_run():
            results["run"] = self.client_a.post("/api/run", json={})

        def do_register():
            start = time.monotonic()
            results["register"] = self.client_b.post(
                "/api/register", json={"register": "pc", "value": 0}
            )
            results["register_elapsed"] = time.monotonic() - start

        with patch("app.SteppableCPU.run_all", side_effect=slow_run_all):
            run_thread = threading.Thread(target=do_run)
            reg_thread = threading.Thread(target=do_register)

            run_thread.start()
            time.sleep(0.05)
            reg_thread.start()

            run_thread.join()
            reg_thread.join()

        self.assertEqual(results["run"].status_code, 200)
        self.assertEqual(results["register"].status_code, 200)
        self.assertLess(results["register_elapsed"], 0.15)


if __name__ == "__main__":
    unittest.main()
