import json

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def min_to_dh(m):
    d = m // (24 * 60)
    h = (m % (24 * 60)) / 60
    if d > 0:
        return f"{d}d {h:.1f}h"
    return f"{h:.1f}h"

def min_to_h(m):
    return f"{m/60:.1f}h"

# Resource color mapping per skill spec
RES_COLORS = {
    'SPACE_R': '#1565C0',
    'SPACE_L': '#0277BD',
    'SPACE_LIGHT': '#00838F',
    'SPACE_OUT': '#2E7D32',
    'SPACE_DOWN': '#F57C00',
    'SPACE_FRONT': '#6A1B9A',
    'SPACE_UP': '#455A64',
    'WORKER': '#37474F',
    '行吊': '#263238',
    'CRANE': '#263238',
    'NONE': '#78909C',
}

RES_LABELS = {
    'SPACE_R': '主机台右侧维护位',
    'SPACE_L': '主机台左侧维护位',
    'SPACE_LIGHT': '光源工作位',
    'SPACE_OUT': '主机台中部-腔外',
    'SPACE_DOWN': '主机台中部-下腔内',
    'SPACE_FRONT': '主机台前部',
    'SPACE_UP': '主机台中部-上腔内',
    'WORKER': '工人',
    '行吊': '行吊',
    'CRANE': '行吊',
    'NONE': '无特定空间',
}

# Load schedule data
data = load_json('/mnt/e/Solver_demo_project/schedule_result_MS010_288.json')
tasks = data['tasks']
critical_path = data['critical_path']
makespan = data['makespan']

# Full plan
total_tasks = len(tasks)
cp_count = len([t for t in tasks if t['op_rule_code'] in critical_path])

# Segment: from OPS004 end (8220 min) to OPS027 end
segment_start = 8220
segment_end = 34158
segment_tasks = [t for t in tasks if t['step_order'] >= 5 and t['step_order'] <= 27]

# Build resource utilization
res_usage = {}
for t in tasks:
    for r in t.get('resources', []):
        rt = r['resource_type']
        if rt not in res_usage:
            res_usage[rt] = {'total_min': 0, 'tasks': 0}
        res_usage[rt]['total_min'] += t['duration_min']
        res_usage[rt]['tasks'] += 1

# Calculate utilization
for rt, info in res_usage.items():
    info['utilization'] = min(100, round((info['total_min'] / makespan) * 100))
    if info['utilization'] >= 70:
        info['level'] = 'HIGH'
    elif info['utilization'] >= 40:
        info['level'] = 'MED'
    else:
        info['level'] = 'LOW'

# Build vis-network data for activity network
nodes_js = []
edges_js = []

for t in segment_tasks:
    # Determine node color based on SPACE resource only (not WORKER or 行吊)
    space_resources = [r for r in t.get('resources', []) if r['resource_type'].startswith('SPACE_')]
    if space_resources:
        node_color = RES_COLORS.get(space_resources[0]['resource_type'], '#78909C')
    else:
        node_color = '#78909C'  # default gray for no space resource

    # Critical path border
    is_cp = t['op_rule_code'] in critical_path
    border_width = 3 if is_cp else 1
    border_color = '#D32F2F' if is_cp else '#1E293B'

    label = f"OPS{t['step_order']:03d}\\n{t['op_rule_name'][:12]}"
    title = f"{t['op_rule_name']}\\nDuration: {min_to_h(t['duration_min'])}"

    nodes_js.append({
        'id': t['step_order'],
        'label': label,
        'title': title,
        'color': {'background': node_color, 'border': border_color},
        'borderWidth': border_width,
        'shape': 'box',
        'font': {'color': 'white', 'size': 11, 'multi': 'html'},
        'margin': 10,
        'widthConstraint': {'minimum': 120, 'maximum': 140},
        'heightConstraint': {'minimum': 45},
        'shadow': {'enabled': False}
    })

    for p in t.get('predecessors', []):
        if 4 <= p <= 27:
            edges_js.append({
                'from': p,
                'to': t['step_order'],
                'arrows': 'to',
                'color': {'color': '#94A3B8'},
                'width': 2
            })

# Serialize for JS
nodes_js_str = json.dumps(nodes_js)
edges_js_str = json.dumps(edges_js)

