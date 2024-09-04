import os
import socket

def main():
    socket_file = os.environ.get("AISHELL_SOCKET")
    if not socket_file:
        print("AIShell socket not found. Make sure AIShell is running.")
        return

    try:
        client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client_socket.connect(socket_file)
        client_socket.sendall(b"GET_PRINT_COUNT")
        response = client_socket.recv(1024).decode('utf-8')
        print(response)
    except Exception as e:
        print(f"Error connecting to AIShell socket: {e}")
    finally:
        client_socket.close()

if __name__ == "__main__":
    main()