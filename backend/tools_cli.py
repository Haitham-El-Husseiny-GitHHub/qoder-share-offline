#!/usr/bin/env python3
"""Inspect or invoke the adapter contract independently of model quality."""
import argparse
import json
from pathlib import Path
from tool_catalog import discover,load_config,public_capabilities

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace')
    parser.add_argument('--objective')
    parser.add_argument('--profile',default='BUILD',choices=['BUILD','FIX','VERIFY','REVIEW','AUDIT'])
    parser.add_argument('--invoke',nargs=2,metavar=('TOOL','OPERATION'))
    parser.add_argument('--inputs',default='{}')
    parser.add_argument('--timeout',type=int,default=120)
    args=parser.parse_args()
    config=load_config()
    try:
        if args.invoke:
            if not args.workspace:parser.error('--invoke requires --workspace')
            from coding_runner import Workspace
            from tool_adapters import invoke
            result=invoke(Workspace(Path(args.workspace),args.profile in {'REVIEW','AUDIT'}),*args.invoke,json.loads(args.inputs),args.timeout,config)
        elif args.objective:
            if not args.workspace:parser.error('--objective requires --workspace')
            from task_router import select
            result=select(args.workspace,args.objective,args.profile,discover(config),config)
        else:result=public_capabilities(discover(config))
        print(json.dumps(result,indent=2))
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'success':False,'error':str(exc)}));raise SystemExit(1)