# Build HTML with Light Industrial Minimalist theme
html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MS010 Schedule Report - Segment OPS004 to OPS027</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
    background: #FFFFFF;
    color: #1E293B;
    line-height: 1.6;
    font-size: 14px;
}}
.container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}

/* Header */
.header {{
    background: #FFFFFF;
    border-bottom: 2px solid #1E293B;
    padding: 20px 0;
    margin-bottom: 24px;
}}
.header h1 {{ font-size: 20px; font-weight: 600; margin-bottom: 6px; color: #1E293B; }}
.header .meta {{ font-size: 12px; color: #64748B; }}

/* Section */
.section {{
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 4px;
    padding: 20px;
    margin-bottom: 20px;
}}
.section h2 {{
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid #E2E8F0;
    color: #334155;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* Stats grid */
.stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
}}
.stat-card {{
    border: 1px solid #E2E8F0;
    border-radius: 4px;
    padding: 16px;
    text-align: center;
}}
.stat-value {{
    font-size: 24px;
    font-weight: 700;
    color: #1E293B;
    margin: 4px 0;
}}
.stat-label {{ font-size: 11px; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; }}

/* Tables */
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #E2E8F0; }}
th {{
    background: #F8FAFC;
    font-weight: 600;
    color: #475569;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
tr:hover {{ background: #F8FAFC; }}
tr.critical {{ border-left: 3px solid #D32F2F; }}
tr.critical td:first-child {{ padding-left: 9px; }}

/* Gantt */
.gantt-wrapper {{ overflow-x: auto; margin-top: 12px; }}
.gantt-row {{
    display: flex;
    align-items: center;
    margin-bottom: 4px;
    min-width: 900px;
    height: 28px;
}}
.gantt-row.critical {{ border-left: 3px solid #D32F2F; padding-left: 6px; }}
.gantt-label {{
    width: 240px;
    flex-shrink: 0;
    font-size: 11px;
    color: #475569;
    padding-right: 10px;
    text-align: right;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.gantt-track {{
    flex: 1;
    height: 20px;
    background: #F1F5F9;
    border-radius: 2px;
    position: relative;
}}
.gantt-bar {{
    height: 100%;
    border-radius: 2px;
    position: absolute;
    top: 0;
    display: flex;
    align-items: center;
    padding: 0 6px;
    font-size: 10px;
    color: white;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
}}
.gantt-timeline {{
    display: flex;
    justify-content: space-between;
    margin: 8px 0;
    padding: 6px 0;
    border-top: 1px dashed #CBD5E1;
    border-bottom: 1px dashed #CBD5E1;
    font-size: 10px;
    color: #64748B;
    min-width: 900px;
}}

/* Resource badges */
.res-badge {{
    display: inline-block;
    padding: 2px 6px;
    border-radius: 2px;
    font-size: 10px;
    margin-right: 4px;
    color: white;
    font-weight: 500;
}}

/* Critical path chain */
.cp-chain {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    font-size: 12px;
}}
.cp-node {{
    border: 1px solid #1E293B;
    padding: 8px 12px;
    border-radius: 4px;
    background: #FFFFFF;
    font-weight: 500;
}}
.cp-node.critical {{ border: 2px solid #D32F2F; }}
.cp-arrow {{ color: #64748B; font-size: 14px; }}

/* Risk alerts */
.alert {{
    border-left: 3px solid #F59E0B;
    background: #FEF3C7;
    padding: 12px 16px;
    border-radius: 0 4px 4px 0;
    margin-bottom: 10px;
    font-size: 13px;
}}
.alert.danger {{ border-left-color: #EF4444; background: #FEE2E2; }}
.alert.info {{ border-left-color: #3B82F6; background: #DBEAFE; }}
.alert-title {{ font-weight: 600; margin-bottom: 4px; display: block; }}

/* Progress bars */
.progress-bar {{
    height: 8px;
    background: #E2E8F0;
    border-radius: 4px;
    overflow: hidden;
    width: 120px;
}}
.progress-fill {{
    height: 100%;
    background: #1E293B;
    border-radius: 4px;
}}
.level-high {{ color: #D32F2F; font-weight: 600; }}
.level-med {{ color: #F57C00; font-weight: 600; }}
.level-low {{ color: #2E7D32; font-weight: 600; }}

/* Legend */
.legend-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 8px;
}}
.legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 12px; }}
.legend-color {{ width: 16px; height: 16px; border-radius: 2px; }}
.legend-cp {{ width: 16px; height: 16px; border-left: 3px solid #D32F2F; background: #F8FAFC; }}

/* Resource Gantt */
.res-group {{
    margin-bottom: 16px;
    border: 1px solid #E2E8F0;
    border-radius: 4px;
    overflow: hidden;
}}
.res-group-header {{
    background: #F8FAFC;
    padding: 8px 12px;
    font-size: 12px;
    font-weight: 600;
    color: #475569;
    border-bottom: 1px solid #E2E8F0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
.res-group-body {{ padding: 8px; }}
</style>
</head>
<body>
<div class="container">

<!-- Header -->
<div class="header">
    <h1>MS010 SCHEDULE REPORT</h1>
    <div class="meta">
        SEGMENT: OPS004 (Host Mid-Module Install) to OPS027 (Outer Shield Install) &nbsp;|&nbsp;
        PLAN ID: 272 &nbsp;|&nbsp; SCHEDULE ID: 275 &nbsp;|&nbsp; STATUS: OPTIMAL &nbsp;|&nbsp; SOLVER: OR-Tools CP-SAT
    </div>
</div>

<!-- Summary Stats -->
<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-label">Segment Duration</div>
        <div class="stat-value">{min_to_dh(segment_end - segment_start)}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Full Plan Duration</div>
        <div class="stat-value">{min_to_dh(makespan)}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Activities</div>
        <div class="stat-value">{len(segment_tasks)}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Critical Path</div>
        <div class="stat-value">{cp_count}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Parallel Groups</div>
        <div class="stat-value">{len(data.get('parallel_groups', []))}</div>
    </div>
</div>

<!-- Critical Path Chain -->
<div class="section">
    <h2>Critical Path Chain</h2>
    <div class="cp-chain">
"""

# Build CP chain
chain_parts = []
for t in tasks:
    if t['op_rule_code'] in critical_path:
        cp_class = 'critical' if t['step_order'] >= 4 and t['step_order'] <= 27 else ''
        chain_parts.append(f'<div class="cp-node {cp_class}">{t["op_rule_code"]}<br><span style="font-size:10px;color:#64748B">{min_to_h(t["duration_min"])}</span></div>')

html += '<span class="cp-arrow">&rarr;</span>\n'.join(chain_parts)

html += """
    </div>
</div>

<!-- Activity Network -->
<div class="section">
    <h2>Activity Network</h2>
    <div id="activity-network" style="height: 600px; border: 1px solid #E2E8F0;"></div>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <script type="text/javascript">
        var nodes = new vis.DataSet(""" + nodes_js_str + """);
        var edges = new vis.DataSet(""" + edges_js_str + """);
        var container = document.getElementById('activity-network');
        var data = {nodes: nodes, edges: edges};
        var options = {
            layout: {
                hierarchical: {
                    direction: 'LR',
                    sortMethod: 'directed',
                    shakeTowards: 'roots',
                    levelSeparation: 200,
                    nodeSpacing: 160
                }
            },
            physics: {
                enabled: false
            },
            nodes: {
                font: {multi: 'html'}
            },
            edges: {
                smooth: false,
                arrows: {
                    to: {enabled: true, scaleFactor: 0.5}
                },
                color: {
                    color: '#94A3B8',
                    highlight: '#1E293B'
                },
                width: 2
            },
            interaction: {
                hover: true,
                tooltipDelay: 200
            }
        };
        var network = new vis.Network(container, data, options);
    </script>
</div>

<!-- Gantt Timeline -->
<div class="section">
    <h2>Gantt Timeline</h2>
    <div class="gantt-timeline">
        <span>0h (Segment Start)</span>
        <span>""" + min_to_dh((segment_end - segment_start) * 0.25) + """</span>
        <span>""" + min_to_dh((segment_end - segment_start) * 0.5) + """</span>
        <span>""" + min_to_dh((segment_end - segment_start) * 0.75) + """</span>
        <span>""" + min_to_dh(segment_end - segment_start) + """ (Segment End)</span>
    </div>
    <div class="gantt-wrapper">
"""

# Gantt chart
for t in sorted(segment_tasks, key=lambda x: x['start_min']):
    left = ((t['start_min'] - segment_start) / (segment_end - segment_start)) * 100
    width = (t['duration_min'] / (segment_end - segment_start)) * 100
    cp_class = 'critical' if t['op_rule_code'] in critical_path else ''

    # Primary resource color
    bar_color = '#78909C'
    for r in t.get('resources', []):
        rt = r['resource_type']
        if rt in RES_COLORS:
            bar_color = RES_COLORS[rt]
            break

    cp_text = ' [CP]' if t['op_rule_code'] in critical_path else ''
    label_text = f"[{t['step_order']:02d}] {t['op_rule_name'][:22]}{cp_text}"

    html += f"""
        <div class="gantt-row {cp_class}">
            <div class="gantt-label">{label_text}</div>
            <div class="gantt-track">
                <div class="gantt-bar" style="left:{left:.1f}%;width:{max(width, 1):.1f}%;background:{bar_color};">{min_to_h(t['duration_min'])}</div>
            </div>
        </div>
"""

html += """
    </div>
</div>

<!-- Resource Gantt -->
<div class="section">
    <h2>Resource Gantt</h2>
"""

# Group tasks by resource type
res_tasks = {}
for t in tasks:
    for r in t.get('resources', []):
        rt = r['resource_type']
        if rt not in res_tasks:
            res_tasks[rt] = []
        res_tasks[rt].append(t)

for rt in sorted(res_tasks.keys(), key=lambda x: -len(res_tasks[x])):
    color = RES_COLORS.get(rt, '#78909C')
    label = RES_LABELS.get(rt, rt)
    r_tasks = sorted(res_tasks[rt], key=lambda x: x['start_min'])

    html += f"""
    <div class="res-group">
        <div class="res-group-header" style="border-left: 4px solid {color};">
            {label} ({len(r_tasks)} activities)
        </div>
        <div class="res-group-body">
            <div class="gantt-wrapper">
"""
    for t in r_tasks:
        if t['step_order'] < 4 or t['step_order'] > 27:
            continue
        left = (t['start_min'] / makespan) * 100
        width = (t['duration_min'] / makespan) * 100
        cp_class = 'critical' if t['op_rule_code'] in critical_path else ''
        cp_text = ' [CP]' if t['op_rule_code'] in critical_path else ''
        html += f"""
                <div class="gantt-row {cp_class}">
                    <div class="gantt-label">[{t['step_order']:02d}] {t['op_rule_name'][:22]}{cp_text}</div>
                    <div class="gantt-track">
                        <div class="gantt-bar" style="left:{left:.1f}%;width:{max(width, 0.5):.1f}%;background:{color};">{min_to_h(t['duration_min'])}</div>
                    </div>
                </div>
"""
    html += """
            </div>
        </div>
    </div>
"""

html += "</div>"

# Resource Utilization Table
html += """
<!-- Resource Utilization -->
<div class="section">
    <h2>Resource Utilization</h2>
    <table>
        <thead>
            <tr>
                <th>Resource Type</th>
                <th>Activities</th>
                <th>Total Time</th>
                <th>Utilization</th>
                <th>Level</th>
                <th>Visual</th>
            </tr>
        </thead>
        <tbody>
"""

for rt in sorted(res_usage.keys(), key=lambda x: -res_usage[x]['utilization']):
    info = res_usage[rt]
    color = RES_COLORS.get(rt, '#78909C')
    label = RES_LABELS.get(rt, rt)
    level_class = f"level-{info['level'].lower()}"
    html += f"""
            <tr>
                <td><span class="res-badge" style="background:{color};">{label}</span></td>
                <td>{info['tasks']}</td>
                <td>{min_to_h(info['total_min'])}</td>
                <td>{info['utilization']}%</td>
                <td class="{level_class}">{info['level']}</td>
                <td><div class="progress-bar"><div class="progress-fill" style="width:{info['utilization']}%"></div></div></td>
            </tr>
"""

html += """
        </tbody>
    </table>
</div>
"""

# Task Details Table
html += """
<!-- Task Details -->
<div class="section">
    <h2>Activity Details</h2>
    <table>
        <thead>
            <tr>
                <th>Step</th>
                <th>Code</th>
                <th>Name</th>
                <th>Duration</th>
                <th>Start</th>
                <th>End</th>
                <th>Resources</th>
                <th>Predecessors</th>
            </tr>
        </thead>
        <tbody>
"""

for t in sorted(segment_tasks, key=lambda x: x['step_order']):
    cp_class = 'critical' if t['op_rule_code'] in critical_path else ''

    # Resource badges - show ALL required resources (resource_reqs), not just assigned (resources)
    badges = []
    for req in t.get('resource_reqs', []):
        rt = req['resource_type']
        # Check if this resource was actually assigned
        assigned = any(r['resource_type'] == rt for r in t.get('resources', []))
        if rt in RES_COLORS:
            # If not assigned, show with dashed border to indicate missing assignment
            style = f"background:{RES_COLORS[rt]};"
            if not assigned:
                style += "border: 1.5px dashed #D32F2F;opacity:0.7;"
            badges.append(f'<span class="res-badge" style="{style}">{RES_LABELS.get(rt, rt)} x{req["quantity"]}</span>')

    pre = ', '.join([str(p) for p in t['predecessors']]) if t['predecessors'] else '-'

    html += f"""
            <tr class="{cp_class}">
                <td><b>{t['step_order']}</b></td>
                <td>{t['op_rule_code']}</td>
                <td>{t['op_rule_name']}</td>
                <td>{min_to_h(t['duration_min'])}</td>
                <td>{min_to_dh(t['start_min'])}</td>
                <td>{min_to_dh(t['end_min'])}</td>
                <td>{''.join(badges)}</td>
                <td>{pre}</td>
            </tr>
"""

html += """
        </tbody>
    </table>
</div>
"""

# Risk Alerts
html += """
<!-- Risk Alerts -->
<div class="section">
    <h2>Risk Alerts</h2>
"""

# Long duration activities
long_acts = [t for t in segment_tasks if t['duration_min'] > 2400]
if long_acts:
    html += '<div class="alert danger"><span class="alert-title">LONG DURATION ACTIVITIES</span>'
    html += ', '.join([f"OPS{t['step_order']:03d} {t['op_rule_name']} ({min_to_h(t['duration_min'])})" for t in long_acts])
    html += ' — Verify resource availability and staffing plans.</div>'

# Resource bottleneck
space_out_count = len([t for t in segment_tasks if any(r['resource_type'] == 'SPACE_OUT' for r in t.get('resources', []))])
if space_out_count > 6:
    html += f'<div class="alert danger"><span class="alert-title">SPACE_OUT BOTTLENECK</span>'
    html += f'{space_out_count} activities require SPACE_OUT (Host Mid-Out). '
    html += f'OPS027 Outer Shield Install ({min_to_h(5760)}) is the longest. Consider resource augmentation or task splitting.</div>'

# Parallel opportunity
html += '<div class="alert info"><span class="alert-title">PARALLEL OPPORTUNITY</span>'
html += 'After OPS004, 4 parallel branches emerge (Light Source / Down Chamber / Up Chamber / Out Chamber). '
html += 'Optimal worker allocation across these branches minimizes total makespan.</div>'

# Critical path sensitivity
html += '<div class="alert"><span class="alert-title">CRITICAL PATH SENSITIVITY</span>'
html += 'Critical path spans 20 activities. Any delay in CP activities directly impacts segment completion. '
html += 'Monitor OPS004, OPS009, OPS020, OPS027 closely.</div>'

html += """
</div>

<!-- Legend -->
<div class="section">
    <h2>Legend</h2>
    <div class="legend-grid">
"""

for rt, color in RES_COLORS.items():
    if rt != 'NONE':
        html += f"""
        <div class="legend-item">
            <div class="legend-color" style="background:{color};"></div>
            <span>{RES_LABELS.get(rt, rt)}</span>
        </div>
"""

html += """
        <div class="legend-item">
            <div class="legend-cp"></div>
            <span>Critical Path Activity (Red Left Border)</span>
        </div>
    </div>
</div>

<div style="text-align:center;padding:20px;color:#94A3B8;font-size:11px;border-top:1px solid #E2E8F0;margin-top:20px;">
    MS010 SEGMENT REPORT | PLAN 278 | SCHEDULE 288 | OR-Tools CP-SAT | Generated 2026-05-16
</div>

</div>
</body>
</html>
"""

with open('/mnt/e/Solver_demo_project/MS010_schedule_report_skill.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Report generated: /mnt/e/Solver_demo_project/MS010_schedule_report_skill.html")
print(f"Segment: {min_to_dh(segment_end - segment_start)}")
print(f"Full plan: {min_to_dh(makespan)}")
print(f"Tasks in segment: {len(segment_tasks)}")
