import os
import socket
import argparse

def get_screen_context(line_limit=None):
    socket_file = os.environ.get("AISHELL_SOCKET")
    if not socket_file:
        raise RuntimeError("AIShell socket not found. Make sure AIShell is running.")

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client_socket:
            client_socket.connect(socket_file)
            client_socket.sendall(b"GET_SCREEN_STATE")
            client_socket.settimeout(5)

            length_bytes = client_socket.recv(4)
            length = int.from_bytes(length_bytes, byteorder='big')

            response = b""
            while len(response) < length:
                try:
                    chunk = client_socket.recv(min(4096, length - len(response)))
                    if not chunk:
                        break
                    response += chunk
                except socket.timeout:
                    raise TimeoutError("Timeout while receiving data")

            response_text = response.decode('utf-8')
            client_socket.sendall(b"END")

            if line_limit and line_limit > 0:
                lines = response_text.split('\n')
                return '\n'.join(lines[-line_limit:])
            return response_text

    except Exception as e:
        raise RuntimeError(f"Error connecting to AIShell socket: {e}")

def main():
    parser = argparse.ArgumentParser(description="Get AIShell screen state and save it to a file. Helpful for debugging or when you want to see what's captured by the AIShell.")
    parser.add_argument("--print", "-p", action="store_true", help="Print the log to stdout instead of writing to a file. Warning: This can get messy if done repeatedly.")
    parser.add_argument("--lines", "-n", type=int, default=20, help="Number of lines to print (default: 20)")
    parser.add_argument("--output", "-o", type=str, default="~/.aishell_get_screen", help="Output file path (default: ~/.aishell_get_screen)")
    args = parser.parse_args()

    try:
        context = get_screen_context(args.lines)

        if args.print:
            for line in context.split('\n'):
                print(f"| {line}")
        else:
            output_file = os.path.expanduser(args.output)
            with open(output_file, 'w') as f:
                f.write(context)
            print(f"Screen state saved to {output_file}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()