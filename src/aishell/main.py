import os
import sys
import pty
import select
import termios
import tty
import signal
import fcntl
import struct
import socket
import tempfile
import argparse

from .terminal_parser import TerminalParser

AISHELL_ENV_VAR = "AISHELL_ACTIVE"
SOCKET_ENV_VAR = "AISHELL_SOCKET"

def set_winsize(fd, rows, cols):
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

def get_winsize(fd):
    winsize = fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8)
    rows, cols, _, _ = struct.unpack("HHHH", winsize)
    return rows, cols

def get_terminal_settings(fd):
    return termios.tcgetattr(fd)

def set_terminal_settings(fd, settings):
    termios.tcsetattr(fd, termios.TCSANOW, settings)

def handle_client_connection(client_socket, term, shell_state):
    shell_state['print_count'] = shell_state.get('print_count', 0) + 1
    try:
        request = client_socket.recv(1024).decode('utf-8')
        if request == "GET_SCREEN_STATE":
            screen_state, _ = term.get_screen_state()
            screen_state_bytes = screen_state.encode('utf-8')
            length_bytes = len(screen_state_bytes).to_bytes(4, byteorder='big')
            client_socket.sendall(length_bytes + screen_state_bytes)

            # Wait for the "END" message or timeout after 5 seconds
            client_socket.settimeout(5)
            try:
                end_message = client_socket.recv(1024).decode('utf-8')
                if end_message != "END":
                    print("Unexpected end message from client")
            except socket.timeout:
                print("Client connection timed out")
        elif request == "GET_PRINT_COUNT":
            count = shell_state['print_count']
            message = f"aishell-print has been called {count} times."
            client_socket.sendall(message.encode('utf-8'))
    finally:
        client_socket.close()

def start_socket_server(socket_file):
    if os.path.exists(socket_file):
        os.remove(socket_file)

    server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_socket.bind(socket_file)
    server_socket.listen(1)
    return server_socket

def run_shell():
    parser = argparse.ArgumentParser(description="AIShell - An AI-enhanced shell")
    parser.add_argument('--shell', "-s", default=os.environ.get('SHELL', '/bin/bash'),
                        help="Specify the shell to use (default: $SHELL or /bin/bash)")
    args = parser.parse_args()

    if os.environ.get(AISHELL_ENV_VAR):
        print("AISHELL_ENV_VAR is set. You appear to be already in an AIShell session. Nested sessions are not supported. Exit with ctrl-d or exit")
        return

    shell = args.shell
    print(f"✨✨✨ Starting AIShell with {shell} ✨✨✨")

    old_tty = termios.tcgetattr(sys.stdin)

    # Create temporary file for the socket and set environment variable
    temp_socket = tempfile.NamedTemporaryFile(delete=False)
    socket_file = temp_socket.name
    temp_socket.close()
    os.environ[SOCKET_ENV_VAR] = socket_file

    shell_state = {}
    try:
        pid, fd = pty.fork()

        if pid == 0:  # Child process
            os.environ[AISHELL_ENV_VAR] = "1"
            os.execvp(shell, [shell, "-i"])
        else:  # Parent process
            term = TerminalParser()
            buffer = b""

            def sigwinch_handler(signum, frame):
                rows, cols = get_winsize(sys.stdin.fileno())
                set_winsize(fd, rows, cols)
                os.kill(pid, signal.SIGWINCH)

            signal.signal(signal.SIGWINCH, sigwinch_handler)
            sigwinch_handler(None, None)  # Initial size setup

            tty.setraw(sys.stdin.fileno())
            tty.setcbreak(fd)

            initial_fd_settings = get_terminal_settings(fd)

            new_fd_settings = list(initial_fd_settings)
            # set echo and canonical mode
            new_fd_settings[3] = new_fd_settings[3] | termios.ECHO | termios.ICANON
            set_terminal_settings(fd, new_fd_settings)

            server_socket = start_socket_server(socket_file)

            def handle_terminal_and_buffer(buffer, term):
                buffer_utf8 = buffer.decode('utf-8', errors='ignore')
                if '\n' in buffer_utf8:
                    lines = buffer_utf8.split('\n')
                    for line in lines[:-1]:
                        term.process_line(line)
                    buffer = lines[-1].encode('utf-8')
                return buffer, term

            while True:
                try:
                    r, w, e = select.select([sys.stdin, fd, server_socket], [], [])

                    if sys.stdin in r:
                        # sys.stdin is the terminal
                        data = os.read(sys.stdin.fileno(), 1024)
                        if not data:
                            break
                        os.write(fd, data)

                    if fd in r:
                        # fd is the pty output
                        data = os.read(fd, 1024)
                        if not data:
                            break
                        os.write(sys.stdout.fileno(), data)
                        sys.stdout.flush()

                        buffer += data

                        if len(buffer) > 10000:
                            buffer, term = handle_terminal_and_buffer(buffer, term)

                    if server_socket in r:
                        client_socket, _ = server_socket.accept()
                        buffer, term = handle_terminal_and_buffer(buffer, term)
                        handle_client_connection(client_socket, term, shell_state)

                except (OSError, IOError):
                    pass

    finally:
        # Restore the original terminal settings
        termios.tcsetattr(sys.stdin, termios.TCSAFLUSH, old_tty)
        if os.path.exists(socket_file):
            os.remove(socket_file)
        print('💫 AIShell session ended 💫')

def main():
    run_shell()

if __name__ == "__main__":
    main()