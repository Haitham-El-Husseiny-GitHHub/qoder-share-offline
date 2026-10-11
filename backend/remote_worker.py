#!/usr/bin/env python3
"""Install backend/ on a trusted build host; no model or HTTP service required."""
import argparse
import json
import os
import re
import signal
import sys
from pathlib import Path

from tool_catalog import discover, load_config, public_capabilities


def root():
    value = os.environ.get('QODER_REMOTE_ROOT')
    if not value:
        raise ValueError('Set QODER_REMOTE_ROOT to a private remote jobs directory.')
    path = Path(value).resolve()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def workspace(identifier, create=False):
    if not re.fullmatch(r'[0-9a-f]{32}', identifier):
        raise ValueError('Invalid remote job identifier.')
    target = root() / identifier
    if create:
        target.mkdir(mode=0o700)
    elif not target.is_dir() or target.is_symlink():
        raise ValueError('Remote workspace does not exist.')
    return target


def main(args):
    if args.capabilities:
        return public_capabilities(discover(device=False))
    if args.prepare:
        return {'workspace': str(workspace(args.prepare, True))}
    if args.cancel:
        target = workspace(args.cancel)
        (target / '.cancel').touch(mode=0o600)
        return {'cancel_requested': True}
    raw = sys.stdin.buffer.read(64001)
    if len(raw) > 64000:
        raise ValueError('Remote request exceeds limit.')
    request = json.loads(raw)
    target = workspace(request['id'])
    from coding_runner import Workspace, Cancelled
    from tool_adapters import invoke
    stopped = False
    def on_stop(signum, frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, on_stop)
    signal.signal(signal.SIGHUP, on_stop)
    def cancel():
        if stopped or (target / '.cancel').exists():
            raise Cancelled('Remote operation cancelled.')
    ws = Workspace(target, False, cancel=cancel)
    config = load_config()
    config['remote'] = {'enabled': False}
    if request['tool'] in {'adb', 'rish', 'apksigner', 'bundletool', 'zipalign', 'http'}:
        raise ValueError('Device, signing and direct HTTP operations stay on the phone.')
    return invoke(ws, request['tool'], request['operation'], request.get('inputs', {}), request.get('timeout', 120), config, allow_remote=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--capabilities', action='store_true')
    group.add_argument('--prepare')
    group.add_argument('--cancel')
    group.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(main(args)))
    except Exception as error:
        print(json.dumps({'success': False, 'error': str(error)}))
        sys.exit(1)
