# Shared planner source snapshot

This directory captures the `planner_experiment` Python source used by Solver
Workbench on 2026-11-09, including local changes that are not in the upstream
planner commit. `SOURCE_SNAPSHOT.json` records the upstream commit and SHA-256
of each copied source file. The upstream repository is
https://github.com/kdyk842606106-cpu/planner.

For a source checkout, run the following from the Solver_demo_project root
before starting the API, worker, or solver tests in the same PowerShell session:

```powershell
$env:PLANNER_PROJECT_PATH = (Resolve-Path .\solver).Path
```

For Windows release packaging, use this snapshot explicitly:

```powershell
.\deploy\scripts\package_release.ps1 -Version 0.3.1-beta.5 -PlannerRoot (Resolve-Path .\solver).Path -OutputDirectory D:\releases\planner-0.3.1-beta5
```

The command is a build example, not an already published release. Packaging
prerequisites and database handling are documented in
[ONE_CLICK_DEPLOYMENT.md](../docs/ONE_CLICK_DEPLOYMENT.md).

This snapshot contains source only, not databases, credentials, virtual
environments, or historical run data. It does not change the existing runtime
path selection or modify the separate planner checkout. Refresh it deliberately
when the shared planner changes, along with the file hashes.
