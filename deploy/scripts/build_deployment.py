"""Build a self-contained Windows package without modifying the running checkout."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SOURCE_DIRS = ('app', 'migrations', 'deploy')
SOURCE_FILES = ('alembic.ini', 'requirements.txt', 'README.md', 'deploy.bat', 'start-workbench.cmd', 'stop.bat')


def run(args, cwd=None):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def git_info(root):
    def git(*args):
        return subprocess.check_output(['git', '-c', f'safe.directory={root.as_posix()}', '-C', str(root), *args], text=True).strip()
    return {'commit': git('rev-parse', 'HEAD'), 'dirty': bool(git('status', '--porcelain'))}


def runtime_requirements(root):
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    roots = (root / 'requirements.txt').read_text(encoding='utf-8').split('# Testing')[0]
    versions, visited = {}, set()
    def include(req):
        key = canonicalize_name(req.name)
        visit = (key, tuple(sorted(req.extras)))
        if visit in visited:
            return
        visited.add(visit)
        dist = metadata.distribution(req.name)
        if req.specifier and not req.specifier.contains(dist.version):
            raise ValueError(f'Installed {req.name} does not satisfy requirements')
        versions[key] = dist.version
        for text in dist.requires or []:
            child = Requirement(text)
            if child.marker is None or any(child.marker.evaluate({'extra': extra}) for extra in ('', *req.extras)):
                include(child)
    for line in roots.splitlines():
        if line.strip() and not line.startswith('#'):
            include(Requirement(line))
    return '\n'.join(f'{name}=={version}' for name, version in sorted(versions.items())) + '\n'


def release_level(version, dirty):
    if dirty:
        return 'working-tree snapshot (not a formal release)'
    if 'beta' in version:
        return 'beta release'
    if 'rc' in version:
        return 'release candidate'
    return 'pre-release' if '-' in version else 'stable release'


def copytree(source, destination):
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache', 'node_modules'))


def build(args):
    root = args.project_root.resolve()
    planner = args.planner_root.resolve()
    postgres = args.postgres_root.resolve()
    assert sys.platform == 'win32' and sys.maxsize > 2**32, 'Windows x64 builder required'
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?', args.version):
        raise ValueError('Invalid version')
    info, planner_info = git_info(root), git_info(planner)
    dirty = info['dirty'] or planner_info['dirty']
    if dirty and not args.allow_dirty:
        raise ValueError('Clean worktrees required; --allow-dirty explicitly builds a traced working-tree snapshot')
    for required in (planner/'planner_experiment/scenario.py', postgres/'bin/initdb.exe', postgres/'bin/pg_dump.exe'):
        if not required.is_file():
            raise FileNotFoundError(required)
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Output must not already exist; existing deployments are never overwritten')
    if output == root or root.is_relative_to(output) or output == planner or planner.is_relative_to(output):
        raise ValueError('Output must not contain a source checkout')
    output.mkdir(parents=True)
    work = output.parent / ('.build-' + uuid.uuid4().hex)
    work.mkdir()
    print('[PACKAGE] Building React in a separate directory', flush=True)
    front = work/'frontend'
    front.mkdir()
    for name in ('src', 'public'):
        if (root/'frontend'/name).is_dir():
            copytree(root/'frontend'/name, front/name)
    for name in ('package.json', 'package-lock.json', 'index.html', 'tsconfig.json', 'vite.config.js', '.npmrc'):
        if (root/'frontend'/name).is_file():
            shutil.copy2(root/'frontend'/name, front/name)
    npm = shutil.which('npm.cmd')
    if not npm:
        raise RuntimeError('Node.js/npm required on packaging machine only')
    run([npm, 'ci', '--prefer-offline', '--no-audit', '--no-fund'], front)
    run([npm, 'run', 'build'], front)
    copytree(front/'dist', output/'frontend/dist')
    for name in SOURCE_DIRS:
        copytree(root/name, output/name)
    for name in SOURCE_FILES:
        shutil.copy2(root/name, output/name)
    (output/'docs').mkdir()
    shutil.copy2(root/'docs/ONE_CLICK_DEPLOYMENT.md', output/'docs/ONE_CLICK_DEPLOYMENT.md')
    copytree(planner/'planner_experiment', output/'solver/planner_experiment')
    print('[PACKAGE] Bundling Python and PostgreSQL (no databases or credentials)', flush=True)
    pyroot = Path(sys.base_prefix)
    pyout = output/'runtime/python'
    pyout.mkdir(parents=True)
    for file in pyroot.iterdir():
        if file.is_file() and (file.suffix.lower() in ('.exe', '.dll') or file.name == 'LICENSE.txt'):
            shutil.copy2(file, pyout/file.name)
    for directory in ('Lib', 'DLLs'):
        shutil.copytree(pyroot/directory, pyout/directory,
                        ignore=shutil.ignore_patterns('site-packages', '__pycache__', '*.pyc'))
    for directory in ('bin', 'lib', 'share'):
        copytree(postgres/directory, output/'runtime/postgresql'/directory)
    for file in postgres.glob('*license*.txt'):
        shutil.copy2(file, output/'runtime/postgresql'/file.name)
    lock = runtime_requirements(root)
    (output/'requirements-runtime.lock').write_text(lock, encoding='utf-8')
    print('[PACKAGE] Downloading locked Windows wheels for offline installation', flush=True)
    run([sys.executable, '-m', 'pip', 'download', '--only-binary=:all:', '-r', output/'requirements-runtime.lock', '-d', output/'wheelhouse'])
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(root/'alembic.ini'))
    cfg.set_main_option('script_location', str(root/'migrations'))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    version = {'app_version': args.version, 'app_commit': info['commit'], 'release_id': f'{args.version}+{stamp}.{uuid.uuid4().hex[:8]}',
               'release_level': release_level(args.version, dirty), 'source': info, 'solver_source': planner_info,
               'migration_heads': heads, 'python_version': list(sys.version_info[:3]), 'platform': 'windows-x64',
               'built_at': stamp}
    (output/'VERSION.json').write_text(json.dumps(version, indent=2), encoding='utf-8')
    hashes = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(output.rglob('*')) if p.is_file()}
    (output/'MANIFEST.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    print('[PACKAGE] Creating ZIP and checksum', flush=True)
    archive_path = output.with_suffix('.zip')
    if archive_path.exists():
        raise ValueError('Refusing to overwrite existing archive')
    with zipfile.ZipFile(archive_path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for file in output.rglob('*'):
            if file.is_file():
                archive.write(file, Path(output.name)/file.relative_to(output))
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix('.zip.sha256').write_text(digest+'  '+archive_path.name+'\n', encoding='ascii')
    print(json.dumps({'package': str(output), 'zip': str(archive_path), 'sha256': digest, 'build_workspace': str(work), **version}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument('--planner-root', type=Path, required=True)
    p.add_argument('--postgres-root', type=Path, default=Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'PostgreSQL/15')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--version', required=True)
    p.add_argument('--allow-dirty', action='store_true')
    build(p.parse_args())
