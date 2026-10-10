"""Read-only, bounded health check for the phone's existing Termux/Rish bridge."""
import shutil, subprocess, threading, time
_lock = threading.Lock()
_cached = None
_checked = 0
def status():
    global _cached, _checked
    with _lock:
        if _cached is not None and time.monotonic() - _checked < 20:
            return dict(_cached)
        rish = shutil.which('rish')
        data = {'termux': True, 'rish_installed': bool(rish), 'rish_connected': False,
                'access_level': 'offline', 'private_app_data': False, 'checked_at': time.time(), 'detail': 'Rish is not installed in Termux.'}
        if rish:
            try:
                result = subprocess.run([rish, '-c', "id && printf '\nQODER_BRIDGE_OK\n'"], capture_output=True,
                                        text=True, timeout=3)
                data['rish_connected'] = (result.returncode == 0 or 'QODER_BRIDGE_OK' in result.stdout) and any(x in result.stdout for x in ('uid=2000(', 'uid=0('))
                data['access_level'] = 'root' if data['rish_connected'] and 'uid=0(' in result.stdout else 'shell' if data['rish_connected'] else 'offline'
                data['private_app_data'] = data['access_level'] == 'root'
                data['detail'] = 'Shizuku shell connected' if data['rish_connected'] else 'Start Shizuku and authorize Termux. ' + (result.stderr or result.stdout).strip()[:300]
            except subprocess.TimeoutExpired:
                data['detail'] = 'Shizuku connection timed out; check Shizuku.'
            except OSError:
                data['detail'] = 'Rish could not start; check its Termux installation.'
        _cached, _checked = data, time.monotonic()
        return dict(data)
