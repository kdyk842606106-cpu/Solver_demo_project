from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _release_script() -> str:
    return (PROJECT_ROOT / "deploy/scripts/package_release.ps1").read_text(encoding="utf-8")


def test_release_packaging_requires_clean_traceable_source():
    script = _release_script()

    assert "git' @('status', '--porcelain')" in script
    assert "git' @('rev-parse', 'HEAD')" in script
    assert "Release tag already exists" in script
    assert "The production build changed tracked files" in script


def test_release_packaging_uses_allowlist_and_generated_metadata():
    script = _release_script()

    assert "@('app', 'migrations', 'deploy', 'scripts', 'seeds', 'frontend\\dist')" in script
    assert "@('.env.example', 'alembic.ini', 'requirements.txt', 'README.md')" in script
    assert "app_version = $Version" in script
    assert "app_commit = $commit" in script
    assert "MANIFEST.sha256" in script
    assert "Get-FileHash -Algorithm SHA256" in script


def test_release_notes_document_upgrade_safety_and_exclusions():
    script = _release_script()

    assert "Back up the existing PostgreSQL database" in script
    assert "--project=chromium', '--workers=1'" in script
    assert "Copy the verifier machine's existing .env" in script
    assert "intentionally excludes .env, databases" in script
    assert "install_verify.ps1 -ExpectedCommit" in script


def test_release_notes_classify_beta_separately_from_rc():
    script = _release_script()

    assert "'beta release'" in script
    assert "'release candidate'" in script
    assert "Release level: $releaseLevel" in script
