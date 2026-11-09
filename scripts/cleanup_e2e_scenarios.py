"""Back up identified browser-test projects, then delete only the frozen ID list."""
import argparse
import hashlib
import json
import re
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/project-cleanup/20261104'
BASE = 'http://127.0.0.1:8016/api/v1'
PATTERN = re.compile(r'(UI端到端|并行快照|另一项目|状态测试|参考交互|完整参考流程|删除和只读|标注验收|自动执行规模|日历验收|精密吊装空档填补验收|全局作业独占验收|资源弹窗简化核验) \d{13}')
DUPLICATE_256 = 'scenario:f72eb535-689f-4158-8018-382f670c9430'


def api(path, method='GET'):
    with urllib.request.urlopen(urllib.request.Request(BASE+path, method=method), timeout=60) as response:
        body = response.read()
        return json.loads(body) if body else None


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8')


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'manifest.json').exists():
        raise RuntimeError('Existing cleanup manifest retained')
    projects = api('/planner-scenarios')
    runs = api('/planner-runs')
    candidates = [p for p in projects if (PATTERN.fullmatch(p['name']) and p['activity_count'] <= 4)
                  or (p['name'] == '外部更名' and p['activity_count'] == 2)
                  or (p['id'] == DUPLICATE_256 and p['name'] == 'React 256 活动队列验收')]
    with ThreadPoolExecutor(max_workers=6) as pool:
        details = list(pool.map(lambda p: api('/planner-scenarios/'+p['id']), candidates))
    verified = []
    for p, detail in zip(candidates, details):
        s = detail['scenario']
        if p['name'] == '外部更名' and {a['name'] for a in s['activities']} != {'并行活动甲', '并行活动乙'}:
            continue
        if p['revision'] != detail['revision']:
            raise RuntimeError('Concurrent edit: '+p['id'])
        verified.append((p, detail))
    ids = {p['id'] for p, _ in verified}
    selected_runs = [r for r in runs if r['scenario_id'] in ids]
    assert not any(r.get('job_status') in ('QUEUED', 'RUNNING') for r in selected_runs), 'Active jobs retained'
    with ThreadPoolExecutor(max_workers=4) as pool:
        run_details = list(pool.map(lambda r: api('/planner-runs/'+r['id']), selected_runs))
    manifest = {'before_count': len(projects), 'delete_projects': [p for p, _ in verified],
                'delete_run_ids': [r['id'] for r in selected_runs],
                'retained_projects': [p for p in projects if p['id'] not in ids],
                'retained_run_ids': [r['id'] for r in runs if r['scenario_id'] not in ids]}
    backup = OUT / 'deleted-test-projects-backup.zip'
    with zipfile.ZipFile(backup, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', encode(manifest))
        for p, detail in verified:
            archive.writestr('scenarios/'+p['id'].split(':')[-1]+'.json', encode(detail))
        for r in run_details:
            archive.writestr('runs/'+r['id'].split(':')[-1]+'.json', encode(r))
    with zipfile.ZipFile(backup) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == 1 + len(verified) + len(selected_runs)
    manifest['backup_sha256'] = hashlib.sha256(backup.read_bytes()).hexdigest()
    (OUT / 'manifest.json').write_bytes(encode(manifest))
    print(json.dumps({'delete_projects': len(ids), 'delete_runs': len(selected_runs),
                      'retain': [p['name'] for p in manifest['retained_projects']], 'backup': str(backup)}, ensure_ascii=False))


def apply():
    manifest = json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    backup = OUT/'deleted-test-projects-backup.zip'
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == manifest['backup_sha256']
    projects = {p['id']: p for p in api('/planner-scenarios')}
    targets = manifest['delete_projects']
    ids = {p['id'] for p in targets}
    runs = api('/planner-runs')
    assert {r['id'] for r in runs if r['scenario_id'] in ids} == set(manifest['delete_run_ids']), 'Runs changed since backup'
    assert not any(r.get('job_status') in ('QUEUED', 'RUNNING') for r in runs if r['scenario_id'] in ids)
    for p in targets:
        assert projects[p['id']] == p, 'Project changed since backup: '+p['id']
    deleted = []
    for p in targets:
        api('/planner-scenarios/'+p['id'], method='DELETE')
        deleted.append(p['id'])
        (OUT/'deleted-ids.json').write_bytes(encode(deleted))
    remaining = api('/planner-scenarios')
    remaining_ids = {p['id'] for p in remaining}
    remaining_runs = api('/planner-runs')
    assert not (ids & remaining_ids)
    assert all(p['id'] in remaining_ids for p in manifest['retained_projects'])
    assert set(manifest['retained_run_ids']).issubset({r['id'] for r in remaining_runs})
    assert not any(r['scenario_id'] in ids for r in remaining_runs)
    result = {'deleted_projects': len(deleted), 'deleted_test_runs': len(manifest['delete_run_ids']),
              'remaining_projects': remaining, 'remaining_run_count': len(remaining_runs),
              'backup': str(backup), 'retained_history_verified': True}
    (OUT/'result.json').write_bytes(encode(result))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'apply'])
    args = parser.parse_args()
    {'prepare': prepare, 'apply': apply}[args.action]()
