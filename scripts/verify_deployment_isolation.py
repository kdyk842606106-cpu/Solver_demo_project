"""Read-only fingerprints of the original running system before/after deployment."""
import argparse
import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/deploy-acceptance'


def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8016'+path, timeout=20) as response:
        return json.load(response)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def capture():
    projects = get('/api/v1/planner-scenarios')
    runs = get('/api/v1/planner-runs')
    with ThreadPoolExecutor(max_workers=4) as pool:
        project_data = list(pool.map(lambda p: get('/api/v1/planner-scenarios/'+p['id']), projects))
        run_data = list(pool.map(lambda r: get('/api/v1/planner-runs/'+r['id']), runs))
    return {'projects': {p['id']: digest(p) for p in project_data}, 'runs': {r['id']: digest(r) for r in run_data},
            'health': get('/health'), 'env_sha256': hashlib.sha256((ROOT/'.env').read_bytes()).hexdigest(),
            'frontend': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (ROOT/'frontend/dist').rglob('*') if p.is_file()},
            'process_manifest': json.loads((ROOT/'output/react-cutover/processes.json').read_text(encoding='utf-8-sig'))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['before', 'after'])
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True, parents=True)
    state = capture()
    if args.action == 'before' and (OUT/'before.json').exists():
        raise RuntimeError('Original baseline already exists; do not overwrite')
    (OUT/f'{args.action}.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    if args.action == 'after':
        assert state == json.loads((OUT/'before.json').read_text()), 'Original system changed; inspect fingerprint differences'
    print(json.dumps({'phase': args.action, 'original_projects': len(state['projects']), 'original_runs': len(state['runs']),
                      'status': 'PASS', 'original_processes': state['process_manifest']}))
