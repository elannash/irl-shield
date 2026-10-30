"""Socket-level fail guard: synthetic tests may connect only to IPv4 loopback."""
import socket
from contextlib import ExitStack, contextmanager
from unittest.mock import patch


@contextmanager
def local_network():
    connect, connect_ex, resolve = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo
    def check(address):
        if isinstance(address, tuple) and address[0] != '127.0.0.1':
            raise AssertionError('nonlocal test connection refused')
    def guarded_connect(sock, address):
        check(address)
        return connect(sock, address)
    def guarded_connect_ex(sock, address):
        check(address)
        return connect_ex(sock, address)
    def guarded_resolve(host, *args, **kwargs):
        if host != '127.0.0.1':
            raise AssertionError('nonlocal test DNS refused')
        return resolve(host, *args, **kwargs)
    with ExitStack() as stack:
        stack.enter_context(patch.object(socket.socket, 'connect', guarded_connect))
        stack.enter_context(patch.object(socket.socket, 'connect_ex', guarded_connect_ex))
        stack.enter_context(patch.object(socket, 'getaddrinfo', guarded_resolve))
        yield
