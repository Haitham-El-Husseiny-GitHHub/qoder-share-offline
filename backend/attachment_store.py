"""Bounded, streamed imports of user-selected files into an existing workspace."""
import hashlib
import mimetypes
import os
from pathlib import Path
import re
import shutil
import uuid

MAX_BYTES=256*1024*1024
TEXT_SUFFIXES={'.txt','.md','.py','.js','.ts','.json','.xml','.yaml','.yml','.java','.kt','.c','.cpp','.h','.css','.html','.csv','.log','.smali'}

def store(workspace,name,stream,length,allowed_roots):
    root=Path(workspace).resolve(strict=True)
    if not root.is_dir() or not any(root.is_relative_to(Path(base).resolve()) for base in allowed_roots):raise ValueError('Choose an existing project folder.')
    if not isinstance(length,int) or not 0<=length<=MAX_BYTES:raise ValueError('File limit is 256 MB.')
    if not isinstance(name,str) or not name or name in {'.','..'} or '/' in name or '\\' in name or any(ord(c)<32 for c in name):raise ValueError('Invalid file name.')
    if name.startswith('.') or re.search(r'(?i)(\.env|\.pem|\.key|\.keystore|\.jks)$',name):raise ValueError('Private configuration and signing keys cannot be attached.')
    # Ignore supplied paths, create a unique directory, and never overwrite source.
    safe=re.sub(r'[^\w. ()+-]','_',name)[:120]
    base=root/'attachments'
    if base.is_symlink():raise ValueError('Attachment folder must not be a symlink.')
    base.mkdir(mode=0o700,exist_ok=True)
    folder=base/uuid.uuid4().hex;folder.mkdir(mode=0o700)
    target=folder/safe;digest=hashlib.sha256();remaining=length
    try:
        with target.open('xb') as output:
            os.chmod(target,0o600)
            while remaining:
                block=stream.read(min(65536,remaining))
                if not block:raise ValueError('Incomplete attachment transfer.')
                output.write(block);digest.update(block);remaining-=len(block)
            output.flush();os.fsync(output.fileno())
        suffix=target.suffix.lower()
        kind='image' if suffix in {'.png','.jpg','.jpeg','.webp','.gif','.bmp'} else 'apk' if suffix in {'.apk','.aab','.apks','.xapk'} else 'text' if suffix in TEXT_SUFFIXES else 'file'
        return {'name':safe,'path':str(target.relative_to(root)),'size':length,'sha256':digest.hexdigest(),'kind':kind,'mime':mimetypes.guess_type(safe)[0] or 'application/octet-stream'}
    except BaseException:
        shutil.rmtree(folder);raise
