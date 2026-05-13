#!/usr/bin/env python3
"""
Schedule Report Generator — V6 (Resource Color + Border CP Mark)

Fusion of V5 features (network graph, resource gantt, utilization stats)
with border-based critical path marking (no background fill override).

Usage:
    python report_generator.py <input_json> <output_html>
"""

import json
import sys
import datetime


# Resource type → color mapping (same as V5)
RESOURCE_COLORS = {
    "SPACE_R": "#e74c3c",
    "SPACE_LIGHT": "#f1c40f",
    "SPACE_OUT": "#2ecc71",
    "SPACE_DOWN": "#f39c12",
    "SPACE_FRONT": "#1abc9c",
    "SPACE_UP": "#3498db",
    "NONE": "#95a5a6",
}

RESOURCE_LABELS = {
    "SPACE_R": "主机台右侧维护位",
    "SPACE_LIGHT": "光源工作位",
    "SPACE_OUT": "主机台中部-腔外",
    "SPACE_DOWN": "主机台中部-下腔内",
    "SPACE_FRONT": "主机台前部",
    "SPACE_UP": "主机台中部-上腔内",
    "NONE": "无特定空间",
}

RESOURCE_TAGS = {
    "SPACE_R": "tag-space_r",
    "SPACE_LIGHT": "tag-space_light",
    "SPACE_OUT": "tag-space_out",
    "SPACE_DOWN": "tag-space_down",
    "SPACE_FRONT": "tag-space_front",
    "SPACE_UP": "tag-space_up",
    "NONE": "tag-none",
}


