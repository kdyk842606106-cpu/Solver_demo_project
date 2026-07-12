"""
Generate Activity Network Diagram + Gantt Chart for OPS schedule.

Creates an HTML file with:
1. Activity Network (DAG) - vis.js
2. Gantt Chart - custom HTML/CSS
"""

import json

# Schedule data from solve API
SCHEDULE = {
    "makespan": 28835,
    "tasks": [
        {"step": 1, "code": "MS010-OPS001", "name": "集成入口条件检查", "start": 0, "end": 450, "dur": 450, "res": "", "preds": []},
        {"step": 2, "code": "MS010-OPS002", "name": "机台安装前准备", "start": 450, "end": 2880, "dur": 2430, "res": "", "preds": [1]},
        {"step": 3, "code": "MS010-OPS003", "name": "主机中部模块安装前准备", "start": 2880, "end": 4860, "dur": 1980, "res": "SPACE_R", "preds": [2]},
        {"step": 4, "code": "MS010-OPS004", "name": "主机中部模块安装", "start": 4860, "end": 8220, "dur": 3360, "res": "SPACE_R", "preds": [3]},
        {"step": 5, "code": "MS010-OPS005", "name": "顶部拖链模块主体安装", "start": 8220, "end": 9120, "dur": 900, "res": "SPACE_LIGHT", "preds": [4]},
        {"step": 15, "code": "MS010-OPS015", "name": "中框气体分析模块安装", "start": 8220, "end": 9030, "dur": 810, "res": "SPACE_OUT", "preds": [4]},
        {"step": 17, "code": "MS010-OPS017", "name": "顶部计量框架安装", "start": 8220, "end": 9360, "dur": 1140, "res": "SPACE_UP", "preds": [4]},
        {"step": 16, "code": "MS010-OPS016", "name": "机械臂1推入恢复", "start": 9030, "end": 9210, "dur": 180, "res": "SPACE_OUT", "preds": [15, 4]},
        {"step": 8, "code": "MS010-OPS008", "name": "光源导轨精调节", "start": 9120, "end": 10152, "dur": 1032, "res": "SPACE_LIGHT", "preds": [4, 5]},
        {"step": 18, "code": "MS010-OPS018", "name": "中框公共线缆布线", "start": 9360, "end": 14880, "dur": 5520, "res": "SPACE_OUT", "preds": [17]},
        {"step": 9, "code": "MS010-OPS009", "name": "光源连接模块安装与调节", "start": 10152, "end": 13272, "dur": 3120, "res": "SPACE_LIGHT", "preds": [8]},
        {"step": 12, "code": "MS010-OPS012", "name": "动态气体开关安装", "start": 13272, "end": 15372, "dur": 2100, "res": "SPACE_DOWN", "preds": [9, 4]},
        {"step": 6, "code": "MS010-OPS006", "name": "供气盒模块安装", "start": 14880, "end": 16620, "dur": 1740, "res": "SPACE_OUT", "preds": [5]},
        {"step": 19, "code": "MS010-OPS019", "name": "大气机械臂2安装与调节", "start": 14880, "end": 16847, "dur": 1967, "res": "SPACE_FRONT", "preds": [18]},
        {"step": 13, "code": "MS010-OPS013", "name": "光学传感器组件安装", "start": 15372, "end": 16332, "dur": 960, "res": "SPACE_DOWN", "preds": [12]},
        {"step": 14, "code": "MS010-OPS014", "name": "热屏蔽板安装", "start": 16332, "end": 17712, "dur": 1380, "res": "SPACE_DOWN", "preds": [13]},
        {"step": 7, "code": "MS010-OPS007", "name": "中框真空系统前级管路安装", "start": 16620, "end": 17040, "dur": 420, "res": "SPACE_OUT", "preds": [6]},
        {"step": 20, "code": "MS010-OPS020", "name": "真空机械臂2安装与调节", "start": 16847, "end": 20105, "dur": 3258, "res": "SPACE_FRONT", "preds": [19]},
        {"step": 10, "code": "MS010-OPS010", "name": "光源主体对准", "start": 17040, "end": 19560, "dur": 2520, "res": "SPACE_LIGHT", "preds": [9, 7]},
        {"step": 25, "code": "MS010-OPS025", "name": "底部运动台安装", "start": 17712, "end": 20934, "dur": 3222, "res": "SPACE_DOWN", "preds": [14]},
        {"step": 21, "code": "MS010-OPS021", "name": "机械支柱安装", "start": 20105, "end": 21185, "dur": 1080, "res": "SPACE_OUT", "preds": [20]},
        {"step": 22, "code": "MS010-OPS022", "name": "顶部运动台安装与调节", "start": 21185, "end": 21905, "dur": 720, "res": "SPACE_UP", "preds": [21]},
        {"step": 26, "code": "MS010-OPS026", "name": "整机管路安装", "start": 21185, "end": 22865, "dur": 1680, "res": "SPACE_OUT", "preds": [25, 16]},
        {"step": 23, "code": "MS010-OPS023", "name": "顶部拖链模块及机械支柱功能调试安装", "start": 21905, "end": 23705, "dur": 1800, "res": "SPACE_LIGHT", "preds": [22]},
        {"step": 27, "code": "MS010-OPS027", "name": "外防护安装", "start": 22865, "end": 28625, "dur": 5760, "res": "SPACE_OUT", "preds": [26]},
        {"step": 11, "code": "MS010-OPS011", "name": "光源组件对准", "start": 24155, "end": 28835, "dur": 4680, "res": "", "preds": [10]},
        {"step": 24, "code": "MS010-OPS024", "name": "顶部区域真空抽排管路安装", "start": 28625, "end": 28835, "dur": 210, "res": "SPACE_OUT", "preds": [23]},
    ]
}

