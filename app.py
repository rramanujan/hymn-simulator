#!/usr/bin/env python3
"""Flask API wrapper for HYMN simulator."""

from flask import Flask, request, jsonify, send_from_directory
from simulator import CPU, MemoryLocation
from collections import deque
import os

app = Flask(__name__, static_folder="static")

sessions = {}


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

    def run_all(self, max_steps=10000):
        steps = 0
        while steps < max_steps and self.step():
            steps += 1
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
    data = request.json
    code = data.get("code", "")
    input_buf = data.get("input", [])
    session_id = data.get("session", "default")

    try:
        input_buf = [int(x) for x in input_buf if str(x).strip()]
    except ValueError:
        return jsonify({"error": "Invalid input buffer"}), 400

    cpu = SteppableCPU()
    try:
        cpu.load_program(code, tuple(input_buf))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    sessions[session_id] = cpu
    return jsonify(cpu.to_state())


@app.route("/api/step", methods=["POST"])
def step():
    session_id = request.json.get("session", "default")
    cpu = sessions.get(session_id)
    if not cpu:
        return jsonify({"error": "No program loaded"}), 400
    cpu.step()
    return jsonify(cpu.to_state())


@app.route("/api/run", methods=["POST"])
def run():
    session_id = request.json.get("session", "default")
    cpu = sessions.get(session_id)
    if not cpu:
        return jsonify({"error": "No program loaded"}), 400
    cpu.run_all()
    return jsonify(cpu.to_state())


@app.route("/api/reset", methods=["POST"])
def reset():
    session_id = request.json.get("session", "default")
    if session_id in sessions:
        del sessions[session_id]
    return jsonify({"status": "reset"})


@app.route("/api/memory", methods=["POST"])
def update_memory():
    """Update a memory location by address and decimal value."""
    session_id = request.json.get("session", "default")
    cpu = sessions.get(session_id)
    if not cpu:
        return jsonify({"error": "No program loaded"}), 400

    address = request.json.get("address")
    decimal = request.json.get("decimal")

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


@app.route("/api/register", methods=["POST"])
def update_register():
    """Update PC or AC register."""
    session_id = request.json.get("session", "default")
    cpu = sessions.get(session_id)
    if not cpu:
        return jsonify({"error": "No program loaded"}), 400

    register = request.json.get("register")
    value = request.json.get("value")

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


@app.route("/api/input", methods=["POST"])
def provide_input():
    """Provide input value when CPU is waiting for input."""
    session_id = request.json.get("session", "default")
    cpu = sessions.get(session_id)
    if not cpu:
        return jsonify({"error": "No program loaded"}), 400

    value = request.json.get("value")

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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
