#!/usr/bin/env python3
from __future__ import annotations
import os, re, sys
from pathlib import Path

ROOT = Path(os.environ.get('FBAW_DSH_WORKDIR', r'D:\AI_Research\dsh-run'))

def candidates(root: Path):
    direct = [
        root/'node_modules'/'@deepseek-ai'/'dsh-base'/'cordis.patch.yml',
        root/'node_modules'/'.pnpm'/'node_modules'/'@deepseek-ai'/'dsh-base'/'cordis.patch.yml',
    ]
    seen=set()
    for p in direct:
        if p.exists() and p not in seen:
            seen.add(p); yield p
    pnpm=root/'node_modules'/'.pnpm'
    if pnpm.exists():
        for p in pnpm.glob('@deepseek-ai+dsh-base@*/node_modules/@deepseek-ai/dsh-base/cordis.patch.yml'):
            if p not in seen:
                seen.add(p); yield p
        for p in pnpm.glob('@deepseek-ai+dsh@*/node_modules/@deepseek-ai/dsh-base/cordis.patch.yml'):
            if p not in seen:
                seen.add(p); yield p

def parse_default(path: Path):
    text=path.read_text(encoding='utf-8', errors='replace')
    # Restrict parsing to the agent-default-model block so unrelated providers/models do not win.
    m=re.search(r"(?ms)^\s*- id:\s*agent-default-model\s*$.*?(?=^\s*- id:|\Z)", text)
    block=m.group(0) if m else text
    pm=re.search(r"(?m)^\s*provider:\s*['\"]?([^'\"#\s]+)", block)
    mm=re.search(r"(?m)^\s*model:\s*['\"]?([^'\"#\s]+)", block)
    return (pm.group(1) if pm else None, mm.group(1) if mm else None)

def main():
    # Explicit overrides, if supplied by the launcher/user, take precedence.
    provider=os.environ.get('FBAW_DSH_PROVIDER_OVERRIDE','').strip()
    model=os.environ.get('FBAW_DSH_MODEL_OVERRIDE','').strip()
    source='explicit FBAW_DSH_*_OVERRIDE environment'
    config_path=''
    if not (provider and model):
        for p in candidates(ROOT):
            pr, mo=parse_default(p)
            if pr and mo:
                provider, model, config_path = pr, mo, str(p)
                source='DSH agent-default-model configuration'
                break
    if not (provider and model):
        print('DSH_MODEL_DETECTION=FAIL')
        print('Could not resolve DSH agent-default-model provider/model.', file=sys.stderr)
        return 2
    print(f'DSH_PROVIDER={provider}')
    print(f'DSH_MODEL={model}')
    print(f'DSH_MODEL_SOURCE={source}')
    if config_path: print(f'DSH_MODEL_CONFIG={config_path}')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
