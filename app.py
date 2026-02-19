#!/usr/bin/env python3
"""Flask API wrapper for HYMN simulator."""

from flask import Flask, request, jsonify, send_from_directory, session
from simulator import CPU, MemoryLocation
from collections import deque
from threading import RLock
from time import monotonic, time
from datetime import timedelta
import secrets
import os

MAX_SESSIONS = int(os.environ.get("MAX_SESSIONS", "1000"))
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", "7200"))
EXECUTION_TIMEOUT_SECONDS = int(os.environ.get("EXECUTION_TIMEOUT_SECONDS", "60"))

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("SESSION_COOKIE_SECURE", "0").lower() in ("1", "true", "yes")
)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=SESSION_TTL_SECONDS)


class SessionStore:
    """Thread-safe in-memory CPU session store with bounded retention."""

    def __init__(self, max_sessions=MAX_SESSIONS, ttl_seconds=SESSION_TTL_SECONDS):
        self._sessions = {}
        self._session_locks = {}
        self._lock = RLock()
        self._max_sessions = max_sessions
        self._ttl_seconds = ttl_seconds

    def _cleanup_locked(self, now):
        stale_ids = [
            sid for sid, (_, last_seen) in self._sessions.items()
            if now - last_seen > self._ttl_seconds
        ]
        for sid in stale_ids:
            del self._sessions[sid]
            self._session_locks.pop(sid, None)

        if len(self._sessions) <= self._max_sessions:
            return

        # Evict least-recently-used sessions when above capacity.
        sorted_sessions = sorted(self._sessions.items(), key=lambda item: item[1][1])
        overflow = len(self._sessions) - self._max_sessions
        for sid, _ in sorted_sessions[:overflow]:
            del self._sessions[sid]
            self._session_locks.pop(sid, None)

    def put(self, session_id, cpu):
        with self._lock:
            now = time()
            self._cleanup_locked(now)
            self._sessions[session_id] = (cpu, now)
            self._session_locks.setdefault(session_id, RLock())

    def get(self, session_id):
        with self._lock:
            current = self._sessions.get(session_id)
            if not current:
                return None
            cpu, _ = current
            self._sessions[session_id] = (cpu, time())
            return cpu

    def delete(self, session_id):
        with self._lock:
            self._sessions.pop(session_id, None)
            self._session_locks.pop(session_id, None)

    def lock_for(self, session_id, create=False):
        with self._lock:
            lock = self._session_locks.get(session_id)
            if lock is None and create:
                lock = RLock()
                self._session_locks[session_id] = lock
            return lock


sessions = SessionStore()


def _request_json():
    return request.get_json(silent=True) or {}


def _get_session_id(create=False):
    session_id = session.get("sid")
    if isinstance(session_id, str) and session_id:
        return session_id
    if not create:
        return None

    session_id = secrets.token_urlsafe(32)
    session["sid"] = session_id
    session.permanent = True
    return session_id


def _cpu_from_request(data):
    session_id = _get_session_id(create=False)
    if session_id is None:
        return None, None, None, (jsonify({"error": "No program loaded"}), 400)

    session_lock = sessions.lock_for(session_id, create=False)
    if session_lock is None:
        return None, None, None, (jsonify({"error": "No program loaded"}), 400)

    session_lock.acquire()

    cpu = sessions.get(session_id)
    if not cpu:
        session_lock.release()
        return None, None, None, (jsonify({"error": "No program loaded"}), 400)
    return session_id, cpu, session_lock, None


class SteppableCPU(CPU):
    """Wrapper that adds step-by-step execution without modifying original."""

    def load_program(self, code: str, input_buffer=()):
        self.pc = 0
        self.ac = 0
        self.memory = [MemoryLocation(decimal=0) for _ in range(30)]
        self.output_buffer = []
        self._symbol_table = {}
        self.halted = False
        self.error = None
        self.waiting_for_input = False
        self.source_lines = code.strip().split('\n')

        program = [CPU._strip_comment(line).lower().strip()
                   for line in code.splitlines() if len(line) > 0]
        program = [line for line in program if len(line) > 0]
        program = self._inline_labels(program)
        self._fill_symbol_table(program)
        self._assemble(program)
        self.input_buffer = deque(input_buffer)

    def needs_input(self):
        """Check if current instruction is READ and input buffer is empty."""
        if self.halted or self.error:
            return False
        instruction = self.memory[self.pc].instruction
        operand = self.memory[self.pc].operand
        # READ is load from address 30
        is_read = (instruction == 'load' and operand == 30)
        return is_read and len(self.input_buffer) == 0

    def step(self):
        if self.halted or self.error:
            return False

        # Check if we need input before executing
        if self.needs_input():
            self.waiting_for_input = True
            return False

        self.waiting_for_input = False

        try:
            if self.memory[self.pc].instruction == 'halt':
                self.halted = True
                return False
            instruction = self.memory[self.pc].instruction
            operand = self.memory[self.pc].operand
            self._JUMP_TABLE[instruction](data=operand)
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def provide_input(self, value: int):
        """Add a value to the input buffer."""
        self.input_buffer.append(value)
        self.waiting_for_input = False

    def run_all(self, timeout_seconds=EXECUTION_TIMEOUT_SECONDS):
        start = monotonic()
        steps = 0
        while self.step():
            steps += 1
            if monotonic() - start >= timeout_seconds:
                self.error = f"Execution timed out after {timeout_seconds} seconds"
                break
        return steps

    def to_state(self):
        return {
            "pc": self.pc,
            "ac": self.ac,
            "memory": [{"decimal": m.decimal, "instr": str(m)} for m in self.memory],
            "output": list(self.output_buffer),
            "input": list(self.input_buffer),
            "halted": self.halted,
            "error": self.error,
            "symbols": self._symbol_table,
            "waiting_for_input": self.waiting_for_input,
        }


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/docs")
def docs():
    return send_from_directory("static", "docs.html")


