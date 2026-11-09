import hashlib
import importlib.util
import json
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'deploy/scripts'/f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_snapshot_provenance_and_release_level():
    builder = module('build_deployment')
    assert 'not a formal release' in builder.release_level('1.0.0', True)
    assert builder.release_level('1.0.0-beta.1', False) == 'beta release'
    assert builder.release_level('1.0.0-rc.1', False) == 'release candidate'
    assert builder.release_level('1.0.0', False) == 'stable release'


def test_locked_runtime_closure_contains_solver_database_and_no_dev_tools():
    builder = module('build_deployment')
    lock = builder.runtime_requirements(ROOT)
    names = {line.split('==')[0] for line in lock.splitlines()}
    assert {'fastapi', 'asyncpg', 'psycopg-binary', 'ortools', 'numpy', 'tzdata', 'alembic'} <= names
    assert not {'pytest', 'black', 'mypy'} & names
    assert all('==' in line and '@' not in line for line in lock.splitlines())


def test_deployment_path_cannot_escape_managed_root(tmp_path):
    runtime = module('deploy_runtime')
    assert runtime.owned_path(tmp_path/'data', tmp_path) == tmp_path/'data'
    for path in [tmp_path, tmp_path.parent/'foreign', tmp_path/'..'/'foreign']:
        with pytest.raises(ValueError):
            runtime.owned_path(path, tmp_path)


def test_package_hash_tampering_and_path_escape_are_rejected(tmp_path, monkeypatch):
    runtime = module('deploy_runtime')
    monkeypatch.setattr(runtime, 'ROOT', tmp_path)
    file = tmp_path/'app.txt'
    file.write_text('expected')
    manifest = tmp_path/'MANIFEST.json'
    manifest.write_text(json.dumps({'app.txt': hashlib.sha256(file.read_bytes()).hexdigest()}))
    runtime.verify_manifest()
    file.write_text('tampered')
    with pytest.raises(RuntimeError, match='checksum'):
        runtime.verify_manifest()
    manifest.write_text(json.dumps({'../outside': 'irrelevant'}))
    with pytest.raises(ValueError):
        runtime.verify_manifest()


def test_environment_does_not_inherit_original_database_or_solver(tmp_path, monkeypatch):
    runtime = module('deploy_runtime')
    monkeypatch.setattr(runtime, 'ROOT', tmp_path)
    (tmp_path/'VERSION.json').write_text(json.dumps({'app_version': 'x', 'app_commit': 'c', 'release_id': 'r'}))
    for key in ('DATABASE_URL', 'DATABASE_URL_SYNC', 'PYTHONPATH', 'PYTHONHOME', 'PLANNER_PROJECT_PATH'):
        monkeypatch.setenv(key, 'must-not-use-original')
    env = runtime.env_for({'db_port': 55450, 'app_password': 'fake-test-value'})
    assert env['DB_PORT'] == '55450' and env['DB_NAME'] == 'planner'
    assert env['PLANNER_PROJECT_PATH'] == str(tmp_path/'solver')
    assert all(key not in env for key in ('DATABASE_URL', 'DATABASE_URL_SYNC', 'PYTHONPATH', 'PYTHONHOME'))


def test_port_collision_detected_without_terminating_owner():
    runtime = module('deploy_runtime')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        sock.listen()
        assert not runtime.port_free(sock.getsockname()[1])
        assert sock.getsockname()[1] > 0


@pytest.mark.parametrize('foreign', ['path', 'created', 'marker', 'exited'])
def test_reused_or_foreign_pid_is_never_stopped(monkeypatch, foreign):
    runtime = module('deploy_runtime')
    info = {'CommandLine': f'{runtime.ROOT} python -m uvicorn', 'CreationDate': 'original'}
    if foreign == 'path': info['CommandLine'] = 'C:/other python -m uvicorn'
    if foreign == 'created': info['CreationDate'] = 'new-process'
    if foreign == 'marker': info['CommandLine'] = f'{runtime.ROOT} unrelated-program'
    monkeypatch.setattr(runtime, 'process_info', lambda pid: None if foreign == 'exited' else info)
    monkeypatch.setattr(runtime, 'command', lambda *a, **kw: pytest.fail('must not terminate foreign process'))
    runtime.stop_process({'pid': 1234, 'marker': 'uvicorn', 'created': 'original'})
