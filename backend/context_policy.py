"""Size Qoder's Q8 KV cache from local GGUF metadata and available phone RAM."""
import functools
import json
import math
from pathlib import Path
import struct

RESERVE_BYTES = 1024**3
COMPUTE_BYTES = 512*1024**2
MIN_CONTEXT = 2048
POLICY_VERSION = 2
FORMATS = {0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}

def _number(stream, fmt):
    size = struct.calcsize('<'+fmt)
    data = stream.read(size)
    if len(data) != size: raise ValueError('Truncated GGUF metadata.')
    return struct.unpack('<'+fmt, data)[0]

def _string(stream, keep):
    size = _number(stream, 'Q')
    if size > 16*1024**2: raise ValueError('Invalid GGUF string size.')
    if keep:
        data = stream.read(size)
        if len(data) != size: raise ValueError('Truncated GGUF string.')
        return data.decode('utf-8')
    stream.seek(size, 1)

def _value(stream, kind, keep=False):
    if kind == 8: return _string(stream, keep)
    if kind == 9:
        subtype, count = _number(stream,'I'), _number(stream,'Q')
        if count > 2_000_000 or subtype == 9: raise ValueError('Invalid GGUF array.')
        if subtype in FORMATS:
            stream.seek(count*struct.calcsize('<'+FORMATS[subtype]), 1)
        elif subtype == 8:
            for _ in range(count): _string(stream, False)
        else: raise ValueError('Unknown GGUF array type.')
        return None
    if kind not in FORMATS: raise ValueError('Unknown GGUF metadata type.')
    return _number(stream, FORMATS[kind])

@functools.lru_cache(maxsize=16)
def _metadata(filename, size, mtime):
    fields = {}
    with open(filename,'rb') as stream:
        if stream.read(4) != b'GGUF' or _number(stream,'I') not in (2,3):
            raise ValueError('Unsupported GGUF header.')
        _number(stream,'Q')
        count = _number(stream,'Q')
        if count > 100_000: raise ValueError('Invalid GGUF metadata count.')
        for _ in range(count):
            key = _string(stream,True)
            keep = key == 'general.architecture' or any(key.endswith('.'+suffix) for suffix in (
                'context_length','block_count','embedding_length','attention.head_count',
                'attention.head_count_kv','attention.key_length','attention.value_length','full_attention_interval'))
            value = _value(stream,_number(stream,'I'),keep)
            if keep: fields[key] = value
    return fields

def metadata(path):
    path = Path(path); stat = path.stat()
    return _metadata(str(path),stat.st_size,stat.st_mtime_ns).copy()

def memory_available():
    fields = {line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemAvailable:','MemTotal:'))}
    return fields.get('MemAvailable',fields.get('MemTotal',0))

def reclaimable_runtime(state_path):
    """Anonymous memory of Qoder's process; mmap file cache is already in MemAvailable."""
    try:
        state = json.loads(Path(state_path).read_text())
        proc = Path('/proc',str(int(state['pid'])))
        args = (proc/'cmdline').read_bytes().split(b'\0')
        if str(state['model_path']).encode() not in args or b'18082' not in args: return 0
        return int(next(line.split()[1] for line in (proc/'status').read_text().splitlines() if line.startswith('RssAnon:')))*1024
    except (OSError,ValueError,KeyError,StopIteration): return 0

def plan(path, parallel=2, available_bytes=None, reclaim_bytes=0):
    if parallel < 1: raise ValueError('Invalid parallel slot count.')
    fields = metadata(path); arch = fields.get('general.architecture')
    def integer(key, default=None):
        value = fields.get(str(arch)+'.'+key,default)
        if not isinstance(value,int) or value <= 0: raise ValueError('Missing GGUF context metadata: '+key)
        return value
    trained = integer('context_length'); layers = integer('block_count')
    heads = integer('attention.head_count'); kv_heads = integer('attention.head_count_kv',heads)
    embedding = integer('embedding_length')
    key = integer('attention.key_length',embedding//heads)
    value = integer('attention.value_length',embedding//heads)
    if arch == 'qwen35':
        # Hybrid Qwen3.5 keeps a token KV cache only on full-attention layers.
        interval = integer('full_attention_interval')
        layers = math.ceil(layers/interval)
    # q8_0 stores 32 elements plus a 2-byte scale. Allow 15% for padding/overheads.
    per_token = math.ceil(layers*kv_heads*(math.ceil(key/32)+math.ceil(value/32))*34*parallel*1.15)
    available = memory_available() if available_bytes is None else available_bytes
    weights = math.ceil(Path(path).stat().st_size*1.05)
    budget = max(0,available+reclaim_bytes-RESERVE_BYTES-COMPUTE_BYTES-weights)
    context = min(trained,(budget//per_token)//512*512)
    return {'context_window':context,'trained_context_window':trained,'parallel':parallel,
            'estimated_kv_bytes':context*per_token,'available_bytes':available,
            'reserved_bytes':RESERVE_BYTES,'fits':context>=MIN_CONTEXT,'policy_version':POLICY_VERSION}