@app.route("/credits")
def credits():
    return send_from_directory("static", "credits.html")


@app.route("/api/load", methods=["POST"])
def load():
    data = _request_json()
    code = data.get("code", "")
    input_buf = data.get("input", [])
    session_id = _get_session_id(create=True)
    session_lock = sessions.lock_for(session_id, create=True)

    try:
        input_buf = [int(x) for x in input_buf if str(x).strip()]
    except ValueError:
        return jsonify({"error": "Invalid input buffer"}), 400

    with session_lock:
        cpu = SteppableCPU()
        try:
            cpu.load_program(code, tuple(input_buf))
        except Exception as e:
            return jsonify({"error": str(e)}), 400

        sessions.put(session_id, cpu)
        return jsonify(cpu.to_state())


@app.route("/api/step", methods=["POST"])
def step():
    _, cpu, session_lock, error = _cpu_from_request(_request_json())
    if error:
        return error
    try:
        cpu.step()
        return jsonify(cpu.to_state())
    finally:
        session_lock.release()


@app.route("/api/run", methods=["POST"])
def run():
    _, cpu, session_lock, error = _cpu_from_request(_request_json())
    if error:
        return error
    try:
        cpu.run_all(timeout_seconds=EXECUTION_TIMEOUT_SECONDS)
        return jsonify(cpu.to_state())
    finally:
        session_lock.release()


@app.route("/api/reset", methods=["POST"])
def reset():
    _request_json()
    session_id = _get_session_id(create=False)
    if session_id is None:
        return jsonify({"status": "reset"})
    session_lock = sessions.lock_for(session_id, create=False)
    if session_lock is None:
        return jsonify({"status": "reset"})

    with session_lock:
        sessions.delete(session_id)
    return jsonify({"status": "reset"})


@app.route("/api/memory", methods=["POST"])
def update_memory():
    """Update a memory location by address and decimal value."""
    data = _request_json()
    _, cpu, session_lock, error = _cpu_from_request(data)
    if error:
        return error

    try:
        address = data.get("address")
        decimal = data.get("decimal")

        if address is None or decimal is None:
            return jsonify({"error": "Missing address or decimal"}), 400

        if not isinstance(address, int) or address < 0 or address > 29:
            return jsonify({"error": "Invalid address (must be 0-29)"}), 400

        if not isinstance(decimal, int) or decimal < -128 or decimal > 127:
            return jsonify({"error": "Invalid value (must be -128 to 127)"}), 400

        try:
            cpu.memory[address] = MemoryLocation(decimal=decimal)
            return jsonify(cpu.to_state())
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    finally:
        session_lock.release()


@app.route("/api/register", methods=["POST"])
def update_register():
    """Update PC or AC register."""
    data = _request_json()
    _, cpu, session_lock, error = _cpu_from_request(data)
    if error:
        return error

    try:
        register = data.get("register")
        value = data.get("value")

        if register is None or value is None:
            return jsonify({"error": "Missing register or value"}), 400

        if register == "pc":
            if not isinstance(value, int) or value < 0 or value > 29:
                return jsonify({"error": "Invalid PC value (must be 0-29)"}), 400
            cpu.pc = value
        elif register == "ac":
            if not isinstance(value, int) or value < -128 or value > 127:
                return jsonify({"error": "Invalid AC value (must be -128 to 127)"}), 400
            cpu.ac = value
        else:
            return jsonify({"error": "Invalid register (must be 'pc' or 'ac')"}), 400

        return jsonify(cpu.to_state())
    finally:
        session_lock.release()


@app.route("/api/input", methods=["POST"])
def provide_input():
    """Provide input value when CPU is waiting for input."""
    data = _request_json()
    _, cpu, session_lock, error = _cpu_from_request(data)
    if error:
        return error

    try:
        value = data.get("value")

        if value is None:
            return jsonify({"error": "Missing value"}), 400

        try:
            value = int(value)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid value (must be an integer)"}), 400

        if value < -128 or value > 127:
            return jsonify({"error": "Value out of range (must be -128 to 127)"}), 400

        cpu.provide_input(value)
        return jsonify(cpu.to_state())
    finally:
        session_lock.release()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
