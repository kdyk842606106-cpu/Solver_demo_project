"""Readable, ID-disambiguated export of the saved 8-thread 20-pair schedule."""
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/multicore-hard-20261106'
TAG = 'ranks-0-none-required-cycles-20-new-seed11-w8'


def main():
    s = json.loads((OUT/f'{TAG}-input.json').read_text(encoding='utf-8'))
    r = json.loads((OUT/f'{TAG}-result.json').read_text(encoding='utf-8'))
    acts = {a['id']: a for a in s['activities']}
    resources = {a['id']: a for a in s['resources']}
    rows = sorted(r['paths'][0]['executions'], key=lambda e: (e['start_time'], e['end_time'], e['activity_id']))
    assert len(rows) == 164 and max(e['end_time'] for e in rows) == 1955
    assert r['paths'][0]['validator_status'] == 'VALID'
    lines = ['20对必须拆卸维修：8线程主试验保存的真实排程',
             '时间为相对计划起点的分钟；总工期1955分钟（32小时35分钟）；164次执行。',
             '60秒预算结束时有解，回放VALID，尚未证明最优。重复试验的2035分钟方案不是本文来源。',
             '四组独立状态链，每组5对拆装；各组共享资源。同名活动通过组号和稳定ID区分。',
             '无工作日历；行吊全局独占、调测全局独占和精密吊装禁夜均关闭；容量资源约束仍生效。',
             '此规模压力测试未配置拆卸使下游调测/验收失效，允许验收之后继续拆装维修。', '', '资源容量：']
    lines.extend(f"  {a['name']}: {a['capacity']}" for a in resources.values())
    lines += ['', '20对拆装的实际序列（括号为起止分钟）：']
    kinds = {}
    for b in range(4):
        lines += ['', f'第{b+1}组']
        for i in range(1, 6):
            repair = acts[f'block:{b}:repair:{i}']
            name = repair['name'].removesuffix('拆后维修')
            install = next(a for a in acts.values() if a['id'].startswith(f'block:{b}:') and a['name'] == name)
            ids = {install['id']: '安装/回装', f'block:{b}:benchmark:dismantle:{i}': '拆卸', repair['id']: '维修'}
            kinds.update(ids)
            selected = [e for e in rows if e['activity_id'] in ids]
            lines.append(name + ': ' + ' → '.join(f"{ids[e['activity_id']]}#{e['ordinal']}({e['start_time']}–{e['end_time']})" for e in selected))
        end = [e for e in rows if e['activity_id'].startswith(f'block:{b}:') and acts[e['activity_id']]['name'] == '整机功能联调与验收']
        lines.extend(f"整机功能联调与验收: {e['start_time']}–{e['end_time']}" for e in end)
    counts = Counter(kinds.get(e['activity_id'], '其他装配/调测/验收') for e in rows)
    assert counts == {'安装/回装': 52, '拆卸': 32, '维修': 20, '其他装配/调测/验收': 60}
    lines += ['', '执行构成：' + '；'.join(f'{k} {v}次' for k,v in counts.items()), '', '全部164次执行（按开始时间排序）：']
    for n, e in enumerate(rows, 1):
        a = acts[e['activity_id']]
        group = int(e['activity_id'].split(':')[1]) + 1
        reqs = '、'.join(f"{resources[rid]['name']}×{qty}" for rid, qty in a.get('resource_reqs', {}).items()) or '无'
        lines.append(f"{n:03d} | {e['start_time']:4d}–{e['end_time']:4d} | 第{group}组 | {a['name']} #{e['ordinal']} | {reqs}\n      ID: {e['activity_id']}")
    target = OUT/'required-cycles-20-w8-schedule.txt'
    target.write_text('\n'.join(lines), encoding='utf-8')
    print(target)
    print(counts)


if __name__ == '__main__':
    main()
