from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_script(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_backend_restart_only_claims_processes_from_this_checkout():
    script = _read_script("deploy/scripts/install_verify.ps1")

    assert "return $normalizedCommand.Contains($normalizedRoot)" in script
    assert "if (Test-ProjectProcess $pidValue $Root)" in script
    assert "Ignoring stale backend PID file owned by another process" in script
    assert "$normalizedCommand.Contains('uvicorn')" not in script
    assert "$env:APP_COMMIT = $ExpectedCommit" in script


def test_frontend_restart_only_claims_processes_from_this_checkout():
    script = _read_script("deploy/scripts/start_intranet_frontend.ps1")

    assert "return $normalizedCommand.Contains($normalizedRoot)" in script
    assert "$normalizedCommand.Contains('vite')" not in script
    assert "$normalizedCommand.Contains('npm.cmd')" not in script


def test_verified_start_can_explicitly_replace_stale_frontend():
    frontend_script = _read_script("deploy/scripts/start_intranet_frontend.ps1")
    local_start = _read_script("start.local.bat")

    assert "[switch]$ForceKillPortProcess" in frontend_script
    assert "-Force:$ForceKillPortProcess" in frontend_script
    assert "-ForceKillPortProcess" in local_start
    assert "-ExpectedCommit" in local_start
