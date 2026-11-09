"""Build and audit the 150-activity UI fixture; never writes to the database."""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.planner_scenarios import (
    new_scenario, create_activity, create_package, add_membership,
    expand_packages, validate_scenario, technical_id,
)
from app.services.planner_engine_bridge import _planner_modules

NAME = "150活动压力测试｜主线＋6支线｜平均7前置｜四类瓶颈"
BRANCHES = ["机架结构", "动力传动", "液压管路", "电气配线", "控制仪表", "防护附件"]
PHASES = ["基础构建", "模块装配", "系统集成", "联调准备", "交付验收"]


def build():
    s = new_scenario(NAME)
    s.update(execution_mode="parallel", max_steps=150,
             default_budget={"time_limit_seconds": 120, "transition_limit": 20000, "max_solutions": 20})
    s['provenance'].update(fixture="mainline_6branches_150_v1", material_semantics="renewable_capacity")

    def state(name, initial=False):
        sid = technical_id('state') + ':seed'
        s['states'].append({'id': sid, 'name': name, 'state_kind': 'seed', 'managed': True})
        if initial:
            s['initial_state_ids'].append(sid)
        return sid

    seeds = [state(n, True) for n in ["设计文件已批准", "工艺规程已批准", "作业许可已生效",
             "质量基准已确认", "安全交底已完成", "检验规范已发布", "装配基准已确认"]]
    resources = {}
    for kind, name, capacity in [('crew', '综合装配责任组', 6), ('workspace', '共享装配作业区', 3),
                                 ('material', '标准周转物料套件', 4), ('crane', '通用行吊池', 1)]:
        r = {'id': technical_id('resource'), 'name': name, 'kind': kind, 'capacity': capacity, 'is_active': True}
        s['resources'].append(r)
        resources[kind] = r
    packs = {}
    for line, title in enumerate(['主线·整机集成'] + ['支线·' + x for x in BRANCHES]):
        root = create_package(s, {'name': title, 'sort_order': line}, display_number=len(s['activity_packages'])+1)
        for phase, title in enumerate(PHASES):
            packs[line, phase] = create_package(s, {'name': f'{phase+1:02d} {title}', 'parent_id': root['id'],
                                                   'sort_order': phase}, display_number=len(s['activity_packages'])+1)['id']

    waves = []
    previous = []
    terminal = None

    def activity(line, phase, name, required, *, transition=(), outputs=(), delete=(), demand=None, duration=5):
        assert len(required) == len(set(required)) == 7
        a = create_activity(s, {'name': name, 'duration': duration, 'max_instances': 1,
             'preconditions': [{'state_id': st, 'relation_role': 'required'} for st in required]
                 + [{'state_id': st, 'relation_role': 'transition'} for st in transition],
             'additional_output_state_ids': list(outputs), 'delete_effect_state_ids': list(delete),
             'resource_reqs': {resources[k]['id']: v for k, v in (demand or {'crew': 1, 'workspace': 1}).items()},
             'metadata': {'activity_type': '机械集成' if phase < 3 else '功能调测',
                 'fixture_line': 'main' if line == 0 else f'branch_{line}', 'fixture_phase': phase+1,
                 'description': '一次性必选工序；无替代活动。普通前置7项，转移条件另计。周转物料完工释放。',
                 'risk_jobs': ['吊装作业'] if demand and demand.get('crane') else [],
                 'precision_fragile': bool(demand and demand.get('crane') and line in (4, 5))}},
             display_number=len(s['activities'])+1)
        add_membership(s, packs[line, phase], a['id'], sort_order=len(s['activities']))
        return a

    for phase, phase_name in enumerate(PHASES):
        main = activity(0, phase, f'主线{phase*6+1:02d}·{phase_name}启动',
                        [terminal['output_state_id'], *previous] if terminal else seeds, duration=6+phase)
        clean = [state(f'{phase_name}·{b}·防护与清洁合格', True) for b in BRANCHES]
        ready = [state(f'{phase_name}·{b}·待开工', True) for b in BRANCHES]
        hoist = [state(f'{phase_name}·{b}·待吊装') for b in BRANCHES]
        open_work = [state(f'{phase_name}·{b}·待恢复防护') for b in BRANCHES]
        for step, verb in enumerate(['预装放行', '吊装就位', '连接与防护恢复', '完工验证']):
            wave = []
            for branch, branch_name in enumerate(BRANCHES):
                required = [main['output_state_id'], *(previous if previous else seeds[:6])]
                if step == 0 or step == 3:
                    # Keep seven prerequisites; restored protection is a real condition.
                    required[-1] = clean[branch]
                transitions = [ready[branch]] if step == 0 else [hoist[branch]] if step == 1 else [open_work[branch]] if step == 2 else []
                outputs = [hoist[branch]] if step == 0 else [open_work[branch]] if step == 1 else [clean[branch]] if step == 2 else []
                demands = [dict(crew=3, workspace=1, material=1), dict(crew=1, workspace=1, material=1, crane=1),
                           dict(crew=1, workspace=1, material=2), dict(crew=1, workspace=2, material=1)][step]
                a = activity(branch+1, phase, f'{branch_name}{phase*4+step+1:02d}·{phase_name}·{verb}', required,
                             transition=transitions, outputs=outputs, delete=[clean[branch]] if step == 1 else [],
                             demand=demands, duration=[14, 10, 12, 8][step]+phase+branch)
                wave.append(a)
            previous = [a['output_state_id'] for a in wave]
            waves.append({'phase': phase_name, 'step': verb, 'activity_ids': [a['id'] for a in wave],
                          'limiting_resource': ['crew', 'crane', 'material', 'workspace'][step]})
            main = activity(0, phase, f'主线{phase*6+step+2:02d}·{phase_name}·{verb}汇检',
                            [main['output_state_id'], *previous], duration=4+phase)
        terminal = activity(0, phase, f'主线{phase*6+6:02d}·{phase_name}阶段关闭',
                            [main['output_state_id'], *previous], duration=5+phase)
    s['goal_state_ids'] = [terminal['output_state_id']]
    return s, waves