def generate_report(input_path: str, output_path: str) -> None:
    with open(input_path) as f:
        d = json.load(f)

    schedule = d["schedule"]
    tasks = schedule["tasks"]
    cp = set(d["critical_path"])
    makespan = schedule["makespan"]

    # Build lookup
    task_by_order = {t["step_order"]: t for t in tasks}

    # Sort by start time
    tasks_sorted = sorted(tasks, key=lambda t: t["start_min"])

    # Resource usage stats (derive from assigned resources)
    resource_stats = {}
    for t in tasks:
        # Get resource type from assigned resources, fallback to NONE
        resources = t.get("resources", [])
        if resources:
            # Use first resource's code prefix to determine type
            rcode = resources[0].get("resource_code", "NONE")
            # Map resource code to resource type
            if rcode.startswith("SPACE_"):
                rtype = rcode  # e.g., SPACE_R, SPACE_OUT
            else:
                rtype = "NONE"
        else:
            rtype = "NONE"
        
        if rtype not in resource_stats:
            resource_stats[rtype] = {"count": 0, "total_min": 0, "tasks": []}
        resource_stats[rtype]["count"] += 1
        resource_stats[rtype]["total_min"] += t["duration_min"]
        resource_stats[rtype]["tasks"].append(t)

    # Determine utilization level
    max_resource_time = max(s["total_min"] for s in resource_stats.values())
    for rtype, stat in resource_stats.items():
        ratio = stat["total_min"] / max_resource_time if max_resource_time > 0 else 0
        if ratio >= 0.7:
            stat["level"] = "high"
            stat["level_emoji"] = "🔴"
            stat["level_text"] = "高"
        elif ratio >= 0.4:
            stat["level"] = "medium"
            stat["level_emoji"] = "🟠"
            stat["level_text"] = "中"
        else:
            stat["level"] = "low"
            stat["level_emoji"] = "🟢"
            stat["level_text"] = "低"
        stat["ratio"] = ratio

    # Build edges from predecessors
    edges = []
    for t in tasks:
        for pred in t.get("predecessors", []):
            edges.append((pred, t["step_order"]))

    # HTML generation
    html_parts = []

    # Head
    html_parts.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Schedule Report — Resource-Aware Critical Path</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #f5f6fa; }}
  h1 {{ color: #2c3e50; text-align: center; font-size: 28px; margin-bottom: 8px; }}
  h2 {{ color: #34495e; margin-top: 30px; border-bottom: 2px solid #3498db; padding-bottom: 10px; font-size: 18px; }}
  .subtitle {{ text-align: center; color: #666; margin-bottom: 30px; font-size: 14px; }}

  .summary {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }}
  .summary-item {{ text-align: center; }}
  .summary-value {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
  .summary-label {{ font-size: 12px; color: #7f8c8d; margin-top: 5px; }}

  .warning-box {{ padding: 16px 20px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid; }}
  .warning-box.critical {{ background: #ffebee; border-left-color: #d32f2f; }}
  .warning-box.info {{ background: #e3f2fd; border-left-color: #1976d2; }}
  .warning-box h4 {{ font-size: 14px; margin-bottom: 6px; font-weight: 600; }}
  .warning-box.critical h4 {{ color: #c62828; }}
  .warning-box.info h4 {{ color: #1565c0; }}
  .warning-box p {{ font-size: 13px; color: #555; margin: 0; }}

  #network {{ width: 100%; height: 600px; border: 1px solid #ddd; border-radius: 8px; background: white; margin-bottom: 20px; }}

  .gantt-container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow-x: auto; margin-bottom: 20px; }}
  .gantt-row {{ display: flex; align-items: center; height: 30px; margin-bottom: 2px; position: relative; }}
  .gantt-row:hover {{ background: #f8f9fa; }}
  /* CP marking: red left border, NOT red background */
  .gantt-row.cp::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: #e74c3c; border-radius: 0 2px 2px 0; z-index: 2; }}
  .gantt-label {{ width: 280px; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-right: 10px; text-align: right; flex-shrink: 0; padding-left: 8px; }}
  .gantt-bar-container {{ flex: 1; position: relative; height: 24px; background: #ecf0f1; border-radius: 4px; }}
  .gantt-bar {{ position: absolute; height: 20px; top: 2px; border-radius: 3px; font-size: 9px; color: white; display: flex; align-items: center; padding-left: 5px; overflow: hidden; white-space: nowrap; font-weight: 500; }}
  .gantt-timeline {{ display: flex; margin-left: 290px; margin-bottom: 10px; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; }}
  .timeline-mark {{ flex: 1; text-align: right; font-size: 10px; color: #7f8c8d; }}

  .resource-gantt-container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow-x: auto; margin-top: 20px; }}
  .resource-group {{ margin-bottom: 15px; }}
  .resource-header {{ display: flex; align-items: center; padding: 8px 12px; background: #f8f9fa; border-radius: 6px; margin-bottom: 8px; font-weight: 600; font-size: 14px; color: #2c3e50; }}
  .resource-tag {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11px; margin-left: 8px; font-weight: normal; }}
  .tag-space_r {{ background: #e3f2fd; color: #1976d2; }}
  .tag-space_light {{ background: #fff3e0; color: #f57c00; }}
  .tag-space_out {{ background: #e8f5e9; color: #388e3c; }}
  .tag-space_down {{ background: #fce4ec; color: #c2185b; }}
  .tag-space_up {{ background: #f3e5f5; color: #7b1fa2; }}
  .tag-space_front {{ background: #e0f2f1; color: #00796b; }}
  .tag-none {{ background: #f5f5f5; color: #757575; }}

  .stats-table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
  .stats-table th, .stats-table td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }}
  .stats-table th {{ background: #f8f9fa; font-weight: 600; color: #555; }}
  .progress-bar {{ height: 20px; background: #e0e0e0; border-radius: 10px; overflow: hidden; width: 200px; }}
  .progress-fill {{ height: 100%; border-radius: 10px; display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; color: white; font-size: 11px; font-weight: 600; }}
  .progress-fill.high {{ background: linear-gradient(90deg, #ef5350, #c62828); }}
  .progress-fill.medium {{ background: linear-gradient(90deg, #ffa726, #ef6c00); }}
  .progress-fill.low {{ background: linear-gradient(90deg, #66bb6a, #2e7d32); }}

  .legend {{ display: flex; flex-wrap: wrap; gap: 15px; margin-top: 15px; padding: 15px; background: #f8f9fa; border-radius: 8px; }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; font-size: 12px; }}
  .legend-color {{ width: 16px; height: 16px; border-radius: 3px; }}
  .legend-border {{ width: 16px; height: 16px; border-radius: 3px; border: 3px solid #e74c3c; background: transparent; }}

  .cp-chain {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 8px 0; }}
  .cp-node {{ background: linear-gradient(135deg, #ff6b6b, #ee5a5a); color: white; padding: 10px 16px; border-radius: 8px; font-weight: 600; font-size: 13px; box-shadow: 0 2px 4px rgba(231,76,60,0.3); }}
  .cp-arrow {{ color: #ccc; font-size: 18px; font-weight: 300; }}

  /* CP text marking in task labels */
  .cp-text {{ color: #e74c3c; font-weight: 600; }}
</style>
</head>
<body>
<h1>🔧 Schedule Report</h1>
<p class="subtitle">Resource-Aware Critical Path Analysis • Generated {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}</p>

<div class="summary">
  <div class="summary-grid">
    <div class="summary-item">
      <div class="summary-value">{len(tasks)}</div>
      <div class="summary-label">总活动数</div>
    </div>
    <div class="summary-item">
      <div class="summary-value">{makespan/60:.1f}h</div>
      <div class="summary-label">总工期 (Makespan)</div>
    </div>
    <div class="summary-item">
      <div class="summary-value" style="color:#e74c3c;">{len(cp)}</div>
      <div class="summary-label">关键路径活动数</div>
    </div>
    <div class="summary-item">
      <div class="summary-value">{len(resource_stats)}</div>
      <div class="summary-label">空间资源</div>
    </div>
  </div>
</div>
""")

    # CP Chain
    html_parts.append("""
<div class="gantt-container">
  <h2 style="margin-top:0;border:none;padding:0;">🔗 Critical Path Chain</h2>
  <div class="cp-chain">
""")
    for i, code in enumerate(d["critical_path"]):
        html_parts.append(f'    <div class="cp-node">{code}</div>\n')
        if i < len(d["critical_path"]) - 1:
            html_parts.append('    <span class="cp-arrow">→</span>\n')
    html_parts.append("""  </div>
</div>
""")

    # Network Graph
    html_parts.append('<h2>🔗 Activity Network</h2>\n<div id="network"></div>\n')

    # Gantt Chart
    html_parts.append('<h2>📅 Gantt Chart</h2>\n<div class="gantt-container">\n')
    html_parts.append('<div class="gantt-timeline">\n')
    for i in range(6):
        val = int(makespan * i / 5 / 60)
        html_parts.append(f'<div class="timeline-mark">{val}h</div>\n')
    html_parts.append('</div>\n')

    max_end = max(t["end_min"] for t in tasks)
    scale = 100.0 / max_end if max_end > 0 else 0

    for t in tasks_sorted:
        left = t["start_min"] * scale
        width = max(t["duration_min"] * scale, 0.5)
        rtype = t.get("resource_type", "NONE")
        color = RESOURCE_COLORS.get(rtype, "#95a5a6")
        is_cp = t["op_rule_code"] in cp
        row_class = "cp" if is_cp else ""
        cp_marker = " 🔴CP" if is_cp else ""
        
        html_parts.append(f"""<div class="gantt-row {row_class}">
  <div class="gantt-label">{t["step_order"]}. {t["op_rule_name"]} ({t["duration_min"]}min){cp_marker}</div>
  <div class="gantt-bar-container">
    <div class="gantt-bar" style="left: {left:.2f}%; width: {width:.2f}%; background: {color};">{t["op_rule_code"]}</div>
  </div>
</div>
""")

    html_parts.append('</div>\n')

    # Resource Gantt
    html_parts.append('<h2>🏭 Resource Gantt Chart</h2>\n<div class="resource-gantt-container">\n')
    
    for rtype in sorted(resource_stats.keys(), key=lambda x: -resource_stats[x]["total_min"]):
        stat = resource_stats[rtype]
        color = RESOURCE_COLORS.get(rtype, "#95a5a6")
        tag_class = RESOURCE_TAGS.get(rtype, "tag-none")
        label = RESOURCE_LABELS.get(rtype, rtype)
        
        html_parts.append(f"""<div class="resource-group">
  <div class="resource-header">
    {rtype} <span class="resource-tag {tag_class}">{label}</span>
    <span style="margin-left:auto; font-size:12px; color:#666;">{stat['count']}个活动 | 总占用{stat['total_min']/60:.1f}h | {stat['level_emoji']} {stat['level_text']}利用率</span>
  </div>
  <div class="gantt-row">
    <div class="gantt-label" style="width:180px;">{', '.join(t['op_rule_code'] for t in stat['tasks'][:8])}{'...' if len(stat['tasks']) > 8 else ''}</div>
    <div class="gantt-bar-container">
""")
        for t in stat["tasks"]:
            left = t["start_min"] * scale
            width = max(t["duration_min"] * scale, 0.5)
            is_cp = t["op_rule_code"] in cp
            cp_marker = "🔴" if is_cp else ""
            html_parts.append(f'      <div class="gantt-bar" style="left: {left:.2f}%; width: {width:.2f}%; background: {color};">{t["op_rule_code"]}{cp_marker}</div>\n')
        
        html_parts.append("""    </div>
  </div>
</div>
""")

    html_parts.append('</div>\n')

    # Resource Stats Table
    html_parts.append("""
<h2>📊 Resource Utilization</h2>
<div class="gantt-container">
<table class="stats-table">
  <thead>
    <tr>
      <th>Resource Type</th>
      <th>Activities</th>
      <th>Total Time</th>
      <th>Utilization</th>
      <th>Visualization</th>
    </tr>
  </thead>
  <tbody>
""")
    for rtype in sorted(resource_stats.keys(), key=lambda x: -resource_stats[x]["total_min"]):
        stat = resource_stats[rtype]
        tag_class = RESOURCE_TAGS.get(rtype, "tag-none")
        label = RESOURCE_LABELS.get(rtype, rtype)
        pct = int(stat["ratio"] * 100)
        
        html_parts.append(f"""    <tr>
      <td><span class="resource-tag {tag_class}">{rtype} {label}</span></td>
      <td>{stat['count']}</td>
      <td>{stat['total_min']/60:.1f}h</td>
      <td style="color:{'#c62828' if stat['level']=='high' else '#ef6c00' if stat['level']=='medium' else '#2e7d32'}; font-weight:600;">{stat['level_emoji']} {stat['level_text']}</td>
      <td><div class="progress-bar"><div class="progress-fill {stat['level']}" style="width: {pct}%">{pct}%</div></div></td>
    </tr>
""")
    
    html_parts.append("""  </tbody>
</table>
</div>
""")

    # Warnings
    html_parts.append("""
<h2>⚠️ Risk Alerts</h2>
<div class="gantt-container">
""")
    # Find bottleneck resource
    bottleneck = max(resource_stats.items(), key=lambda x: x[1]["ratio"])
    if bottleneck[1]["level"] == "high":
        html_parts.append(f"""
<div class="warning-box critical">
  <h4>🔴 {bottleneck[0]} Resource Bottleneck</h4>
  <p>{bottleneck[1]['count']} activities share "{RESOURCE_LABELS.get(bottleneck[0], bottleneck[0])}" space, utilization {int(bottleneck[1]['ratio']*100)}%. Critical path activities on this resource directly impact total makespan.</p>
</div>
""")

    # Longest activities
    longest = sorted(tasks, key=lambda t: -t["duration_min"])[:2]
    html_parts.append(f"""
<div class="warning-box critical">
  <h4>🔴 Long Duration Activities</h4>
  <p>{longest[0]['op_rule_code']} ({longest[0]['duration_min']/60:.1f}h) and {longest[1]['op_rule_code']} ({longest[1]['duration_min']/60:.1f}h) are the longest activities. Any delay on these directly extends the total makespan.</p>
</div>
""")

    html_parts.append("""
<div class="warning-box info">
  <h4>ℹ️ Critical Path Note</h4>
  <p>Critical path is computed using the new <strong>ScheduleGraph</strong> architecture, combining logical edges (from Planner) and resource edges (from Scheduler). This gives a resource-aware critical path that correctly identifies bottlenecks caused by resource contention.</p>
</div>
</div>
""")

    # Legend
    html_parts.append("""
<div class="legend">
  <div class="legend-item"><div class="legend-border"></div> Critical Path (red border)</div>
""")
    for rtype, color in RESOURCE_COLORS.items():
        if rtype != "NONE":
            html_parts.append(f'  <div class="legend-item"><div class="legend-color" style="background: {color};"></div> {rtype} ({RESOURCE_LABELS.get(rtype, rtype)})</div>\n')
    html_parts.append(f'  <div class="legend-item"><div class="legend-color" style="background: {RESOURCE_COLORS["NONE"]};"></div> No Space Constraint</div>\n')
    html_parts.append('</div>\n')

    # Footer
    html_parts.append(f"""
<div style="text-align: center; padding: 30px; color: #999; font-size: 12px;">
  Generated by ScheduleGraph Report Generator | OpenClaw Agent | {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
</div>
""")

    # Network Graph Script
    # Build vis-network data
    nodes_js = []
    for t in tasks:
        rtype = t.get("resource_type", "NONE")
        color = RESOURCE_COLORS.get(rtype, "#95a5a6")
        is_cp = t["op_rule_code"] in cp
        
        # CP nodes: thick red border, keep resource color background
        border_color = "#e74c3c" if is_cp else "#2c3e50"
        border_width = 4 if is_cp else 2
        cp_label = " 🔴" if is_cp else ""
        
        nodes_js.append(f'{{"id": {t["step_order"]}, "label": "{t["op_rule_code"]}\\n{t["op_rule_name"][:12]}{cp_label}", "title": "{t["op_rule_name"]}\\nDuration: {t["duration_min"]}min\\nResource: {rtype}{"\\n🔴 Critical Path" if is_cp else ""}", "color": {{"background": "{color}", "border": "{border_color}"}}, "borderWidth": {border_width}, "shape": "box", "font": {{"size": 10, "color": "{"white" if is_cp else "#333"}"}}}}')

    edges_js = []
    for t in tasks:
        for pred in t.get("predecessors", []):
            is_cp_edge = (task_by_order[pred]["op_rule_code"] in cp and t["op_rule_code"] in cp)
            edge_color = "#e74c3c" if is_cp_edge else "#7f8c8d"
            edge_width = 3 if is_cp_edge else 1
            edges_js.append(f'{{"from": {pred}, "to": {t["step_order"]}, "arrows": "to", "color": {{"color": "{edge_color}"}}, "width": {edge_width}}}')

    html_parts.append(f"""
<script>
const nodes = new vis.DataSet([{','.join(nodes_js)}]);
const edges = new vis.DataSet([{','.join(edges_js)}]);
const container = document.getElementById('network');
const data = {{ nodes: nodes, edges: edges }};
const options = {{
  layout: {{
    hierarchical: {{
      direction: 'LR',
      sortMethod: 'directed',
      levelSeparation: 150,
      nodeSpacing: 120
    }}
  }},
  physics: {{ enabled: false }},
  nodes: {{
    shadow: true,
    margin: 8
  }},
  edges: {{
    smooth: {{
      type: 'cubicBezier',
      forceDirection: 'horizontal'
    }}
  }}
}};
new vis.Network(container, data, options);
</script>
</body>
</html>
""")

    # Write output
    html = ''.join(html_parts)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Report generated: {output_path}")
    print(f"   File size: {len(html):,} bytes")
    print(f"   Activities: {len(tasks)}")
    print(f"   Critical path: {len(cp)} activities")
    print(f"   Resources: {len(resource_stats)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python report_generator.py <input_json> <output_html>")
        sys.exit(1)
    generate_report(sys.argv[1], sys.argv[2])
