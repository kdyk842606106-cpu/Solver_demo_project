"""Owned, offline Windows deployment. Never attaches to an existing database."""
import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.deployment'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


@contextmanager
def deployment_lock():
    import msvcrt
    with (ROOT/'.deployment.lock').open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('Another deployment command is running in this directory') from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def owned_path(path, root=None):
    path, root = Path(path).resolve(), Path(root or ROOT).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError('Managed path is outside this installation')
    return path


def port_free(port):
    with socket.socket() as sock:
        if os.name == 'nt':
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def command(args, env=None, input=None, log=None):
    if log:
        # PostgreSQL descendants can retain inherited stdout pipe handles on
        # Windows. A real log file lets us wait for pg_ctl itself, not EOF from
        # the long-lived database server.
        with log.open('w', encoding='utf-8') as output:
            result = subprocess.run([str(a) for a in args], cwd=ROOT, env=env, input=input,
                                    text=True, encoding='utf-8', errors='replace', stdout=output,
                                    stderr=subprocess.STDOUT, creationflags=NO_WINDOW, timeout=600)
    else:
        result = subprocess.run([str(a) for a in args], cwd=ROOT, env=env, input=input,
                                text=True, encoding='utf-8', errors='replace', capture_output=True,
                                creationflags=NO_WINDOW, timeout=60)
    if result.returncode:
        # Commands can contain SQL passwords on stdin, never print their input.
        raise RuntimeError(f'{Path(args[0]).name} failed ({result.returncode}); see {log or "deployment logs"}')
    return result.stdout or ''


def env_for(config):
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'DATABASE_URL', 'DATABASE_URL_SYNC', 'APP_COMMIT', 'APP_VERSION', 'RELEASE_ID'):
        env.pop(key, None)
    version = load(ROOT/'VERSION.json')
    env.update(DB_HOST='127.0.0.1', DB_PORT=str(config['db_port']), DB_NAME='planner', DB_USER='planner_app',
               DB_PASSWORD=config['app_password'], DB_CONNECT_TIMEOUT='5',
               PLANNER_PROJECT_PATH=str(ROOT/'solver'), PYTHONIOENCODING='utf-8', PYTHONUTF8='1',
               PYTHONNOUSERSITE='1', APP_ENV='production', DEBUG='false',
               APP_VERSION=version['app_version'], APP_COMMIT=version['app_commit'], RELEASE_ID=version['release_id'])
    return env


def request(config, path, body=None, method=None):
    url = f"http://127.0.0.1:{config['api_port']}"+path
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read()
            return json.loads(data) if data else None
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'API {path}: HTTP {exc.code}: {exc.read().decode("utf-8", errors="replace")}') from exc


def process_info(pid):
    script = f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {int(pid)}' -ErrorAction SilentlyContinue; if($p){{$p | Select-Object ProcessId,CommandLine,CreationDate | ConvertTo-Json -Compress}}"
    value = command(['powershell', '-NoProfile', '-Command', script]).strip()
    return json.loads(value) if value else None


def is_our_process(record):
    if not record:
        return False
    info = process_info(record['pid'])
    if not info:
        return False
    line = (info.get('CommandLine') or '').lower()
    return (str(ROOT).lower() in line and record['marker'].lower() in line
            and info.get('CreationDate') == record.get('created'))


def stop_process(record):
    if not record or not is_our_process(record):
        return  # A reused PID or foreign process must never be stopped.
    pid = int(record['pid'])
    # Resolve descendants in one shell, and only after verifying the root's
    # full installation path, command marker and process creation timestamp.
    script = f"""$all=@(Get-CimInstance Win32_Process); function Stop-Tree([int]$processIdToStop) {{
      foreach($child in $all | Where-Object {{$_.ParentProcessId -eq $processIdToStop}}) {{Stop-Tree $child.ProcessId}}
      Stop-Process -Id $processIdToStop -ErrorAction SilentlyContinue
    }}; Stop-Tree {pid}"""
    command(['powershell', '-NoProfile', '-Command', script])