def audit(s, waves):
    issues = validate_scenario(s)
    assert not issues, issues
    acts = s['activities']
    assert len(acts) == 150
    counts = Counter(a['metadata']['fixture_line'] for a in acts)
    assert counts == {'main': 30, **{f'branch_{b}': 20 for b in range(1, 7)}}
    producers = defaultdict(list)
    for a in acts:
        for sid in [a['output_state_id'], *a['additional_output_state_ids']]:
            producers[sid].append(a['id'])
        assert sum(p['relation_role'] == 'required' for p in a['preconditions']) == 7
    assert max(map(len, producers.values())) == 1, '替代生产者'
    by_id = {a['id']: a for a in acts}
    ancestors = set()

    def walk(sid):
        for aid in producers.get(sid, []):
            if aid in ancestors:
                continue
            ancestors.add(aid)
            for p in by_id[aid]['preconditions']:
                walk(p['state_id'])
    for sid in s['goal_state_ids']:
        walk(sid)
    assert len(ancestors) == 150, '存在最终目标不需要的活动'

    resource_by_kind = {r['kind']: r for r in s['resources']}
    bottlenecks = []
    lower_bound = sum(a['duration'] for a in acts if a['metadata']['fixture_line'] == 'main')
    for wave in waves:
        r = resource_by_kind[wave['limiting_resource']]
        total = sum(by_id[aid]['resource_reqs'].get(r['id'], 0) for aid in wave['activity_ids'])
        assert total > r['capacity']
        demands = {by_id[aid]['resource_reqs'][r['id']] for aid in wave['activity_ids']}
        assert len(demands) == 1
        concurrency = r['capacity'] // demands.pop()
        # Each mainline gate waits for all six branch tasks. These waves cannot
        # overlap, so their resource work lower bounds can be added.
        wave_bound = math.ceil(sum(by_id[aid]['duration'] for aid in wave['activity_ids']) / concurrency)
        lower_bound += wave_bound
        bottlenecks.append({**wave, 'resource_name': r['name'], 'simultaneous_demand': total,
                           'capacity': r['capacity'], 'max_concurrent': concurrency, 'duration_lower_bound': wave_bound})

    # A conservative witness proves that data is feasible, without fabricating a solver result.
    rows = []
    clock = 0
    for a in acts:
        rows.append({'activity_id': a['id'], 'ordinal': 1, 'start': clock, 'end': clock+a['duration']})
        clock += a['duration']
    modules = _planner_modules()
    from app.core.joint_cpsat import replay_candidate
    expanded = expand_packages(s)
    candidate, _ = replay_candidate(expanded, modules['scenario_from_dict'](expanded), rows, run_id='fixture-witness', seed=11)
    assert candidate.validator_status == 'VALID'
    assert len(candidate.executions) == 150
    # Removing any protection-restoration output must invalidate the same witness.
    import copy
    broken = copy.deepcopy(expanded)
    restorer = next(a for a in broken['activities'] if '连接与防护恢复' in a['name'])
    restorer['additional_output_state_ids'] = []
    try:
        replay_candidate(broken, modules['scenario_from_dict'](broken), rows, run_id='broken-witness', seed=11)
    except (ValueError, RuntimeError):
        restoration_needed = True
    else:
        raise AssertionError('破坏后的恢复未被实际约束')
    return {'name': s['name'], 'scenario_id': s['id'], 'activity_count': 150,
            'line_counts': dict(counts), 'required_count': 1050, 'required_mean': 7,
            'transition_count': sum(p['relation_role']=='transition' for a in acts for p in a['preconditions']),
            'delete_count': sum(len(a['delete_effect_state_ids']) for a in acts),
            'goal_ancestor_count': len(ancestors), 'alternative_producers': 0,
            'restoration_is_necessary': restoration_needed, 'witness_validator': candidate.validator_status,
            'witness_makespan': candidate.metrics.makespan, 'witness_is_optimized': False,
            'analytical_makespan_lower_bound': lower_bound,
            'bottleneck_waves': bottlenecks, 'resources': s['resources']}, rows


if __name__ == '__main__':
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('output/fixtures/mainline-150')
    out.mkdir(parents=True, exist_ok=True)
    s, waves = build()
    report, rows = audit(s, waves)
    for filename, data in [('scenario.json', s), ('audit.json', report), ('feasible-witness.json', rows)]:
        (out/filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('bottleneck_waves','resources')}, ensure_ascii=False))
