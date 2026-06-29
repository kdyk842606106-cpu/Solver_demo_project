"""
Full pipeline: Planner + Scheduler for OPS integration.

Each OPS is a state feature. Planner derives DAG from preconditions/effects.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from app.db.session import AsyncSessionLocal
from app.db.models import (
    MachineType, Machine, MachineState, MachineStateFeature,
    StateFeatureDef, OpRule, OpRulePrecond, OpRuleEffect, OpRuleResourceReq,
    Resource,
)

BASE_ID = 9000

OPS_DATA = [
    {"code": "MS010-OPS001", "name": "集成入口条件检查", "deps": [], "duration": 7.5, "space": None},
    {"code": "MS010-OPS002", "name": "机台安装前准备", "deps": ["MS010-OPS001"], "duration": 40.5, "space": None},
    {"code": "MS010-OPS003", "name": "主机中部模块安装前准备", "deps": ["MS010-OPS002"], "duration": 33, "space": "SPACE_R"},
    {"code": "MS010-OPS004", "name": "主机中部模块安装", "deps": ["MS010-OPS003"], "duration": 56, "space": "SPACE_R"},
    {"code": "MS010-OPS005", "name": "顶部拖链模块主体安装", "deps": ["MS010-OPS004"], "duration": 15, "space": "SPACE_LIGHT"},
    {"code": "MS010-OPS006", "name": "供气盒模块安装", "deps": ["MS010-OPS005"], "duration": 29, "space": "SPACE_OUT"},
    {"code": "MS010-OPS007", "name": "中框真空系统前级管路安装", "deps": ["MS010-OPS006"], "duration": 7, "space": "SPACE_OUT"},
    {"code": "MS010-OPS008", "name": "光源导轨精调节", "deps": ["MS010-OPS004", "MS010-OPS005"], "duration": 17.2, "space": "SPACE_LIGHT"},
    {"code": "MS010-OPS009", "name": "光源连接模块安装与调节", "deps": ["MS010-OPS008"], "duration": 52, "space": "SPACE_LIGHT"},
    {"code": "MS010-OPS010", "name": "光源主体对准", "deps": ["MS010-OPS009", "MS010-OPS007"], "duration": 42, "space": "SPACE_LIGHT"},
    {"code": "MS010-OPS011", "name": "光源组件对准", "deps": ["MS010-OPS010"], "duration": 78, "space": None},
    {"code": "MS010-OPS012", "name": "动态气体开关安装", "deps": ["MS010-OPS009", "MS010-OPS004"], "duration": 35, "space": "SPACE_DOWN"},
    {"code": "MS010-OPS013", "name": "光学传感器组件安装", "deps": ["MS010-OPS012"], "duration": 16, "space": "SPACE_DOWN"},
    {"code": "MS010-OPS014", "name": "热屏蔽板安装", "deps": ["MS010-OPS013"], "duration": 23, "space": "SPACE_DOWN"},
    {"code": "MS010-OPS015", "name": "中框气体分析模块安装", "deps": ["MS010-OPS004"], "duration": 13.5, "space": "SPACE_OUT"},
    {"code": "MS010-OPS016", "name": "机械臂1推入恢复", "deps": ["MS010-OPS015", "MS010-OPS004"], "duration": 3, "space": "SPACE_OUT"},
    {"code": "MS010-OPS017", "name": "顶部计量框架安装", "deps": ["MS010-OPS004"], "duration": 19, "space": "SPACE_UP"},
    {"code": "MS010-OPS018", "name": "中框公共线缆布线", "deps": ["MS010-OPS017"], "duration": 92, "space": "SPACE_OUT"},
    {"code": "MS010-OPS019", "name": "大气机械臂2安装与调节", "deps": ["MS010-OPS018"], "duration": 32.8, "space": "SPACE_FRONT"},
    {"code": "MS010-OPS020", "name": "真空机械臂2安装与调节", "deps": ["MS010-OPS019"], "duration": 54.3, "space": "SPACE_FRONT"},
    {"code": "MS010-OPS021", "name": "机械支柱安装", "deps": ["MS010-OPS020"], "duration": 18, "space": "SPACE_OUT"},
    {"code": "MS010-OPS022", "name": "顶部运动台安装与调节", "deps": ["MS010-OPS021"], "duration": 12, "space": "SPACE_UP"},
    {"code": "MS010-OPS023", "name": "顶部拖链模块及机械支柱功能调试安装", "deps": ["MS010-OPS022"], "duration": 30, "space": "SPACE_LIGHT"},
    {"code": "MS010-OPS024", "name": "顶部区域真空抽排管路安装", "deps": ["MS010-OPS023"], "duration": 3.5, "space": "SPACE_OUT"},
    {"code": "MS010-OPS025", "name": "底部运动台安装", "deps": ["MS010-OPS014"], "duration": 53.7, "space": "SPACE_DOWN"},
    {"code": "MS010-OPS026", "name": "整机管路安装", "deps": ["MS010-OPS025", "MS010-OPS016"], "duration": 28, "space": "SPACE_OUT"},
    {"code": "MS010-OPS027", "name": "外防护安装", "deps": ["MS010-OPS026"], "duration": 96, "space": "SPACE_OUT"},
]

SPACES = {
    "SPACE_R": "主机台右侧维护位",
    "SPACE_L": "主机台左侧维护位",
    "SPACE_DOWN": "主机台中部-下腔内",
    "SPACE_LIGHT": "光源工作位",
    "SPACE_OUT": "主机台中部-腔外",
    "SPACE_FRONT": "主机台前部",
    "SPACE_UP": "主机台中部-上腔内",
}


async def setup():
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        
        # Check if already exists
        result = await session.execute(select(MachineType).where(MachineType.id == BASE_ID + 1))
        mt = result.scalar_one_or_none()
        
        if mt:
            print(f"Using existing machine_type: {mt.id}")
            result = await session.execute(select(Machine).where(Machine.id == BASE_ID + 1))
            m = result.scalar_one()
            return m.id, BASE_ID + 1, BASE_ID + 2
        
        # 1. Machine type
        mt = MachineType(
            id=BASE_ID + 1,
            code="SEMI_ASSEMBLY",
            name="半导体机台装配",
        )
        session.add(mt)
        await session.flush()

        # 2. Machine
        m = Machine(
            id=BASE_ID + 1,
            machine_type_id=mt.id,
            code="MS010",
            name="MS010 整机集成机台",
        )
        session.add(m)
        await session.flush()

        # 3. State feature defs (27 features, one per OPS)
        for i, ops in enumerate(OPS_DATA, 1):
            sf = StateFeatureDef(
                id=BASE_ID + i,
                machine_type_id=mt.id,
                feature_key=ops["code"],
                feature_name=ops["name"],
                value_type="enum",
                allowed_values='["", "done"]',
            )
            session.add(sf)
        await session.flush()

        # 4. Current state (all empty)
        cs = MachineState(
            id=BASE_ID + 1,
            machine_id=m.id,
            state_type="current",
            label="初始状态-全部待完成",
        )
        session.add(cs)

        # 5. Target state (all done)
        ts = MachineState(
            id=BASE_ID + 2,
            machine_id=m.id,
            state_type="target",
            label="目标状态-全部完成",
        )
        session.add(ts)
        await session.flush()

        # 6. State features for current (all "")
        for ops in OPS_DATA:
            csf = MachineStateFeature(
                machine_state_id=cs.id,
                feature_key=ops["code"],
                feature_value="",
            )
            session.add(csf)

        # 7. State features for target (all "done")
        for ops in OPS_DATA:
            tsf = MachineStateFeature(
                machine_state_id=ts.id,
                feature_key=ops["code"],
                feature_value="done",
            )
            session.add(tsf)
        await session.flush()

        # 8. OpRules
        op_map = {}
        for i, ops in enumerate(OPS_DATA, 1):
            op = OpRule(
                id=BASE_ID + i,
                machine_type_id=mt.id,
                code=ops["code"],
                name=ops["name"],
                duration_min=int(ops["duration"] * 60),
                is_active=True,
            )
            session.add(op)
            op_map[ops["code"]] = op.id
        await session.flush()

        # 9. Preconditions (strong dependencies -> "done")
        pc_id = BASE_ID + 1
        for ops in OPS_DATA:
            for dep in ops["deps"]:
                pc = OpRulePrecond(
                    id=pc_id,
                    op_rule_id=op_map[ops["code"]],
                    feature_key=dep,
                    operator="eq",
                    feature_value="done",
                )
                session.add(pc)
                pc_id += 1
        await session.flush()

        # 10. Effects (mark self as "done")
        ef_id = BASE_ID + 1
        for ops in OPS_DATA:
            ef = OpRuleEffect(
                id=ef_id,
                op_rule_id=op_map[ops["code"]],
                feature_key=ops["code"],
                new_value="done",
            )
            session.add(ef)
            ef_id += 1
        await session.flush()

        # 11. Resources (spaces)
        for i, (code, name) in enumerate(SPACES.items(), 1):
            r = Resource(
                id=BASE_ID + i,
                code=code,
                name=name,
                resource_type=code,
                capacity=1,
                is_available=True,
            )
            session.add(r)
        await session.flush()

        # 12. Resource requirements
        rr_id = BASE_ID + 1
        for ops in OPS_DATA:
            if ops["space"]:
                rr = OpRuleResourceReq(
                    id=rr_id,
                    op_rule_id=op_map[ops["code"]],
                    resource_type=ops["space"],
                    quantity=1,
                    is_required=True,
                )
                session.add(rr)
                rr_id += 1
        await session.flush()

        await session.commit()
        print("Setup complete!")
        print(f"  Machine: {m.id}")
        print(f"  Current state: {cs.id}")
        print(f"  Target state: {ts.id}")
        print(f"  OpRules: {len(op_map)}")

        return m.id, cs.id, ts.id


def call_solve(machine_id, current_state_id, target_state_id):
    url = "http://172.26.16.1:8000/api/v1/solve"
    payload = {
        "machine_id": machine_id,
        "current_state_id": current_state_id,
        "target_state_id": target_state_id,
        "objective": "minimize_makespan"
    }

    response = requests.post(url, json=payload, timeout=60)
    return response.json()


async def main():
    m_id, cs_id, ts_id = await setup()
    print("\nCalling solve API...")
    result = call_solve(m_id, cs_id, ts_id)
    
    print(f"\nSolve result status: {result['status']}")
    
    if result['status'] == 'done':
        print(f"Makespan: {result['schedule']['makespan']} min ({result['schedule']['makespan']/60:.1f} h)")
        print(f"\nTasks ({len(result['schedule']['tasks'])}):")
        for t in result['schedule']['tasks']:
            preds = f" (after {t['predecessors']})" if t['predecessors'] else ""
            res = ", ".join(r['resource_code'] for r in t.get('resources', [])) or "unassigned"
            print(
                f"  Step {t['step']:2d}: {t['op_code']:30s} "
                f"start={t['start']:5d} end={t['end']:5d} "
                f"dur={t['duration']:3d} res={res}{preds}"
            )
    else:
        print(f"Error code: {result.get('error_code', 'Unknown')}")
        print(f"Error message: {result.get('error_message', 'No details')}")


if __name__ == "__main__":
    asyncio.run(main())
