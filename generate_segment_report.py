import json

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def min_to_dh(m):
    d = m // (24 * 60)
    h = (m % (24 * 60)) / 60
    if d > 0:
        return f"{d}天{h:.1f}小时"
    return f"{h:.1f}小时"

def min_to_h(m):
    return f"{m/60:.1f}小时"

# Load schedule data
data = load_json('/mnt/e/Solver_demo_project/schedule_result_MS010.json')
tasks = data['schedule']['tasks']
critical_path = data['critical_path']

# Segment: from OPS003 end (4860 min) to OPS027 end
# Actually user wants from "after OPS003" to OPS027 done
segment_start = 4860  # OPS003 end
segment_end = 34158   # OPS027 end
segment_tasks = [t for t in tasks if t['step_order'] >= 4 and t['step_order'] <= 27]

# Resource colors
res_colors = {
    'SPACE_R': '#1565C0',
    'SPACE_L': '#0277BD',
    'SPACE_LIGHT': '#00838F',
    'SPACE_OUT': '#2E7D32',
    'SPACE_DOWN': '#F57C00',
    'SPACE_FRONT': '#6A1B9A',
    'SPACE_UP': '#455A64',
    'WORKER': '#37474F',
    '行吊': '#263238',
}

res_labels = {
    'SPACE_R': '主机台右侧维护位',
    'SPACE_L': '主机台左侧维护位',
    'SPACE_LIGHT': '光源工作位',
    'SPACE_OUT': '主机台中部-腔外',
    'SPACE_DOWN': '主机台中部-下腔内',
    'SPACE_FRONT': '主机台前部',
    'SPACE_UP': '主机台中部-上腔内',
    'WORKER': '工人',
    '行吊': '行吊',
}

