"""Audit the isolated rank diagnosis and retain reproducible evidence."""
import hashlib
import json
from pathlib import Path
import re
from google.protobuf import text_format
from ortools.sat import cp_model_pb2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/causal-rank-diagnosis-20261106'
SOURCE = ROOT / 'output/test-a-b-d-repair-effects-20261106/after-input.json'

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def stats(text):
    result = dict(re.findall(r'^(\w+): (.+)$', text, re.M))
    for key, value in list(result.items()):
        try:
            result[key] = float(value) if any(c in value for c in '.e') else int(value)
        except ValueError:
            pass
    return result

def model(tag):
    p = cp_model_pb2.CpModelProto()
    return text_format.Parse((OUT / f'{tag}-initial-model.pbtxt').read_text(encoding='utf-8'), p)

def business_constraints(p):
    return [str(c) for c in p.constraints if c.ListFields() and not c.name.startswith('causal_rank:')]

base = model('off')
source = read(SOURCE)
source_hash = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
results = {}
for path in sorted(OUT.glob('*-summary.json')):
    r = read(path)
    tag = path.name.split('seed37-', 1)[1].removesuffix('-summary.json')
    diagnostics = read(OUT / f'{tag}-diagnostics.json')
    actual = model(tag)
    assert source == read(path.with_name(path.name.replace('-summary.json', '-input.json')))
    assert r['input_sha256'] == source_hash
    assert r['seed'] == 37 and r['worker_threads'] == 1 and r['budget_seconds'] == 60
    assert r['encoding'] == 'appended' and r['implementation'] == 'new'
    assert r['status'] == 'OPTIMAL' and r['validator'] == 'VALID' and not r['validator_rejections']
    assert (r['best_makespan'], r['best_execution_count']) == (390, 10)
    assert list(base.variables) == list(actual.variables)[:len(base.variables)]
    assert business_constraints(base) == business_constraints(actual)
    assert base.objective == actual.objective and base.solution_hint == actual.solution_hint
    assert all(name.startswith('causal_rank:') for d in diagnostics for name in d['removed_auxiliary_constraints'])
    first = stats(diagnostics[0]['response_stats'])
    after = r['branches'] - first['branches']
    log = (OUT / f'{tag}-call0.log').read_text(encoding='utf-8')
    preloaded = re.search(r'Starting search at ([\d.]+)s', log)
    presolved = log.split('Presolved optimization model', 1)[1]
    count = re.search(r'#Variables: ([\d\']+)', presolved)
    results[tag] = {
        'first_solution_seconds': r['first_solution_seconds'],
        'total_seconds': r['elapsed_seconds'], 'total_branches': r['branches'],
        'first_call': first, 'after_first_call_branches': after,
        'after_first_solution_seconds': r['elapsed_seconds'] - r['first_solution_seconds'],
        'presolve_and_loading_seconds': float(preloaded.group(1)),
        'presolved_variables': int(count.group(1).replace("'", '')),
        'source_variables': len(actual.variables),
        'source_nonempty_constraints': sum(bool(c.ListFields()) for c in actual.constraints),
        'removed_auxiliary_constraints': len(diagnostics[0]['removed_auxiliary_constraints']),
        'status': r['status'], 'makespan': 390, 'executions': 10, 'validator': r['validator'],
        'source_and_original_model_unchanged': True,
        'log': str(OUT / f'{tag}-call0.log')}

assert len(results) == 11
for tag in ('off', 'on', 'no-absent'):
    assert results[tag]['total_branches'] == results[tag + '-repeat']['total_branches']
    for key in ('branches', 'conflicts', 'booleans', 'integer_propagations', 'propagations', 'lp_iterations'):
        assert results[tag]['first_call'][key] == results[tag + '-repeat']['first_call'][key]

report = {
    'input_sha256': source_hash, 'source': str(SOURCE), 'ortools': '9.15.6755',
    'method': '11 serial fresh-process runs, frozen recovery-current input, seed 37, single thread, 60 seconds; appended mandatory encoding and new linear propagation unchanged.',
    'production_changes': False, 'database_writes': False,
    'findings': [
        'The same first-call and total branch counts reproduce exactly for off/on; machine load does not explain this branch regression.',
        'The first search before any incumbent feedback causes the regression: 52,414 -> 590,117 branches; after the first call branches decrease 44,431 -> 15,724.',
        'The original model has 777 variables; ranks add 28 variables and 263 constraints. Presolve/loading stays about 0.20/0.21 seconds, and both begin with working-time finish domain [141,44940] then lower bound 180.',
        'Bounds-only reproduces baseline branches. Edges-only improves elapsed time. Removing just absent=>rank=0 retains all business constraints and causal edges, and reproducibly yields 137,143 total branches, about 3.3 seconds.',
        'The absent-zero normalization is an implementation convention, not a business requirement. Together with present=>rank>=1 it links activity presence to rank zero/nonzero; selected support edges already require present producer/consumer.',
        'Disabling LP changes the outcome in opposite directions for off/on. Both default runs have the same logged LP pool size and final LP dimension; this is search/propagation interaction, not evidence that rank constraints enlarged the LP matrix.',
        'No-present alone takes longer despite fewer branches: branch counts are not equal-cost units of work.',
        'All 11 runs prove 390 minutes / 10 executions and replay VALID. The experiment diagnoses this representation/seed interaction, not a universally harmful constraint or a general replacement strategy.'
    ],
    'limitations': [
        'The native log aggregates SAT/LP statistics; it does not label each decision or learned clause by original variable. It cannot identify a particular bad branch or assign exact CPU time to each propagator.',
        'The growth of internal Boolean variables is observed, but its exact attribution to time/rank/resource encodings is not available in these logs.',
        'Ablation timing is local to this input and seed; no-absent was repeated here but not benchmarked across other scenes or seeds. Production rank switch remains off.'
    ],
    'source_references': [
        'https://github.com/google/or-tools/blob/v9.15/ortools/sat/integer.h',
        'https://github.com/google/or-tools/blob/v9.15/ortools/sat/sat_parameters.proto'
    ], 'results': results}
target = ROOT / 'docs/validation/CAUSAL_RANK_DIAGNOSIS_20261106.json'
target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
lines = ['测试A维修恢复：因果层级 / 种子37诊断',
         '业务输入、资源、日历、时间窗、目标、实例上限及必做编码保持不变；仅调整辅助层级或诊断用LP开关。',
         '所有11次独立运行：OPTIMAL，390分钟，10次执行，回放VALID。',
         'mode | first seconds | total seconds | first branches | total branches | post-first branches']
for tag, r in results.items():
    lines.append(f"{tag} | {r['first_solution_seconds']:.3f} | {r['total_seconds']:.3f} | {r['first_call']['branches']} | {r['total_branches']} | {r['after_first_call_branches']}")
lines += ['', '定位：首解前搜索退化；因果边与未执行实例层级归零的绑定、默认搜索/LP共同作用。',
          'off/on复跑分支完全一致。仅移除absent=>rank=0后复跑为137143分支，约3.3秒。',
          '归零是辅助变量规范化，不是业务约束；诊断实验保留所有原始约束、目标和因果边。',
          '不能据此声称每次分支属于哪个变量，也不能承诺换成no-absent后所有场景都加速。',
          '生产实现、项目配置及历史未修改；完整模型审计、日志及证据见JSON。']
(OUT / 'diagnosis.txt').write_text('\n'.join(lines), encoding='utf-8')
print('\n'.join(lines))
print('All model and result audits passed:', target)
