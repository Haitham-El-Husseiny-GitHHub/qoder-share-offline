#!/usr/bin/env python3
"""Cancellable HTTP/MobSF subprocess; killed with the terminal process group."""
import json
import sys
from pathlib import Path

if __name__=='__main__':
    try:
        raw=sys.stdin.buffer.read(1_100_001)
        if len(raw)>1_100_000:raise ValueError('API request exceeds helper size limit.')
        request=json.loads(raw)
        if request['tool'] not in {'http','mobsf'}:raise ValueError('Unknown API helper operation.')
        from coding_runner import Workspace
        from tool_adapters import invoke
        config=request['config'];config['_api_worker']=True;config['remote']={'enabled':False}
        result=invoke(Workspace(Path(request['workspace']),False),request['tool'],request['operation'],request['inputs'],request['timeout'],config,allow_remote=False)
        print(json.dumps(result))
    except Exception as error:
        print(json.dumps({'success':False,'exit_code':1,'error':str(error),'artifacts':[]}));sys.exit(1)
