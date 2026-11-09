"""Acceptance harness; sends writes only to the isolated deployment on 8026."""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
OUT = SOURCE / 'output/deploy-acceptance/final-validation'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deployment', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--check-persistence', action='store_true')
    parser.add_argument('--verify-busy-stop', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    deployed = args.deployment.resolve()
    assert Path(sys.prefix).resolve() == deployed / '.venv'
    assert Path(sys.base_prefix).resolve() == deployed / 'runtime/python'
    os.environ['PLANNER_PROJECT_PATH'] = str(deployed / 'solver')
    spec = importlib.util.spec_from_file_location('fixture_audit', SOURCE / 'scripts/verify_150_night_gap.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    audit.ROOT, audit.OUT, audit.BASE = deployed, out, 'http://127.0.0.1:8026/api/v1'
    out.mkdir(parents=True, exist_ok=True)
    caps = audit.api('/planner-runs/capabilities')
    assert Path(caps['planner_project_path']).resolve() == deployed / 'solver'
    if args.check_persistence:
        old = json.loads((out / 'result.json').read_text(encoding='utf-8'))
        assert audit.api('/planner-runs/' + old['id']) == old
        saved = json.loads((out / 'imported.json').read_text(encoding='utf-8'))
        current = audit.api('/planner-scenarios/' + saved['id'])
        assert current['revision'] == saved['revision']
        assert current['scenario'] == saved['scenario']
        audit.save('persistence.json', {'status': 'PASS', 'run_id': old['id'], 'scenario_id': saved['id']})
        print('PASS: scenario and immutable run survived deployment restart', flush=True)
        return
    assert not (out / 'submitted.json').exists(), 'Retain previous acceptance evidence'
    source = json.loads((SOURCE / 'output/fixtures/exclusive-calendar-150/imported.json').read_text(encoding='utf-8-sig'))
    scenario = source['scenario']
    scenario['name'] = '150活动部署验收｜独立数据库＋打包求解器'
    assert len(scenario['activities']) == 150
    assert scenario['work_calendar_id'] and scenario['night_lift_rule']['enabled']
    assert scenario['exclusive_rules'] == {'crane': True, 'commissioning': True}
    imported = audit.api('/planner-scenarios/import', {'scenario': scenario, 'preserve_ids': False})
    audit.save('imported.json', imported)
    scenario = imported['scenario']
    payload = {'scenario_id': imported['id'], 'expected_revision': imported['revision'],
               'current_state_ids': scenario['initial_state_ids'], 'target_state_ids': scenario['goal_state_ids'],
               'engine': 'JOINT_CP_SAT', 'execution_bound_mode': 'auto', 'budget_mode': 'auto',
               'seed': 11, 'client_request_id': str(uuid.uuid4()),
               'display_start_at': '2026-11-04T19:00:00+08:00', 'display_timezone': 'Asia/Shanghai'}
    audit.save('request.json', payload)
    run = audit.api('/planner-runs/async', payload)
    audit.save('submitted.json', run)
    assert audit.api('/planner-runs/async', payload)['id'] == run['id']
    print(json.dumps({'run_id': run['id'], 'activities': 150, 'status': 'SUBMITTED'}), flush=True)
    if args.verify_busy_stop:
        attempt = subprocess.run([sys.executable, str(deployed / 'deploy/scripts/deploy_runtime.py'), 'stop'],
                                 capture_output=True, text=True, timeout=30,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert attempt.returncode != 0 and 'Active solve jobs' in attempt.stderr, (attempt.stdout, attempt.stderr)
        audit.save('busy-stop.json', {'status': 'PASS', 'exit_code': attempt.returncode, 'message': attempt.stderr.strip()})
        print('PASS: stop refused while real solve was queued/running', flush=True)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        run = audit.api('/planner-runs/' + run['id'])
        if run['job_status'] in ('FINISHED', 'FAILED'):
            break
        time.sleep(2)
    audit.save('result.json', run)
    result = run['result']['results']['JOINT_CP_SAT']
    assert result['status'] == 'OPTIMAL', result
    assert result['paths'][0]['validator_status'] == 'VALID'
    assert result['paths'][0]['metrics']['makespan'] == 3033
    audit.audit()
    import ortools
    import planner_experiment
    paths = {'python_prefix': sys.prefix, 'python_base_prefix': sys.base_prefix,
             'ortools': ortools.__file__, 'solver': planner_experiment.__file__}
    assert all(Path(value).resolve().is_relative_to(deployed) for value in paths.values())
    audit.save('runtime-isolation.json', paths)
    print('PASS: packaged runtimes, real 150-activity solve, replay, capacity, calendar, night and exclusivity', flush=True)


if __name__ == '__main__':
    main()
