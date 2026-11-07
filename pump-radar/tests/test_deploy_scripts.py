"""Gli script di deploy devono restare ASCII puri.

Lezione del 2026-11-07: PowerShell 5.1 (Windows 10) legge i .ps1 senza BOM
come Windows-1252; un carattere UTF-8 multibyte (es. la spunta U+2714) si
spezza in una virgoletta curva che chiude le stringhe -> ParserError
"TerminatorExpectedAtEndOfString" e l'installazione H24 non parte.
Stessa igiene per .bat/.sh/.service: niente sorprese di codifica, mai.
"""
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def _deploy_files():
    return sorted(p for p in DEPLOY.rglob("*") if p.is_file())


def test_deploy_scripts_are_ascii_only():
    bad = {}
    for p in _deploy_files():
        offenders = sorted({b for b in p.read_bytes() if b > 127})
        if offenders:
            bad[str(p.relative_to(DEPLOY))] = offenders
    assert not bad, f"caratteri non-ASCII negli script di deploy: {bad}"


def test_windows_installer_present_and_structured():
    ps1 = (DEPLOY / "windows" / "install.ps1").read_text(encoding="ascii")
    for needle in ("New-ScheduledTaskAction", "New-ScheduledTaskTrigger -AtLogOn",
                   "Register-ScheduledTask", "powercfg /change standby-timeout-ac 0",
                   "ExecutionTimeLimit ([TimeSpan]::Zero)"):
        assert needle in ps1, needle
    bat = (DEPLOY / "windows" / "start-pumpradar.bat").read_text(encoding="ascii")
    assert "goto loop" in bat and "-m pumpradar run" in bat
