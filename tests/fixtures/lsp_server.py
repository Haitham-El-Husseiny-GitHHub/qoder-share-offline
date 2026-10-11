"""Protocol fixture: fragmented frames, server requests and diagnostics."""
import json
import sys

def send(payload):
    data=json.dumps({'jsonrpc':'2.0',**payload}).encode();frame=('Content-Length: %d\r\n\r\n'%len(data)).encode()+data
    for start in range(0,len(frame),13):sys.stdout.buffer.write(frame[start:start+13]);sys.stdout.buffer.flush()

while True:
    headers={}
    while True:
        line=sys.stdin.buffer.readline()
        if not line:raise SystemExit()
        if line==b'\r\n':break
        name,value=line.split(b':',1);headers[name.lower()]=value.strip()
    payload=json.loads(sys.stdin.buffer.read(int(headers[b'content-length'])))
    method=payload.get('method')
    if method=='initialize':
        send({'id':900,'method':'workspace/configuration','params':{'items':[{}]}})
        send({'id':payload['id'],'result':{'capabilities':{}}})
    elif method=='exit':raise SystemExit()
    elif method=='textDocument/didOpen':
        document=payload['params']['textDocument']
        if 'no-diagnostics' not in document['text']:
            send({'method':'textDocument/publishDiagnostics','params':{'uri':document['uri'],'diagnostics':[{'message':'observed diagnostic','severity':1,'range':{'start':{'line':0,'character':0},'end':{'line':0,'character':1}}}]}})
    elif method in {'textDocument/definition','textDocument/references'}:
        params=payload['params'];send({'id':payload['id'],'result':[{'uri':params['textDocument']['uri'],'range':{'start':params['position'],'end':params['position']}}]})