def get_res_badge(task):
    badges = []
    for r in task.get('resources', []):
        rt = r['resource_type']
        if rt in res_colors:
            badges.append(f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;background:{res_colors[rt]};color:white;margin-right:4px;">{res_labels.get(rt, rt)}</span>')
    return ''.join(badges) if badges else '<span style="color:#999;font-size:11px;">无特定空间</span>'

def is_critical(task):
    return task['op_rule_code'] in critical_path

# Build HTML
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>MS010 分段计划报告 — 中部模块安装 → 外防护安装</title>
<style>
* {{margin:0;padding:0;box-sizing:border-box}}
body {{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;background:#f5f7fa;color:#1E293B;line-height:1.6}}
.container {{max-width:1200px;margin:0 auto;padding:20px}}
.header {{background:#fff;padding:30px;border-radius:12px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.1)}}
.header h1 {{font-size:24px;margin-bottom:8px;color:#1E293B}}
.header .meta {{font-size:13px;color:#64748B}}
.stats {{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:20px}}
.stat {{background:#fff;padding:20px;border-radius:10px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.08)}}
.stat .num {{font-size:28px;font-weight:700;color:#1565C0;margin:4px 0}}
.stat .lbl {{font-size:12px;color:#64748B}}
.section {{background:#fff;border-radius:10px;padding:24px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.08)}}
.section h2 {{font-size:16px;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #E2E8F0;color:#334155}}
table {{width:100%;border-collapse:collapse;font-size:13px}}
th,td {{padding:10px 12px;text-align:left;border-bottom:1px solid #E2E8F0}}
th {{background:#F8FAFC;font-weight:600;color:#475569;font-size:12px}}
tr:hover {{background:#F8FAFC}}
tr.critical {{border-left:3px solid #D32F2F}}
tr.critical td:first-child {{padding-left:9px}}
.gantt {{overflow-x:auto;margin-top:12px}}
.gantt-row {{display:flex;align-items:center;margin-bottom:6px;min-width:800px;height:32px}}
.gantt-label {{width:220px;flex-shrink:0;font-size:12px;color:#475569;padding-right:10px;text-align:right}}
.gantt-track {{flex:1;height:24px;background:#F1F5F9;border-radius:4px;position:relative}}
.gantt-bar {{height:100%;border-radius:4px;position:absolute;top:0;display:flex;align-items:center;padding:0 8px;font-size:11px;color:white;font-weight:500;white-space:nowrap;overflow:hidden}}
.timeline {{display:flex;justify-content:space-between;margin:12px 0;padding:8px 0;border-top:1px dashed #CBD5E1;border-bottom:1px dashed #CBD5E1;font-size:11px;color:#64748B}}
.alert {{background:#FEF3C7;border-left:3px solid #F59E0B;padding:12px 16px;border-radius:0 6px 6px 0;margin-bottom:10px;font-size:13px}}
.alert.danger {{background:#FEE2E2;border-left-color:#EF4444}}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>MS010 机台计划报告（分段）</h1>
<div class="meta">当前状态：主机中部模块安装前准备结束（OPS003完成） | 目标状态：外防护安装结束（OPS027完成） | Plan ID: 272 | Schedule ID: 275</div>
</div>

<div class="stats">
<div class="stat"><div class="lbl">分段总工期</div><div class="num">{min_to_dh(segment_end - segment_start)}</div></div>
<div class="stat"><div class="lbl">工序数量</div><div class="num">{len(segment_tasks)}</div></div>
<div class="stat"><div class="lbl">总工期（完整）</div><div class="num">{min_to_dh(data['makespan'])}</div></div>
<div class="stat"><div class="lbl">关键路径工序</div><div class="num">{len([t for t in segment_tasks if is_critical(t)])}</div></div>
</div>

<div class="section">
<h2>关键路径（本段）</h2>
<p style="font-size:13px;color:#64748B;margin-bottom:12px">从 OPS004 开始，到 OPS027 结束的关键工序链：</p>
<div style="font-family:monospace;font-size:13px;background:#F8FAFC;padding:16px;border-radius:6px;line-height:2;color:#334155">
"""

# Build critical chain for segment
for t in segment_tasks:
    if is_critical(t):
        html += f"OPS{t['step_order']:03d} {t['op_rule_name']} ({min_to_h(t['duration_min'])}) → <br>"

html = html.rstrip(" → <br>")

html += """
</div>
</div>

<div class="section">
<h2>甘特图（OPS004 → OPS027）</h2>
<div class="timeline">
<span>分段起点 (OPS003结束)</span>
<span>约 Day 8</span>
<span>约 Day 16</span>
<span>约 Day 24</span>
</div>
<div class="gantt">
"""

# Gantt chart
total_span = segment_end - segment_start
for t in sorted(segment_tasks, key=lambda x: x['start_min']):
    left = ((t['start_min'] - segment_start) / total_span) * 100
    width = (t['duration_min'] / total_span) * 100
    cp_cls = 'critical' if is_critical(t) else ''
    # bar color by primary resource
    bar_color = '#78909C'
    for r in t.get('resources', []):
        rt = r['resource_type']
        if rt in res_colors:
            bar_color = res_colors[rt]
            break
    cp_mark = ' 🔴CP' if is_critical(t) else ''
    html += f"""
<div class="gantt-row">
<div class="gantt-label">OPS{t['step_order']:03d} {t['op_rule_name'][:16]}{cp_mark}</div>
<div class="gantt-track">
<div class="gantt-bar" style="left:{left:.1f}%;width:{width:.1f}%;background:{bar_color};">{min_to_h(t['duration_min'])}</div>
</div>
</div>"""

html += """
</div>
</div>

<div class="section">
<h2>工序详情</h2>
<table>
<thead><tr>
<th>序号</th><th>工序</th><th>名称</th><th>工期</th><th>开始~结束</th><th>资源</th><th>前置</th>
</tr></thead>
<tbody>
"""

for t in sorted(segment_tasks, key=lambda x: x['step_order']):
    cp_style = 'class="critical"' if is_critical(t) else ''
    pre = ','.join([f"OPS{p:03d}" for p in t['predecessors']]) if t['predecessors'] else '-'
    rel_start = t['start_min'] - segment_start
    rel_end = t['end_min'] - segment_start
    html += f"""<tr {cp_style}>
<td><b>OPS{t['step_order']:03d}</b></td>
<td>{t['op_rule_code']}</td>
<td>{t['op_rule_name']}</td>
<td>{min_to_h(t['duration_min'])}</td>
<td>{min_to_dh(rel_start)} ~ {min_to_dh(rel_end)}</td>
<td>{get_res_badge(t)}</td>
<td>{pre}</td>
</tr>"""

html += """
</tbody>
</table>
</div>

<div class="section">
<h2>风险提示</h2>
"""

# Alerts
long_tasks = [t for t in segment_tasks if t['duration_min'] > 3000]
if long_tasks:
    html += '<div class="alert danger"><b>长工期工序：</b>' + ', '.join([f"OPS{t['step_order']:03d} ({min_to_h(t['duration_min'])})" for t in long_tasks]) + ' — 建议提前确认人力和资源</div>'

space_out_tasks = [t for t in segment_tasks if any(r['resource_type'] == 'SPACE_OUT' for r in t.get('resources', []))]
if len(space_out_tasks) > 8:
    html += f'<div class="alert danger"><b>SPACE_OUT 资源瓶颈：</b>{len(space_out_tasks)}个工序共享腔外空间，包括外防护安装(96h)，存在排队风险</div>'

html += '<div class="alert"><b>并行机会：</b>OPS004之后有4条并行分支（光源/下腔内/上腔内/腔外），合理调配可压缩总工期</div>'

html += """
</div>

<div class="section">
<h2>数据调用流程说明</h2>
<div style="font-size:13px;line-height:2;color:#475569">
<p><b>1. 用户输入解析</b> → 提取 machine_code=MS010, 当前/目标状态标签</p>
<p><b>2. 输入校验</b> → 查询 PostgreSQL 数据库(machine/machine_state/op_rule表)，确认状态和工序存在</p>
<p><b>3. 构建 RAG</b> → 读取 op_rule_precond(前置条件) + op_rule_effect(后置效果)，自动推导依赖图(plan_id=272)</p>
<p><b>4. CP-SAT 求解</b> → 输入资源约束(WORKER/行吊/空间资源)，运行 Google OR-Tools 求解最优排程(schedule_id=275)</p>
<p><b>5. 结果校验</b> → 检查 makespan>0, 任务数量, 资源冲突, 关键路径</p>
<p><b>6. 报告生成</b> → 将 schedule JSON → 甘特图/资源统计/风险分析/关键路径可视化</p>
</div>
</div>

<div style="text-align:center;padding:20px;color:#94A3B8;font-size:12px">
Generated by OpenClaw Agent | Solver Demo v0.2 | 2026-05-16
</div>
</div>
</body>
</html>
"""

with open('/mnt/e/Solver_demo_project/MS010_segment_report.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Report generated: /mnt/e/Solver_demo_project/MS010_segment_report.html")
print(f"Segment: {min_to_dh(segment_end - segment_start)} ({segment_end - segment_start} minutes)")
print(f"Tasks: {len(segment_tasks)}")
