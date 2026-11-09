# TICKET-101：三引擎六档规模实验

> Status: complete — 2026-11-01
> Scope: implement the user-approved three-engine experimental protocol in D:/planner and optional Solver bridge instrumentation. No business scenarios, database writes/migrations, deployment or algorithm redesign.

- [x] Deterministic C0–C6 and provider-pair generation at N=8/16/32/64/128/256.
- [x] Complexity vector with transitive order strength and exact poset width.
- [x] Constructive lower-bound certificates, bounded exact oracle and twelve golden cases.
- [x] Optional candidate observation, end-to-end deadlines and single-worker CP-SAT.
- [x] Isolated runner, durable candidates, frozen source/input/config hashes, resume and eight-hour budget.
- [x] Instance-first CSV/JSON summaries and interactive HTML charts.
- [x] Engine regressions, subprocess smoke and report visual verification.
- [x] Freeze formal artifacts and start the default experimental run.
- [x] Formal execution finishes; inspect full coverage and conclusions.

No new parameters change behaviour when omitted. The experiment uses the existing shared Simulator and Validator, with an independent resource interval sweep and analytical golden proofs as cross-checks. The original LEGACY pipeline continues to select its own path; its fixed-path CP-SAT optimal status is never used as a global proof.

Current plan totals: 144 generated + 12 golden instances; 3996 formal runs; 18252 seconds of maximum solve budgets plus startup, proof generation and reporting within a hard eight-hour batch limit. Smoke data remain outside formal statistics. Source snapshot, unrun coverage and unknown proofs are explicit. Detailed runbook: `D:/planner/docs/three-engine-benchmark.md`.

ANCHOR: no violations. TICKET-098 remains deferred; TICKET-100 remains complete. No production database or historical result snapshot is modified.

Verification: Planner full regression 90 passed with temporary files routed to the workspace; existing bridge/delete integration 29 passed (outside the sandbox because its SQLite setup stalled inside it); new optional-instrumentation integration 4 passed. Representative fresh-process pilot: 24 runs, zero rejected unique candidates and zero input-hash conflicts; timeout incumbents and zero-makespan cases retained correctly. Chromium report QA: six charts, working selectors and no JavaScript errors. All formal runs are complete; pilot evidence is never included in formal statistics.

Formal delivery: `D:/planner/runs/three-engine-20261101`. All 156 inputs remain frozen (106 proved optimal after exact oracles, 48 unknown, 2 proved infeasible). The default batch ran from 2026-11-01 17:42 to 22:44 Asia/Shanghai, 18126.52 seconds, and completed 3996/3996 runs. Logs: `runner.stdout.log` / `runner.stderr.log`; progress: `batch_state.json`; report: `report.html`. The final independent audit reconciled every raw run with candidate events and CSV, confirmed source fingerprints unchanged, and found zero input-hash conflicts, candidate rejections or contradictions with proved answers.

Final analysis: `D:/planner/runs/three-engine-20261101/final-analysis.json`, calculated by `D:/planner/tmp/analyze_final_benchmark.py`. In the main suite, each engine/budget has 378 runs and 234 known-optimum runs. Success rates at 1/3/10 seconds: LEGACY 75.7/85.7/89.9%; ASTAR 60.6/65.9/77.8%; GA 46.8/51.6/65.1%. At 10 seconds, PAR-2 is 2.609/5.308/7.861 seconds and optimum hit rates are 100/19.2/69.2% (LEGACY/ASTAR/GA). GA's zero gap among solved known-optimum main cases does not generalize to the provider suite. All 378 GA runs at N=128/256 in the main suite produced no valid candidate. In all 27 C0 ten-second ASTAR runs at N=64/128/256, the final makespan remained the initial seed's, with N-1 redundant executions. Independent diagnosis reproduced a 39.71-second first GA decode at N=128 on a separate CPU. These support implementation bottlenecks; fixes were explicitly deferred and no algorithm was changed for the final readout. There remain 48 main models without optimum proofs and a few LEGACY replay errors; the result is not a general ranking of abstract algorithms or a production-readiness claim.
