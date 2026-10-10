#!/usr/bin/env python3
"""Qoder's independent offline coding CLI."""
import argparse,json
from pathlib import Path
from runtime_controller import start
from runtime_config import CODING_ROUTES
from coding_runner import run
if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Independent offline coding agent; zero Qoder credits, no hosted fallback.')
    parser.add_argument('--workspace',required=True,help='Existing project folder')
    parser.add_argument('--objective',required=True,help='File change or test objective')
    parser.add_argument('--profile',choices=['BUILD','FIX','VERIFY','REVIEW','AUDIT'],default='BUILD')
    parser.add_argument('--model',choices=list(CODING_ROUTES),default='coding')
    args=parser.parse_args()
    workspace=Path(args.workspace).resolve(strict=True)
    if not workspace.is_dir() or not args.objective.strip():parser.error('Choose a project directory and enter an objective.')
    route=CODING_ROUTES[args.model]
    start(route)
    print(json.dumps(run({'workspace':str(workspace),'objective':args.objective,'profile':args.profile,'route':route}),indent=2))
