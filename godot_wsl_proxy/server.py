import io
import logging
import re
import select
import socket
import sys

logger = logging.getLogger("proxy")
wsl_file_re = re.compile(r"['\"](\\/mnt\\/.+?)['\"]")
wsl_uri_re = re.compile(r"['\"](file:\\/\\/\\/mnt\\/.+?)['\"]")

windows_uri_re = re.compile(r"['\"](file:///[A-Z]:/.+?)['\"]")
windows_file_re = re.compile(r"['\"]([A-Z]:/.+?)['\"]")


class SocketReader:
    def __init__(self, reader: io.IOBase) -> None:
        self._reader = reader

    def read(self) -> str:
        content_len = self._reader.readline().strip()
        if not content_len.startswith(b"Content-Length: "):
            raise ValueError("Something went wrong with a socket")
        self._reader.readline()
        number = content_len[16:]
        size = int(number)
        data = b""
        while size > 0:
            portion = self._reader.read(size)
            size -= len(portion)
            data += portion
        logger.debug("RECEIVING REQUEST: %s\\r\\n\\r\\n%s", content_len, data)
        return data.decode()


class SocketWriter:
    def __init__(self, writer: io.IOBase) -> None:
        self._writer = writer

    def write(self, data: str) -> None:
        bin_data = data.encode()
        length = len(bin_data)
        full_data = b"Content-Length: " + str(length).encode() + b"\r\n\r\n" + bin_data
        logger.debug("WRITING REQUEST: %s", full_data)
        self._writer.write(full_data)
        self._writer.flush()


class StreamReader:
    def __init__(self, stdin: io.TextIOBase) -> None:
        self._stdin = stdin

    def read(self) -> str:
        content_len = self._stdin.readline().strip()
        if not content_len.startswith("Content-Length: "):
            raise ValueError("Something went wrong with a socket")
        self._stdin.readline()
        number = content_len[16:]
        size = int(number)
        data = ""
        while size > 0:
            portion = self._stdin.read(size)
            size -= len(portion)
            data += portion
        logger.debug("STDIN REQUEST: %s", data)
        return data


class StreamWriter:
    def __init__(self, stdout: io.TextIOBase) -> None:
        self._stdout = stdout

    def write(self, data: str) -> None:
        length = len(data.encode())
        full_data = "Content-Length: " + str(length) + "\r\n\r\n" + data
        logger.debug("STDOUT RESPONSE: %s", full_data)
        self._stdout.write(full_data)
        self._stdout.flush()


def wsl_to_windows_uri(wsl_uri: str) -> str:
    prefix = "file:\\/\\/"
    wsl_path = wsl_uri[len(prefix) :]
    windows_path = wsl_to_windows_path(wsl_path)
    return "file:///" + windows_path


def wsl_to_windows_path(wsl_path: str, slash="/") -> str:
    parts = re.split(r"\\/", wsl_path)
    drive_letter = parts[2].upper() + ":"
    windows_path = slash.join(parts[3:])
    return drive_letter + slash + windows_path


def windows_to_wsl_uri(windows_uri: str) -> str:
    prefix = "file:///"
    windows_path = windows_uri[len(prefix) :]
    wsl_path = windows_to_wsl_path(windows_path)
    return f"file://{wsl_path}"


def windows_to_wsl_path(windows_path: str) -> str:
    drive_letter = windows_path[0].lower()  # Get the drive letter (e.g., 'C' -> 'c')
    remaining_path = windows_path[3:]  # Skip the colon and backslash after the drive letter
    wsl_path = remaining_path.replace("\\", "/")
    # Construct the WSL path
    return f"/mnt/{drive_letter}/{wsl_path}"


def read_full_data(reader: io.IOBase) -> str:
    content_len = reader.readline().strip()
    if not content_len.startswith(b"Content-Length: "):
        raise ValueError("Something went wrong with a socket")
    reader.readline()
    number = content_len[16:]
    size = int(number)
    data = b""
    while size > 0:
        portion = reader.read(size)
        size -= len(portion)
        data += portion
    logger.debug("RECEIVING REQUEST: %s\\r\\n\\r\\n%s", content_len, data)
    return data.decode()


