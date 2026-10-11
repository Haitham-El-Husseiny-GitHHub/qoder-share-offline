#!/usr/bin/env python3
"""Qoder's independent offline coding CLI."""
import argparse,json
from pathlib import Path
from runtime_controller import start
from runtime_config import CODING_ROUTES
from coding_runner import run
if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Independent offline coding agent; zero Qoder credits, no hosted fallback.')
    parser.add_argument('--workspace',help='Existing project folder')
    parser.add_argument('--objective',help='File change or test objective')
    parser.add_argument('--resume',help='Interrupted/stopped job ID from its operation history')
    parser.add_argument('--profile',choices=['BUILD','FIX','VERIFY','REVIEW','AUDIT'],default='BUILD')
    parser.add_argument('--model',choices=list(CODING_ROUTES),default='coding')
    args=parser.parse_args()
    if args.resume:
        import re
        from runtime_config import ROOT
        if not re.fullmatch(r'[0-9a-f]{32}',args.resume):parser.error('Invalid recovery job ID.')
        saved=json.loads((ROOT/'jobs'/(args.resume+'.journal.json')).read_text())
        args.workspace=saved['target'];args.objective=saved['objective'];args.profile=saved['profile']
    if not args.workspace or not args.objective:parser.error('Choose --workspace and --objective, or --resume JOB_ID.')
    workspace=Path(args.workspace).resolve(strict=True)
    if not workspace.is_dir() or not args.objective.strip():parser.error('Choose a project directory and enter an objective.')
    route=CODING_ROUTES[args.model]
    start(route)
    print(json.dumps(run({'workspace':str(workspace),'objective':args.objective,'profile':args.profile,'route':route,'resume_from':args.resume}),indent=2))
