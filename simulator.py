
import numpy as np
from collections import deque


class MemoryLocation:
    def __init__(self, instruction=(), decimal=0):
        if instruction and decimal:
            raise ValueError('When setting a memory location, specify only the'
                             ' instruction or data value, not both')

        INSTR_TO_OPCODE = {'halt': 0, 'jump': 1, 'jzer': 2, 'jpos': 3,
                           'load': 4, 'stor': 5, 'store': 5, 'add': 6,
                           'sub': 7, 'read': 4, 'write': 5}
        OPCODE_TO_INSTR = ['halt',  'jump', 'jzer', 'jpos', 'load', 'stor',
                            'add', 'sub']

        if instruction:
            self.instruction = instruction[0]
            self.operand = instruction[1]
            self.decimal = 32 * INSTR_TO_OPCODE[self.instruction] + self.operand
            self.decimal = (self.decimal - 256 if self.decimal >= 128
                            else self.decimal)
        else:
            self.decimal = decimal
            binary = np.binary_repr(self.decimal, width=8)
            if len(binary) > 8:
                raise ValueError('Overflow!')
            self.instruction = OPCODE_TO_INSTR[int(binary[:3], base=2)]
            self.operand = int(binary[3:], base=2)

    def __repr__(self):
        return '{} {}'.format(self.instruction, self.operand)

    def __str__(self):
        return '{} {}'.format(self.instruction, self.operand)


class CPU:
    def __init__(self):
        self.pc = 0  # program counter
        self.ac = 0  # accumulator
        self.memory = [MemoryLocation(decimal=0) for i in range(30)]
        self.input_buffer = deque()
        self.output_buffer = list()
        self._symbol_table = dict()
        self._JUMP_TABLE = {'halt':  self._execute_halt,
                            'jump':  self._execute_jump,
                            'jzer':  self._execute_jzer,
                            'jpos':  self._execute_jpos,
                            'load':  self._execute_load,
                            'stor':  self._execute_stor,
                            'store': self._execute_stor,
                            'add':   self._execute_add,
                            'sub':   self._execute_sub,
                            'read':  self._execute_load,
                            'write': self._execute_stor}

    def _execute_halt(self):
        raise ValueError('Attempted to execute a HALT')

    def _execute_jump(self, data):
        if type(data) is not int or data < 0 or data > 29:
            raise ValueError(f'Invalid JUMP address {data}')
        self.pc = data

    def _execute_jzer(self, data):
        if type(data) is not int or data < 0 or data > 29:
            raise ValueError(f'Invalid JZER address {data}')
        if self.ac == 0:
            self.pc = data
        else:
            self.pc += 1

    def _execute_jpos(self, data):
        if type(data) is not int or data < 0 or data > 29:
            raise ValueError(f'Invalid JPOS address {data}')
        if self.ac > 0:
            self.pc = data
        else:
            self.pc += 1

    def _execute_load(self, data):
        if type(data) is not int or data < 0 or data > 30:
            raise ValueError(f'Invalid LOAD address {data}')
        if data != 30:
            self.ac = self.memory[data].decimal
        else:  # read input
            self.ac = self.input_buffer.popleft()
        self.pc += 1

    def _execute_stor(self, data):
        if type(data) is not int or data < 0 or data > 31 or data == 30:
            raise ValueError(f'Invalid STOR address {data}')
        if data != 31:
            self.memory[data] = MemoryLocation(decimal=self.ac)
        else:  # write output
            self.output_buffer.append(self.ac)
        self.pc += 1

    def _execute_add(self, data):
        if type(data) is not int or data < 0 or data > 29:
            raise ValueError(f'Invalid ADD address {data}')
        self.ac += self.memory[data].decimal
        self.pc += 1

    def _execute_sub(self, data):
        if type(data) is not int or data < 0 or data > 29:
            raise ValueError(f'Invalid SUB address {data}')
        self.ac -= self.memory[data].decimal
        self.pc += 1

    @staticmethod
    def _strip_comment(str_):
        try:
            return str_[:str_.index('#')]
        except ValueError:  # no comment on line
            return str_

    def _inline_labels(self, program):
        new_program = []
        i = 0
        while i < len(program):
            line = program[i]
            if line[-1] == ':' and i + 1 < len(program):
                new_program.append('{} {}'.format(line, program[i+1]))
                i += 1
            else:
                new_program.append(line)
            i += 1
        return new_program

    def _fill_symbol_table(self, program):
        for idx, line in enumerate(program):
            tokens = line.split(':')
            if len(tokens) > 1:
                self._symbol_table[tokens[0].strip()] = idx

    def _expand_pseudo_ops(self, tokens):
        if tokens[0] == 'read':
            return ['load', '11110']
        elif tokens[0] == 'write':
            return ['stor', '11111']
        elif tokens[0] == 'halt':
            return ['halt', '00000']
        return tokens

    def _assemble_instruction(self, idx, line, tokens):
        if len(tokens) > 2:
            raise ValueError(f'Invalid instruction {line}')

        tokens = self._expand_pseudo_ops(tokens)
        instruction, data = tokens[0], tokens[1]

        if data in self._symbol_table:  # expand if label is found
            data = self._symbol_table[data]
        else:  # otherwise validate that it is a number
            try:
                data = int(data, base=2)
            except ValueError:
                try:
                    data = int(data)
                except ValueError:
                    raise ValueError(f'Invalid operand {data} on line {idx}')
        self.memory[idx] = MemoryLocation(instruction=(instruction, data))

    def _assemble_data(self, idx, line, tokens):
        if len(tokens) != 1:
            raise ValueError(f'Illegal line {idx}:{line}')
        try:
            self.memory[idx] = MemoryLocation(decimal=int(tokens[0]))
        except ValueError:
            raise ValueError(f'Invalid data value {tokens[0]}')

    def _assemble(self, program):
        for idx, line in enumerate(program):
            # remove labels
            tokens = line.split(':')
            tokens = ' '.join(tokens[1:]) if len(tokens) > 1 else tokens[0]
            tokens = tokens.split()

            # assemble line
            if tokens[0] not in self._JUMP_TABLE:
                self._assemble_data(idx, line, tokens)
            else:
                self._assemble_instruction(idx, line, tokens)

    def run_program(self, program_filename, input_buffer=()):
        try:
            with open(program_filename, 'r') as in_file:
                program = in_file.read()
        except IOError:
            raise IOError(f'File {program_filename} not found.')

        program = [CPU._strip_comment(line).lower().strip()
                   for line in program.splitlines() if len(line) > 0]
        program = [line for line in program if len(line) > 0]
        program = self._inline_labels(program)
        self._fill_symbol_table(program)
        self._assemble(program)

        self.input_buffer = deque(input_buffer)
        while self.memory[self.pc].instruction != 'halt':
            instruction = self.memory[self.pc].instruction
            operand = self.memory[self.pc].operand
            self._JUMP_TABLE[instruction](data=operand)

    def get_state(self):
        return (self.ac, self.memory, self.output_buffer)


if __name__ == '__main__':
    import sys
    simulator = CPU()
    print()
    print(f'File: {sys.argv[1]}')
    simulator.run_program(sys.argv[1], input_buffer=(10,15))
    print(simulator.get_state())
    print()