# Resource colors
RES_COLORS = {
    "": "#95a5a6",
    "SPACE_R": "#e74c3c",
    "SPACE_L": "#e67e22",
    "SPACE_DOWN": "#f39c12",
    "SPACE_LIGHT": "#f1c40f",
    "SPACE_OUT": "#2ecc71",
    "SPACE_FRONT": "#1abc9c",
    "SPACE_UP": "#3498db",
}

def generate_html():
    tasks = SCHEDULE["tasks"]
    makespan = SCHEDULE["makespan"]

    # Build nodes and edges for network diagram
    nodes = []
    for t in tasks:
        color = RES_COLORS.get(t["res"], "#95a5a6")
        nodes.append({
            "id": t["step"],
            "label": f"{t['code']}\n{t['name'][:10]}",
            "title": f"{t['name']}\nDuration: {t['dur']}min\nResource: {t['res'] or 'None'}",
            "color": {"background": color, "border": "#2c3e50"},
            "shape": "box",
            "font": {"size": 10}
        })

    edges = []
    for t in tasks:
        for pred in t["preds"]:
            edges.append({
                "from": pred,
                "to": t["step"],
                "arrows": "to",
                "color": {"color": "#7f8c8d"}
            })

    # Build Gantt chart data
    gantt_rows = []
    for t in tasks:
        left_pct = (t["start"] / makespan) * 100
        width_pct = ((t["end"] - t["start"]) / makespan) * 100
        color = RES_COLORS.get(t["res"], "#95a5a6")
        gantt_rows.append({
            "step": t["step"],
            "code": t["code"],
            "name": t["name"],
            "start": t["start"],
            "end": t["end"],
            "dur": t["dur"],
            "left": left_pct,
            "width": width_pct,
            "color": color,
            "res": t["res"] or "None"
        })

    # Generate timeline markers (every 10%)
    timeline_marks = []
    for i in range(11):
        pct = i * 10
        mins = int(makespan * (pct / 100))
        hours = mins / 60
        timeline_marks.append({"pct": pct, "label": f"{hours:.0f}h"})

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>MS010 整机集成 - 活动网络图 + 甘特图</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #f5f6fa; }}
        h1 {{ color: #2c3e50; text-align: center; }}
        h2 {{ color: #34495e; margin-top: 30px; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        .summary {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }}
        .summary-item {{ text-align: center; }}
        .summary-value {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
        .summary-label {{ font-size: 12px; color: #7f8c8d; margin-top: 5px; }}
        #network {{ width: 100%; height: 600px; border: 1px solid #ddd; border-radius: 8px; background: white; }}
        .gantt-container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow-x: auto; }}
        .gantt-row {{ display: flex; align-items: center; height: 30px; margin-bottom: 2px; }}
        .gantt-label {{ width: 280px; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-right: 10px; text-align: right; flex-shrink: 0; }}
        .gantt-bar-container {{ flex: 1; position: relative; height: 24px; background: #ecf0f1; border-radius: 4px; }}
        .gantt-bar {{ position: absolute; height: 20px; top: 2px; border-radius: 3px; font-size: 9px; color: white; display: flex; align-items: center; padding-left: 5px; overflow: hidden; white-space: nowrap; }}
        .gantt-timeline {{ display: flex; margin-left: 290px; margin-bottom: 10px; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; }}
        .timeline-mark {{ flex: 1; text-align: right; font-size: 10px; color: #7f8c8d; }}
        .legend {{ display: flex; flex-wrap: wrap; gap: 15px; margin-top: 15px; padding: 15px; background: #f8f9fa; border-radius: 8px; }}
        .legend-item {{ display: flex; align-items: center; gap: 5px; font-size: 12px; }}
        .legend-color {{ width: 16px; height: 16px; border-radius: 3px; }}
        .critical {{ background: #ffeaa7 !important; border: 2px solid #fdcb6e !important; }}
    </style>
</head>
<body>
    <h1>MS010 整机集成装配计划</h1>

    <div class="summary">
        <div class="summary-grid">
            <div class="summary-item">
                <div class="summary-value">27</div>
                <div class="summary-label">总活动数</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">480.6h</div>
                <div class="summary-label">总工期 (Makespan)</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">31</div>
                <div class="summary-label">并行组数</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">7</div>
                <div class="summary-label">空间资源</div>
            </div>
        </div>
    </div>

    <h2>1. 活动网络图 (Activity Network)</h2>
    <div id="network"></div>

    <h2>2. 甘特图 (Gantt Chart)</h2>
    <div class="gantt-container">
        <div class="gantt-timeline">
            {''.join(f'<div class="timeline-mark">{m["label"]}</div>' for m in timeline_marks)}
        </div>
        {''.join(f'''
        <div class="gantt-row">
            <div class="gantt-label">{r["step"]:2d}. {r["name"]} ({r["dur"]}min)</div>
            <div class="gantt-bar-container">
                <div class="gantt-bar" style="left: {r["left"]}%; width: {r["width"]}%; background: {r["color"]};">
                    {r["code"]}
                </div>
            </div>
        </div>
        ''' for r in gantt_rows)}
    </div>

    <div class="legend">
        <div class="legend-item"><div class="legend-color" style="background: #e74c3c;"></div>主机台右侧维护位 (SPACE_R)</div>
        <div class="legend-item"><div class="legend-color" style="background: #e67e22;"></div>主机台左侧维护位 (SPACE_L)</div>
        <div class="legend-item"><div class="legend-color" style="background: #f39c12;"></div>主机台中部-下腔内 (SPACE_DOWN)</div>
        <div class="legend-item"><div class="legend-color" style="background: #f1c40f;"></div>光源工作位 (SPACE_LIGHT)</div>
        <div class="legend-item"><div class="legend-color" style="background: #2ecc71;"></div>主机台中部-腔外 (SPACE_OUT)</div>
        <div class="legend-item"><div class="legend-color" style="background: #1abc9c;"></div>主机台前部 (SPACE_FRONT)</div>
        <div class="legend-item"><div class="legend-color" style="background: #3498db;"></div>主机台中部-上腔内 (SPACE_UP)</div>
        <div class="legend-item"><div class="legend-color" style="background: #95a5a6;"></div>无空间约束</div>
    </div>

    <script>
        // Network diagram
        const nodes = new vis.DataSet({json.dumps(nodes)});
        const edges = new vis.DataSet({json.dumps(edges)});

        const container = document.getElementById('network');
        const data = {{ nodes: nodes, edges: edges }};
        const options = {{
            layout: {{
                hierarchical: {{
                    direction: 'LR',
                    sortMethod: 'directed',
                    levelSeparation: 150,
                    nodeSpacing: 100
                }}
            }},
            physics: {{
                enabled: false
            }},
            nodes: {{
                borderWidth: 2,
                shadow: true
            }},
            edges: {{
                width: 1,
                smooth: {{
                    type: 'cubicBezier',
                    forceDirection: 'horizontal'
                }}
            }}
        }};

        new vis.Network(container, data, options);
    </script>
</body>
</html>'''

    return html

if __name__ == "__main__":
    html = generate_html()
    output_path = "E:/Solver_demo_project/scripts/ops_schedule_visualization.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Visualization saved to: {output_path}")
