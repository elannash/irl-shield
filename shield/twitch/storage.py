"""Explicit opt-in OS credential storage; never use a plaintext fallback."""
import json

from .auth import SCOPES, Tokens, Secret, TwitchError, approved_scopes


class TokenStore:
    def __init__(self, backend=None):
        if backend is None:
            import keyring
            backend = keyring.get_keyring()
            qualified = type(backend).__module__ + '.' + type(backend).__name__
            if qualified not in {'keyring.backends.SecretService.Keyring', 'keyring.backends.macOS.Keyring',
                                 'keyring.backends.Windows.WinVaultKeyring'}:
                raise TwitchError('secure OS keyring unavailable')
        self.backend = backend

    def save(self, client_id, broadcaster_id, tokens, *, remember=False):
        if remember is not True:
            return
        try:
            self.backend.set_password('irl-shield-twitch:' + client_id, broadcaster_id,
                json.dumps({'access': tokens.access.reveal(), 'refresh': tokens.refresh.reveal(),
                            'scopes': list(SCOPES)}))
        except Exception:
            raise TwitchError('OS keyring write failed') from None

    def load(self, client_id, broadcaster_id):
        try:
            raw = self.backend.get_password('irl-shield-twitch:' + client_id, broadcaster_id)
            if raw is None:
                return None
            data = json.loads(raw)
            if not isinstance(data, dict) or not approved_scopes(data.get('scopes')):
                raise ValueError
            # Monotonic deadlines cannot survive a process; refresh on load.
            return Tokens(Secret(data['access']), Secret(data['refresh']), 0)
        except Exception:
            raise TwitchError('OS keyring read failed') from None


def owner_terminal_prompt(prompt):
    """Call from an attended owner terminal only, never a captured T3 command.

    /dev/tty bypasses stdout/stderr capture. No browser subprocess argv carries
    the code, and the adapter never writes a file with it.
    """
    try:
        with open('/dev/tty', 'w') as terminal:
            if not terminal.isatty():
                raise TwitchError('owner terminal required')
            terminal.write('Open this activation URL privately: ' + prompt.uri.reveal() + '\n')
            terminal.flush()
    except OSError:
        raise TwitchError('owner terminal required') from None
