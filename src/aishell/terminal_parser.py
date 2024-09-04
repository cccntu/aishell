import json
import os
import re

class TerminalParser:
    def __init__(self):
        self.screen = self.initialize_screen()
        self.cursor_row = 0
        self.cursor_col = 0
        self.log_output = []
        self.vim_mode = False # this is not just vim, this flag is for when we are in an alternate screen buffer
        self.pre_vim_screen = None
        self.csi_regex = re.compile(r'\x1b\[([?]?\d*(?:;\d+)*)([A-Za-z])')
        self.scs_regex = re.compile(r'\x1b[\(\)][@-~]')  # New regex for SCS sequences

    def initialize_screen(self):
        return [[]]

    def screen_to_string(self):
        return '\n'.join(''.join(row).rstrip() for row in self.screen if row)

    def ensure_cursor_position(self, cursor_row, cursor_col, line_log):
        while len(self.screen) <= cursor_row:
            line_log.append('<ecp-new-line>')
            self.screen.append([])
        while len(self.screen[cursor_row]) <= cursor_col:
            self.screen[cursor_row].append(' ')

    def process_line(self, line):
        line_log = []
        i = 0
        while i < len(line):
            if line[i] == '\x1b':  # ESC character
                if i + 1 < len(line) and line[i + 1] == '[':
                    # CSI sequence
                    match = self.csi_regex.match(line[i:])
                    if match:
                        line_log.append('<CSI>')
                        params, command = match.groups()
                        sequence = match.group()
                        if sequence == '\x1b[?1049h':
                            # Vim enter alternate screen
                            line_log.append('<Vim enter alternate screen>')
                            self.vim_mode = True
                            self.pre_vim_screen = [row[:] for row in self.screen]
                            self.screen = self.initialize_screen()
                            self.cursor_row = self.cursor_col = 0
                        elif sequence == '\x1b[?1049l':
                            # Vim exit alternate screen
                            line_log.append('<Vim exit alternate screen>')
                            self.vim_mode = False
                            if self.pre_vim_screen:
                                self.screen = self.pre_vim_screen
                            else:
                                self.screen = self.initialize_screen()
                            self.cursor_row = len(self.screen) - 1
                            self.cursor_col = len(self.screen[-1])
                        elif command == 'H':  # \x1b[{row};{col}H
                            # Set cursor position
                            parts = params.split(';')
                            self.cursor_row = int(parts[0]) - 1 if parts[0] else 0
                            self.cursor_col = int(parts[1]) - 1 if len(parts) > 1 else 0
                            self.ensure_cursor_position(self.cursor_row, self.cursor_col, line_log)
                            line_log.append(f'<CSI-H {self.cursor_row} {self.cursor_col}>')
                        elif command == 'J':  # \x1b[{n}J
                            # Clear screen
                            n = params or '0'
                            if n == '0':
                                self.screen[self.cursor_row] = self.screen[self.cursor_row][:self.cursor_col]
                                self.screen = self.screen[:self.cursor_row+1]
                                line_log.append('<CSI-J clear till end>')
                            elif n == '1':
                                for row in range(self.cursor_row):
                                    self.screen[row] = []
                                self.screen[self.cursor_row] = [' '] * self.cursor_col + self.screen[self.cursor_row][self.cursor_col:]
                                line_log.append('<CSI-J1 clear till beginning>')
                            elif n == '2':
                                self.screen = self.initialize_screen()
                                self.cursor_row = self.cursor_col = 0
                                line_log.append('<CSI-J2 clear all>')
                        elif command == 'K':  # \x1b[{n}K
                            # Clear line
                            n = params or '0'
                            if n == '0':
                                self.screen[self.cursor_row] = self.screen[self.cursor_row][:self.cursor_col]
                                line_log.append('<CSI-K clear line to the right>')
                            elif n == '1':
                                self.screen[self.cursor_row] = [' '] * self.cursor_col + self.screen[self.cursor_row][self.cursor_col:]
                                line_log.append('<CSI-K1 clear line to the left>')
                            elif n == '2':
                                self.screen[self.cursor_row] = []
                                line_log.append('<CSI-K2 clear line>')
                        elif command == 'A':  # \x1b[{n}A
                            # Move cursor up
                            n = int(params) if params else 1
                            self.cursor_row = max(0, self.cursor_row - n)
                            line_log.append(f'<CSI-A move up {n}, {self.cursor_row}/{len(self.screen)}>')
                        elif command == 'B':  # \x1b[{n}B
                            # Move cursor down
                            n = int(params) if params else 1
                            self.cursor_row = min(len(self.screen) - 1, self.cursor_row + n)
                        elif command == 'C':  # \x1b[{n}C
                            # Move cursor forward
                            n = int(params) if params else 1
                            self.cursor_col = min(len(self.screen[self.cursor_row]), self.cursor_col + n)
                        elif command == 'D':  # \x1b[{n}D
                            # Move cursor backward
                            n = int(params) if params else 1
                            self.cursor_col = max(0, self.cursor_col - n)
                        i += len(sequence)
                        continue
                elif i + 1 < len(line) and line[i + 1] in '()':
                    # SCS sequence: fish shell prompt uses this
                    # we ignore it for now
                    match = self.scs_regex.match(line[i:])
                    if match:
                        line_log.append('<SCS>')
                        i += len(match.group())
                        continue

                elif i + 1 < len(line) and line[i + 1] == ']':
                    line_log.append('<OSI>')
                    # OSC sequence
                    j = i + 2
                    while j < len(line) and line[j] != '\x07':  # BEL character
                        j += 1
                    i = j + 1 if j < len(line) else len(line)
                    continue
            elif line[i] == '\r':
                self.cursor_col = 0
            elif line[i] == '\b':
                self.cursor_col = max(0, self.cursor_col - 1)
            else:
                self.ensure_cursor_position(self.cursor_row, self.cursor_col, line_log)
                line_log.append(f'<ecp {self.cursor_row}/{len(self.screen)}:{self.cursor_col}/{len(self.screen[self.cursor_row])}>')
                if self.cursor_col == len(self.screen[self.cursor_row]) - 1:
                    line_log.append(f'<write {line[i]}>')
                else:
                    line_log.append(f'<ecp-insert {line[i]}>')
                self.screen[self.cursor_row][self.cursor_col] = line[i]
                self.cursor_col += 1
            i += 1

        # Handle newline at the end of each input line
        if not self.vim_mode:
            self.cursor_row += 1
            self.cursor_col = 0
            self.screen.append([])
            line_log.append('<my new line>')

        self.log_output.append(''.join(line_log))

    def get_screen_state(self):
        # Remove trailing empty lines
        while self.screen and not self.screen[-1]:
            self.screen.pop()
        return self.screen_to_string(), '\n'.join(self.log_output)

def process_terminal_output(raw_output):
    parser = TerminalParser()
    lines = raw_output.split('\n')
    for line in lines:
        parser.process_line(line)
    return parser.get_screen_dump()
