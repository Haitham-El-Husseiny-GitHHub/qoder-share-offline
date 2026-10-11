"""Bounded stdio JSON-RPC language-server adapter; servers cannot apply edits."""
import json
import os
import selectors
import signal
import subprocess
import tempfile
import time
import urllib.parse

EXTENSIONS = {'.py': 'python', '.ts': 'typescript', '.tsx': 'typescript', '.js': 'javascript', '.jsx': 'javascript',
              '.c': 'c', '.h': 'c', '.cpp': 'cpp', '.cc': 'cpp', '.hpp': 'cpp', '.java': 'java', '.kt': 'kotlin', '.rs': 'rust'}


class Client:
    def __init__(self, command, root, cancel=None, timeout=30):
        self.stderr = tempfile.TemporaryFile()
        self.proc = subprocess.Popen(command, cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.stderr, start_new_session=True)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        self.buffer = b''
        self.deadline = time.monotonic() + timeout
        self.cancel = cancel
        self.counter = 0
        self.notifications = []

    def send(self, payload):
        data = json.dumps({'jsonrpc': '2.0', **payload}).encode()
        self.proc.stdin.write(('Content-Length: %d\r\n\r\n' % len(data)).encode() + data)
        self.proc.stdin.flush()

    def receive(self):
        while True:
            if self.cancel:
                self.cancel()
            if time.monotonic() >= self.deadline:
                raise TimeoutError('Language server did not return a verified result before the deadline.')
            header_end = self.buffer.find(b'\r\n\r\n')
            if header_end >= 0:
                if header_end > 8192:
                    raise ValueError('Language-server header exceeded limit.')
                headers = dict(line.split(b':', 1) for line in self.buffer[:header_end].split(b'\r\n'))
                length = int(next(v.strip() for k, v in headers.items() if k.lower() == b'content-length'))
                if not 0 <= length <= 4_000_000:
                    raise ValueError('Language-server message exceeded limit.')
                start = header_end + 4
                if len(self.buffer) >= start + length:
                    payload = json.loads(self.buffer[start:start + length])
                    self.buffer = self.buffer[start + length:]
                    return payload
            elif len(self.buffer) > 8192:
                raise ValueError('Invalid language-server framing.')
            if self.selector.select(.1):
                chunk = os.read(self.proc.stdout.fileno(), 65536)
                if not chunk:
                    raise ValueError('Language server disconnected before returning a result.')
                self.buffer += chunk

    def handle(self, payload):
        if 'method' in payload and 'id' in payload:
            method = payload['method']
            if method == 'workspace/configuration':
                result = [{} for _ in payload.get('params', {}).get('items', [])]
            elif method == 'workspace/applyEdit':
                result = {'applied': False, 'failureReason': 'Use Qoder checked patch editing.'}
            else:
                result = None
            self.send({'id': payload['id'], 'result': result})
        elif 'method' in payload:
            self.notifications.append(payload)
            self.notifications = self.notifications[-100:]

    def request(self, method, params):
        self.counter += 1
        request_id = self.counter
        self.send({'id': request_id, 'method': method, 'params': params})
        while True:
            payload = self.receive()
            if payload.get('id') == request_id and 'method' not in payload:
                if payload.get('error'):
                    raise ValueError('Language-server error: ' + json.dumps(payload['error']))
                return payload.get('result')
            self.handle(payload)

    def close(self):
        if self.proc.poll() is None:
            try:
                self.send({'method': 'exit'})
                self.proc.wait(timeout=.5)
            except (OSError, subprocess.TimeoutExpired):
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait()
        self.selector.close()
        self.proc.stdin.close()
        self.proc.stdout.close()
        self.stderr.close()


def invoke(ws, operation, inputs, config, timeout):
    path = ws.file(inputs['path'])
    language = EXTENSIONS.get(path.suffix)
    command = config.get('language_servers', {}).get(language)
    if not command:
        raise ValueError('Configure a stdio language server for ' + str(language) + ' in tools.json.')
    if path.stat().st_size > 1_000_000:
        raise ValueError('Language-server input exceeds size limit.')
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
        raise ValueError('Language server command must be a string argv array.')
    client = Client(command, ws.root, ws.cancel, min(timeout, 60))
    try:
        initialize = client.request('initialize', {'processId': os.getpid(), 'rootUri': ws.root.as_uri(),
                        'capabilities': {'textDocument': {'publishDiagnostics': {}, 'definition': {}, 'references': {}}},
                        'workspaceFolders': [{'uri': ws.root.as_uri(), 'name': ws.root.name}]})
        client.send({'method': 'initialized', 'params': {}})
        uri = path.as_uri()
        client.send({'method': 'textDocument/didOpen', 'params': {'textDocument': {'uri': uri, 'languageId': language,
                            'version': 1, 'text': path.read_text()}}})
        if operation in {'definition', 'references'}:
            line, column = inputs.get('line', 1), inputs.get('column', 1)
            if not isinstance(line, int) or not isinstance(column, int) or min(line, column) < 1:
                raise ValueError('line and column are positive, one-based integers.')
            params = {'textDocument': {'uri': uri}, 'position': {'line': line - 1, 'character': column - 1}}
            if operation == 'references':
                params['context'] = {'includeDeclaration': True}
            result = client.request('textDocument/' + operation, params)
            return {'exit_code': 0, 'success': True, 'locations': result, 'position_encoding': 'utf-16', 'diagnostics': [], 'artifacts': []}
        if operation != 'diagnostics':
            raise ValueError('Use definition, references or diagnostics.')
        if initialize.get('capabilities', {}).get('diagnosticProvider'):
            result = client.request('textDocument/diagnostic', {'textDocument': {'uri': uri}})
            diagnostics = result.get('items', [])
        else:
            while True:
                event = next((n for n in client.notifications if n.get('method') == 'textDocument/publishDiagnostics' and n.get('params', {}).get('uri') == uri), None)
                if event:
                    diagnostics = event['params'].get('diagnostics', [])
                    break
                client.handle(client.receive())
        return {'exit_code': 0, 'success': True, 'path': str(path.relative_to(ws.root)), 'diagnostics': diagnostics[:100], 'artifacts': []}
    finally:
        client.close()
