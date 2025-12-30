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
        self.source_lines = code.strip().split('\n')

        program = [CPU._strip_comment(line).lower().strip()
                   for line in code.splitlines() if len(line) > 0]
        program = [line for line in program if len(line) > 0]
        program = self._inline_labels(program)
        self._fill_symbol_table(program)
        self._assemble(program)
        self.input_buffer = deque(input_buffer)

    def step(self):
        if self.halted or self.error:
            return False
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
        }


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