def start_process(args, marker, env, name):
    with (STATE/'logs'/f'{name}.out.log').open('ab') as out, (STATE/'logs'/f'{name}.err.log').open('ab') as err:
        process = subprocess.Popen([str(a) for a in args], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                   stdout=out, stderr=err, creationflags=NO_WINDOW | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    info = process_info(process.pid)
    if not info:
        raise RuntimeError(f'{name} exited during startup; inspect logs')
    return {'pid': process.pid, 'created': info['CreationDate'], 'marker': marker}


def verify_manifest():
    for relative, digest in load(ROOT/'MANIFEST.json').items():
        path = owned_path(ROOT/relative)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Package checksum mismatch: '+relative)


def pg_tool(name):
    return ROOT/'runtime/postgresql/bin'/f'{name}.exe'


def pg_env(config, admin=True):
    env = env_for(config)
    env.update(PGHOST='127.0.0.1', PGPORT=str(config['db_port']), PGDATABASE='postgres' if admin else 'planner',
               PGUSER='planner_admin' if admin else 'planner_app',
               PGPASSWORD=config['admin_password'] if admin else config['app_password'], PGCLIENTENCODING='UTF8')
    # A machine's custom libpq options cannot redirect this deployment.
    for key in ('PGSERVICE', 'PGSERVICEFILE', 'PGOPTIONS'):
        env.pop(key, None)
    return env


def pg_running():
    if not (STATE/'postgres/PG_VERSION').exists():
        return False
    return subprocess.run([str(pg_tool('pg_ctl')), '-D', str(STATE/'postgres'), 'status'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW).returncode == 0


def assert_no_active_jobs(config):
    env = pg_env(config, admin=False)
    exists = command([pg_tool('psql'), '-X', '-At', '-c', "SELECT to_regclass('public.planner_run')"], env=env).strip()
    if exists:
        count = command([pg_tool('psql'), '-X', '-At', '-c',
                         "SELECT count(*) FROM planner_run WHERE job_status IN ('QUEUED','RUNNING')"], env=env).strip()
        if int(count):
            raise RuntimeError('Active solve jobs in this database; service stop/restart refused')


def database(config):
    data = owned_path(STATE/'postgres')
    if not (data/'PG_VERSION').exists():
        if data.exists() and any(data.iterdir()):
            raise RuntimeError('PostgreSQL directory is nonempty but uninitialized; retained for diagnosis')
        password = STATE/'init-password.txt'
        password.write_text(config['admin_password'], encoding='ascii')
        try:
            command([pg_tool('initdb'), '-D', data, '-U', 'planner_admin', '--encoding=UTF8', '--locale=C',
                     '--auth-host=scram-sha-256', '--auth-local=scram-sha-256', f'--pwfile={password}'], log=STATE/'logs/initdb.log')
        finally:
            password.unlink(missing_ok=True)
    if not pg_running():
        if not port_free(config['db_port']):
            raise RuntimeError('Database port occupied; refusing to use or stop another PostgreSQL instance')
        command([pg_tool('pg_ctl'), '-D', data, '-l', STATE/'logs/postgres.log', '-o',
                 f"-h 127.0.0.1 -p {config['db_port']}", '-w', 'start'], log=STATE/'logs/pg-start.log')
    actual = command([pg_tool('psql'), '-X', '-At', '-v', 'ON_ERROR_STOP=1', '-c', 'SHOW data_directory'], env=pg_env(config)).strip()
    if Path(actual).resolve() != data:
        raise RuntimeError('PostgreSQL ownership mismatch')
    query = "SELECT 1 FROM pg_database WHERE datname='planner'"
    exists = command([pg_tool('psql'), '-X', '-At', '-c', query], env=pg_env(config)).strip() == '1'
    if not exists:
        password = config['app_password']  # Generated URL-safe token, no SQL quote characters.
        sql = f"CREATE ROLE planner_app LOGIN PASSWORD '{password}';\nCREATE DATABASE planner OWNER planner_app;\n"
        command([pg_tool('psql'), '-X', '-v', 'ON_ERROR_STOP=1'], env=pg_env(config), input=sql, log=STATE/'logs/create-db.log')
    else:
        backup = STATE/'backups'/('planner-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.dump')
        command([pg_tool('pg_dump'), '-Fc', '-f', backup], env=pg_env(config, admin=False), log=STATE/'logs/backup.log')
        command([pg_tool('pg_restore'), '--list', backup], log=STATE/'logs/backup-contents.log')
        print('[DEPLOY] Existing installation database backed up', flush=True)


def smoke(config, keep=False):
    print('[DEPLOY] Testing real asynchronous solve and replay validation', flush=True)
    response = request(config, '/api/v1/planner-scenarios', {'name': '部署自检｜日历＋禁夜＋独占'})
    sid = response['id']
    rules = {'crane': True, 'commissioning': True}
    operations = [
        {'operation': 'create_seed_state', 'client_ref': 'draft:ready', 'payload': {'name': '已就绪'}},
        {'operation': 'create_resource', 'client_ref': 'draft:c', 'payload': {'name': '共享行吊', 'kind': 'crane', 'capacity': 2}},
        {'operation': 'update_scenario', 'payload': {'execution_mode': 'parallel', 'exclusive_rules': rules,
            'night_lift_rule': {'enabled': True, 'night_start': '20:00', 'night_end': '08:00'},
            'work_calendar_id': 'deployment-calendar', 'work_calendars': [{'id': 'deployment-calendar', 'name': '两班日历',
                'weekdays': [0,1,2,3,4], 'periods': [{'start': '08:00', 'end': '12:00'}, {'start': '13:00', 'end': '24:00'}], 'exceptions': []}]}},
    ]
    for name, duration, kind, fragile, crane in [('精密吊装',120,'机械集成',True,True), ('功能调测',45,'功能调测',False,False),
                                               ('普通甲',30,'机械集成',False,False), ('普通乙',30,'机械集成',False,False)]:
        operations.append({'operation': 'create_activity', 'payload': {'name': name, 'duration': duration, 'max_instances': 1,
            'preconditions': [{'state_id': 'draft:ready', 'relation_role': 'required'}],
            'metadata': {'activity_type': kind, 'precision_fragile': fragile}, 'resource_reqs': {'draft:c': 1} if crane else {}}})
    saved = request(config, f'/api/v1/planner-scenarios/{sid}/draft-commit', {'expected_revision': response['revision'], 'operations': operations})
    s = saved['scenario']
    payload = {'scenario_id': sid, 'expected_revision': saved['revision'], 'engine': 'JOINT_CP_SAT',
               'current_state_ids': [state['id'] for state in s['states'] if state['name'] == '已就绪'],
               'target_state_ids': [a['output_state_id'] for a in s['activities']], 'budget': {'time_limit_seconds': 15},
               'execution_bound_mode': 'auto', 'seed': 11, 'client_request_id': str(uuid.uuid4()),
               'display_start_at': '2026-11-04T19:00:00+08:00', 'display_timezone': 'Asia/Shanghai'}
    job = request(config, '/api/v1/planner-runs/async', payload)
    assert request(config, '/api/v1/planner-runs/async', payload)['id'] == job['id'], 'Idempotency failure'
    deadline = time.monotonic()+90
    while time.monotonic() < deadline:
        job = request(config, '/api/v1/planner-runs/'+job['id'])
        if job['job_status'] in ('FINISHED', 'FAILED'):
            break
        time.sleep(1)
    result = (job.get('result') or {}).get('results', {}).get('JOINT_CP_SAT', {})
    write_json(STATE/'last-smoke-run.json', job)
    if result.get('status') != 'OPTIMAL' or not result.get('paths'):
        raise RuntimeError('Deployment solve failed or worker not ready; inspect last-smoke-run.json')
    candidate = result['paths'][0]
    assert candidate['validator_status'] == 'VALID' and candidate['metrics']['makespan'] == 900
    rows = candidate['executions']
    assert len(rows) == 4
    for row in rows:
        if row['activity_name'] in ('精密吊装', '功能调测'):
            assert all(other is row or row['end_time'] <= other['start_time'] or other['end_time'] <= row['start_time'] for other in rows)
        if row['activity_name'] == '精密吊装':
            assert (row['start_time'], row['end_time']) == (780, 900)
    assert any(row['activity_name'] != '精密吊装' and row['end_time'] <= 780 for row in rows)
    if not keep:
        request(config, '/api/v1/planner-scenarios/'+sid, method='DELETE')
    return {'run_id': job['id'], 'scenario_id': sid, 'status': 'OPTIMAL', 'validator': 'VALID', 'makespan': 900,
            'executions': 4, 'elapsed_seconds': result['elapsed_seconds'], 'data_retained': keep}


def install_example(config):
    marker = STATE/'assembly-example.json'
    if marker.is_file():
        return load(marker)
    example = load(ROOT/'deploy/examples/assembly-commissioning-20.json')
    sid = example['id']
    existing = request(config, '/api/v1/planner-scenarios')
    if any(project['id'] == sid for project in existing):
        # A previous deployment may have committed the import before saving the marker.
        record = request(config, '/api/v1/planner-scenarios/' + sid)
        fixture = record['scenario'].get('provenance', {}).get('fixture')
        if fixture != example['provenance']['fixture']:
            raise RuntimeError('Bundled example ID already belongs to a different project')
    else:
        request(config, '/api/v1/planner-scenarios/import', {'scenario': example, 'preserve_ids': True})
    installed = {'scenario_id': sid, 'name': example['name']}
    write_json(marker, installed)
    return installed


def up(args):
    if os.name != 'nt':
        raise RuntimeError('This deployment package supports Windows x64')
    verify_manifest()
    config_path = STATE/'config.json'
    if config_path.exists():
        config = load(config_path)
        if config['root'] != str(ROOT):
            raise RuntimeError('Initialized deployment was moved; restore into its original path')
        for key in ('api_port', 'db_port'):
            if getattr(args, key) is not None and getattr(args, key) != config[key]:
                raise RuntimeError('Existing installation ports cannot be silently changed')
    else:
        api_port, db_port = args.api_port or 8026, args.db_port or 55450
        if api_port == db_port or not all(1024 <= n <= 65535 for n in (api_port, db_port)):
            raise ValueError('Distinct non-privileged API and database ports required')
        if not port_free(api_port) or not port_free(db_port):
            raise RuntimeError('Requested port occupied; choose other ports. No process was stopped.')
        if STATE.exists() and any(STATE.iterdir()):
            raise RuntimeError('Unowned deployment directory exists; refusing to adopt it')
        if any((ROOT/name).exists() for name in ('.env', '.venv', '.postgres-data')):
            raise RuntimeError('Existing environment detected; extract into a new empty directory')
        STATE.mkdir(exist_ok=True)
        config = {'root': str(ROOT), 'instance_id': str(uuid.uuid4()), 'api_port': api_port, 'db_port': db_port,
                  'admin_password': secrets.token_urlsafe(32), 'app_password': secrets.token_urlsafe(32)}
        write_json(config_path, config)
    for name in ('logs', 'backups'):
        (STATE/name).mkdir(exist_ok=True)
    processes = load(STATE/'processes.json') if (STATE/'processes.json').exists() else {}
    if is_our_process(processes.get('api')):
        active = request(config, '/api/v1/planner-runs')
        if any(r.get('job_status') in ('QUEUED', 'RUNNING') for r in active):
            raise RuntimeError('This installation has active solve jobs; retry after they finish')
    elif not port_free(config['api_port']):
        raise RuntimeError('API port is occupied by an unowned process; refusing to stop it')
    env = env_for(config)
    python = ROOT/'.venv/Scripts/python.exe'
    if not python.exists():
        print('[DEPLOY] Creating isolated Python environment', flush=True)
        command([ROOT/'runtime/python/python.exe', '-m', 'venv', ROOT/'.venv'], env=env, log=STATE/'logs/venv.log')
    lock_hash = hashlib.sha256((ROOT/'requirements-runtime.lock').read_bytes()).hexdigest()
    installed = STATE/'installed-lock.txt'
    if not installed.exists() or installed.read_text() != lock_hash:
        print('[DEPLOY] Installing locked dependencies from bundled wheels (offline)', flush=True)
        command([python, '-m', 'pip', 'install', '--no-index', '--find-links', ROOT/'wheelhouse', '-r', ROOT/'requirements-runtime.lock'],
                env=env, log=STATE/'logs/dependencies.log')
        installed.write_text(lock_hash)
    command([python, '-m', 'pip', 'check'], env=env, log=STATE/'logs/pip-check.log')
    print('[DEPLOY] Preparing owned PostgreSQL database', flush=True)
    database(config)
    assert_no_active_jobs(config)
    # Stop only this installation's services, after taking its database backup.
    stop_process(processes.get('worker'))
    stop_process(processes.get('api'))
    write_json(STATE/'processes.json', {})
    print('[DEPLOY] Migrating database to package head', flush=True)
    command([python, '-m', 'alembic', 'upgrade', 'head'], env=env, log=STATE/'logs/migrations.log')
    print('[DEPLOY] Starting API and durable worker', flush=True)
    processes = {}
    processes['api'] = start_process([python, '-m', 'uvicorn', 'app.main:app', '--app-dir', ROOT, '--host', '127.0.0.1', '--port', config['api_port']], 'uvicorn', env, 'api')
    write_json(STATE/'processes.json', processes)
    processes['worker'] = start_process([python, ROOT/'deploy/scripts/run_deployed_worker.py'], 'run_deployed_worker.py', env, 'worker')
    write_json(STATE/'processes.json', processes)
    deadline = time.monotonic()+40
    while True:
        try:
            health = request(config, '/health')
            status = request(config, '/api/v1/system/status?include_data_checks=false')
            if status['status'] == 'ready' and health['release_id'] == load(ROOT/'VERSION.json')['release_id']:
                break
        except Exception:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('API/database readiness failed; inspect API and migration logs')
        time.sleep(1)
    caps = request(config, '/api/v1/planner-runs/capabilities')
    assert Path(caps['planner_project_path']).resolve() == (ROOT/'solver').resolve()
    assert caps['planner_available'] and caps['joint_cp_sat']['crane_exclusivity_supported']
    with urllib.request.urlopen(f"http://127.0.0.1:{config['api_port']}/") as page:
        assert b'/assets/' in page.read(), 'Built frontend missing'
    verified = smoke(config, keep=args.keep_smoke_data)
    example = install_example(config)
    report = {'url': f"http://127.0.0.1:{config['api_port']}", 'database_port': config['db_port'],
              'migration': status['database']['alembic'], 'solver_path': caps['planner_project_path'],
              'smoke': verified, 'bundled_example': example, 'release_id': health['release_id'], 'status': 'ready'}
    write_json(STATE/'verification.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


def stop():
    config = load(STATE/'config.json')
    assert config['root'] == str(ROOT)
    processes = load(STATE/'processes.json') if (STATE/'processes.json').exists() else {}
    if is_our_process(processes.get('api')):
        if any(r.get('job_status') in ('QUEUED', 'RUNNING') for r in request(config, '/api/v1/planner-runs')):
            raise RuntimeError('Active solve jobs: stop refused to avoid interrupting execution')
    if pg_running():
        assert_no_active_jobs(config)
    for name in ('worker', 'api'):
        stop_process(processes.get(name))
    write_json(STATE/'processes.json', {})
    if pg_running():
        actual = command([pg_tool('psql'), '-X', '-At', '-c', 'SHOW data_directory'], env=pg_env(config)).strip()
        if Path(actual).resolve() != owned_path(STATE/'postgres'):
            raise RuntimeError('Database ownership mismatch; refusing stop')
        command([pg_tool('pg_ctl'), '-D', owned_path(STATE/'postgres'), '-m', 'fast', '-w', 'stop'], log=STATE/'logs/pg-stop.log')
    print('Stopped only this installation. Database and backups retained.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['up', 'stop'])
    parser.add_argument('--api-port', type=int)
    parser.add_argument('--db-port', type=int)
    parser.add_argument('--keep-smoke-data', action='store_true')
    args = parser.parse_args()
    try:
        with deployment_lock():
            up(args) if args.action == 'up' else stop()
    except Exception as exc:
        print(f'[DEPLOY ERROR] {exc}', file=sys.stderr, flush=True)
        sys.exit(1)