def write_full_data(writer: io.IOBase, data: str) -> None:
    bin_data = data.encode()
    length = len(bin_data)
    full_data = b"Content-Length: " + str(length).encode() + b"\r\n\r\n" + bin_data
    logger.debug("WRITING REQUEST: %s", full_data)
    writer.write(full_data)
    writer.flush()


class Application:
    def __init__(self, lsp_host: str, lsp_port: int) -> None:
        self._lsp_host = lsp_host
        self._lsp_port = lsp_port

    def handle_linux_to_windows(self, data: str) -> str:
        for match in wsl_uri_re.finditer(data):
            source_text = match.group(0)
            source_path = match.group(1)
            target_path = wsl_to_windows_uri(source_path)
            target_text = source_text.replace(source_path, target_path)
            data = data.replace(source_text, target_text)
        for match in wsl_file_re.finditer(data):
            source_text = match.group(0)
            source_path = match.group(1)
            target_path = wsl_to_windows_path(source_path)
            target_text = source_text.replace(source_path, target_path)
            data = data.replace(source_text, target_text)
        return data

    def handle_windows_to_linux(self, data: str) -> str:
        for match in windows_uri_re.finditer(data):
            source_text = match.group(0)
            source_path = match.group(1)
            target_path = windows_to_wsl_uri(source_path)
            target_text = source_text.replace(source_path, target_path)
            data = data.replace(source_text, target_text)
        for match in windows_file_re.finditer(data):
            source_text = match.group(0)
            source_path = match.group(1)
            target_path = windows_to_wsl_path(source_path)
            target_text = source_text.replace(source_path, target_path)
            data = data.replace(source_text, target_text)
        return data

    def socket_server(self, host: str, port: int) -> None:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((host, port))
        server_sock.listen()
        try:
            while True:
                client_sock, _client_addr = server_sock.accept()
                proxy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    proxy_sock.connect((self._lsp_host, self._lsp_port))
                except:
                    client_sock.close()
                    continue
                client_reader = SocketReader(client_sock.makefile("rb", buffering=0))
                client_writer = SocketWriter(client_sock.makefile("wb", buffering=0))
                proxy_reader = SocketReader(proxy_sock.makefile("rb", buffering=0))
                proxy_writer = SocketWriter(proxy_sock.makefile("wb", buffering=0))
                operations = {}
                operations[client_sock] = (client_reader, proxy_writer, self.handle_linux_to_windows)
                operations[proxy_sock] = (proxy_reader, client_writer, self.handle_windows_to_linux)
                inputs = list(operations.keys())
                try:
                    while True:
                        rlist, _wlist, _xlist = select.select(inputs, [], [])
                        for sock in rlist:
                            reader, writer, handler = operations[sock]
                            logger.debug("READING")
                            data - reader.read()
                            logger.debug("TRANSFORMING")
                            data = handler(data)
                            logger.debug("WRITING")
                            writer.write(data)
                except ValueError:
                    pass
                finally:
                    logger.warning("CLOSING CLIENT/PROXY CONNECTION")
                    client_sock.close()
                    proxy_sock.close()
        finally:
            server_sock.close()

    def stdin_server(self) -> None:
        proxy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            proxy_sock.connect((self._lsp_host, self._lsp_port))
        except:
            sys.exit(1)
        client_reader = StreamReader(sys.stdin)
        client_writer = StreamWriter(sys.stdout)
        proxy_reader = SocketReader(proxy_sock.makefile("rb", buffering=0))
        proxy_writer = SocketWriter(proxy_sock.makefile("wb", buffering=0))
        operations = {}
        operations[sys.stdin] = (client_reader, proxy_writer, self.handle_linux_to_windows)
        operations[proxy_sock] = (proxy_reader, client_writer, self.handle_windows_to_linux)
        inputs = list(operations.keys())
        try:
            while True:
                rlist, _wlist, _xlist = select.select(inputs, [], [])
                for sock in rlist:
                    reader, writer, handler = operations[sock]
                    logger.debug("READING")
                    data = reader.read()
                    logger.debug("TRANSFORMING")
                    data = handler(data)
                    logger.debug("WRITING")
                    writer.write(data)
        except ValueError:
            pass
        finally:
            logger.warning("CLOSING PROXY CONNECTION")
            proxy_sock.close()
