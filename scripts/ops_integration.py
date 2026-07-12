"""
OPS Integration Script for Solver Demo.

Inserts 27 OPS activities as op_rules, creates resources (spaces),
and prepares data for solve API.

Usage:
    python scripts/ops_integration.py
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.db.models import (
    MachineType,
    Machine,
    MachineState,
    MachineStateFeature,
    StateFeatureDef,
    OpRule,
    OpRulePrecond,
    OpRuleEffect,
    OpRuleResourceReq,
    Resource,
)


# ============================================================
# OPS Data
# ============================================================

OPS_DATA = [
    {"code": "MS010-OPS001", "name": "集成入口条件检查", "deps": [], "duration": 7.5, "people": 3, "lift": None, "space": None},
    {"code": "MS010-OPS002", "name": "机台安装前准备", "deps": ["MS010-OPS001"], "duration": 40.5, "people": 5, "lift": "单钩", "space": None},
    {"code": "MS010-OPS003", "name": "主机中部模块安装前准备", "deps": ["MS010-OPS002"], "duration": 33, "people": 3, "lift": "四钩", "space": "SPACE_R"},
    {"code": "MS010-OPS004", "name": "主机中部模块安装", "deps": ["MS010-OPS003"], "duration": 56, "people": 5, "lift": "四钩", "space": "SPACE_R"},
    {"code": "MS010-OPS005", "name": "顶部拖链模块主体安装", "deps": ["MS010-OPS004"], "duration": 15, "people": 4, "lift": "双钩", "space": "SPACE_LIGHT"},
    {"code": "MS010-OPS006", "name": "供气盒模块安装", "deps": ["MS010-OPS005"], "duration": 29, "people": 3, "lift": "双钩", "space": "SPACE_OUT"},
    {"code": "MS010-OPS007", "name": "中框真空系统前级管路安装", "deps": ["MS010-OPS006"], "duration": 7, "people": 3, "lift": None, "space": "SPACE_OUT"},
    {"code": "MS010-OPS008", "name": "光源导轨精调节", "deps": ["MS010-OPS004", "MS010-OPS005"], "duration": 17.2, "people": 5, "lift": None, "space": "SPACE_LIGHT"},
    {"code": "MS010-OPS009", "name": "光源连接模块安装与调节", "deps": ["MS010-OPS008"], "duration": 52, "people": 5, "lift": "双钩", "space": "SPACE_LIGHT"},
    {"code": "MS010-OPS010", "name": "光源主体对准", "deps": ["MS010-OPS009", "MS010-OPS007"], "duration": 42, "people": 5, "lift": None, "space": "SPACE_LIGHT"},
    {"code": "MS010-OPS011", "name": "光源组件对准", "deps": ["MS010-OPS010"], "duration": 78, "people": 4, "lift": None, "space": None},
    {"code": "MS010-OPS012", "name": "动态气体开关安装", "deps": ["MS010-OPS009", "MS010-OPS004"], "duration": 35, "people": 3, "lift": None, "space": "SPACE_DOWN"},
    {"code": "MS010-OPS013", "name": "光学传感器组件安装", "deps": ["MS010-OPS012"], "duration": 16, "people": 4, "lift": "单钩", "space": "SPACE_DOWN"},
    {"code": "MS010-OPS014", "name": "热屏蔽板安装", "deps": ["MS010-OPS013"], "duration": 23, "people": 4, "lift": None, "space": "SPACE_DOWN"},
    {"code": "MS010-OPS015", "name": "中框气体分析模块安装", "deps": ["MS010-OPS004"], "duration": 13.5, "people": 4, "lift": "四钩", "space": "SPACE_OUT"},
    {"code": "MS010-OPS016", "name": "机械臂1推入恢复", "deps": ["MS010-OPS015", "MS010-OPS004"], "duration": 3, "people": 3, "lift": None, "space": "SPACE_OUT"},
    {"code": "MS010-OPS017", "name": "顶部计量框架安装", "deps": ["MS010-OPS004"], "duration": 19, "people": 4, "lift": "双钩", "space": "SPACE_UP"},
    {"code": "MS010-OPS018", "name": "中框公共线缆布线", "deps": ["MS010-OPS017"], "duration": 92, "people": 5, "lift": None, "space": "SPACE_OUT"},
    {"code": "MS010-OPS019", "name": "大气机械臂2安装与调节", "deps": ["MS010-OPS018"], "duration": 32.8, "people": 4, "lift": "双钩", "space": "SPACE_FRONT"},
    {"code": "MS010-OPS020", "name": "真空机械臂2安装与调节", "deps": ["MS010-OPS019"], "duration": 54.3, "people": 4, "lift": "双钩", "space": "SPACE_FRONT"},
    {"code": "MS010-OPS021", "name": "机械支柱安装", "deps": ["MS010-OPS020"], "duration": 18, "people": 3, "lift": "单钩", "space": "SPACE_OUT"},
    {"code": "MS010-OPS022", "name": "顶部运动台安装与调节", "deps": ["MS010-OPS021"], "duration": 12, "people": 4, "lift": "四钩", "space": "SPACE_UP"},
    {"code": "MS010-OPS023", "name": "顶部拖链模块及机械支柱功能调试安装", "deps": ["MS010-OPS022"], "duration": 30, "people": 4, "lift": "双钩", "space": "SPACE_LIGHT"},
    {"code": "MS010-OPS024", "name": "顶部区域真空抽排管路安装", "deps": ["MS010-OPS023"], "duration": 3.5, "people": 3, "lift": "双钩", "space": "SPACE_OUT"},
    {"code": "MS010-OPS025", "name": "底部运动台安装", "deps": ["MS010-OPS014"], "duration": 53.7, "people": 5, "lift": "双钩", "space": "SPACE_DOWN"},
    {"code": "MS010-OPS026", "name": "整机管路安装", "deps": ["MS010-OPS025", "MS010-OPS016"], "duration": 28, "people": 4, "lift": "单钩", "space": "SPACE_OUT"},
    {"code": "MS010-OPS027", "name": "外防护安装", "deps": ["MS010-OPS026"], "duration": 96, "people": 3, "lift": "单钩", "space": "SPACE_OUT"},
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

# Base ID offset to avoid conflicts with existing data
BASE_ID = 9000


async def create_machine_type(session: AsyncSession) -> int:
    """Create a new machine type for this scenario."""
    mt = MachineType(
        id=BASE_ID + 1,
        code="SEMI_ASSEMBLY",
        name="半导体机台装配",
        description="半导体机台整机集成装配线",
    )
    session.add(mt)
    await session.flush()
    return mt.id


async def create_machine(session: AsyncSession, machine_type_id: int) -> int:
    """Create a new machine instance."""
    m = Machine(
        id=BASE_ID + 1,
        machine_type_id=machine_type_id,
        code="MS010",
        name="MS010 整机集成机台",
        location="Fab 装配车间",
    )
    session.add(m)
    await session.flush()
    return m.id


async def create_resources(session: AsyncSession) -> dict[str, int]:
    """Create space resources."""
    resource_map = {}
    for i, (code, name) in enumerate(SPACES.items(), start=1):
        r = Resource(
            id=BASE_ID + i,
            code=code,
            name=name,
            resource_type=code,
            capacity=1,
            is_available=True,
        )
        session.add(r)
        resource_map[code] = r.id
    await session.flush()
    return resource_map


async def create_states(session: AsyncSession, machine_id: int) -> tuple[int, int]:
    """Create current and target states."""
    # Current state: all OPS pending
    current_state = MachineState(
        id=BASE_ID + 1,
        machine_id=machine_id,
        state_type="current",
        label="初始状态-全部待完成",
    )
    session.add(current_state)

    # Target state: all OPS done
    target_state = MachineState(
        id=BASE_ID + 2,
        machine_id=machine_id,
        state_type="target",
        label="目标状态-全部完成",
    )
    session.add(target_state)
    await session.flush()

    return current_state.id, target_state.id


async def create_op_rules(session: AsyncSession, machine_type_id: int) -> dict[str, int]:
    """Create op_rules for all 27 OPS."""
    op_rule_map = {}

    for i, ops in enumerate(OPS_DATA, start=1):
        op = OpRule(
            id=BASE_ID + i,
            machine_type_id=machine_type_id,
            code=ops["code"],
            name=ops["name"],
            duration_min=int(ops["duration"] * 60),  # hours to minutes
            description=f"人数:{ops['people']}, 吊装:{ops['lift'] or '无'}",
            is_active=True,
        )
        session.add(op)
        op_rule_map[ops["code"]] = op.id

    await session.flush()
    return op_rule_map


async def create_preconditions(
    session: AsyncSession,
    op_rule_map: dict[str, int],
):
    """Create preconditions (strong dependencies)."""
    precond_id = BASE_ID + 1

    for ops in OPS_DATA:
        op_id = op_rule_map[ops["code"]]
        for dep_code in ops["deps"]:
            dep_id = op_rule_map[dep_code]

            # Create a feature-based precondition
            # We use a synthetic feature "ops_done" with value being the dep code
            precond = OpRulePrecond(
                id=precond_id,
                op_rule_id=op_id,
                feature_key="ops_done",
                operator="eq",
                feature_value=dep_code,
            )
            session.add(precond)
            precond_id += 1

    await session.flush()


async def create_effects(
    session: AsyncSession,
    op_rule_map: dict[str, int],
):
    """Create effects (mark this OPS as done)."""
    effect_id = BASE_ID + 1

    for ops in OPS_DATA:
        op_id = op_rule_map[ops["code"]]

        effect = OpRuleEffect(
            id=effect_id,
            op_rule_id=op_id,
            feature_key="ops_done",
            new_value=ops["code"],
        )
        session.add(effect)
        effect_id += 1

    await session.flush()


async def create_resource_reqs(
    session: AsyncSession,
    op_rule_map: dict[str, int],
):
    """Create resource requirements (space constraints)."""
    req_id = BASE_ID + 1

    for ops in OPS_DATA:
        if ops["space"]:
            op_id = op_rule_map[ops["code"]]

            req = OpRuleResourceReq(
                id=req_id,
                op_rule_id=op_id,
                resource_type=ops["space"],
                quantity=1,
                is_required=True,
            )
            session.add(req)
            req_id += 1

    await session.flush()


async def main():
    """Main entry point."""
    async with AsyncSessionLocal() as session:
        print("Creating machine type...")
        mt_id = await create_machine_type(session)

        print("Creating machine...")
        m_id = await create_machine(session, mt_id)

        print("Creating resources (spaces)...")
        resource_map = await create_resources(session)

        print("Creating states...")
        current_state_id, target_state_id = await create_states(session, m_id)

        print("Creating op_rules (27 OPS)...")
        op_rule_map = await create_op_rules(session, mt_id)

        print("Creating preconditions...")
        await create_preconditions(session, op_rule_map)

        print("Creating effects...")
        await create_effects(session, op_rule_map)

        print("Creating resource requirements...")
        await create_resource_reqs(session, op_rule_map)

        await session.commit()

        print(f"\n✅ Done!")
        print(f"   Machine ID: {m_id}")
        print(f"   Current State ID: {current_state_id}")
        print(f"   Target State ID: {target_state_id}")
        print(f"   OpRules: {len(op_rule_map)} created")
        print(f"   Resources: {len(resource_map)} spaces created")

        return m_id, current_state_id, target_state_id


if __name__ == "__main__":
    m_id, cs_id, ts_id = asyncio.run(main())
    print(f"\nExport for API call:")
    print(f'  "machine_id": {m_id},')
    print(f'  "current_state_id": {cs_id},')
    print(f'  "target_state_id": {ts_id},')
    print(f'  "objective": "minimize_makespan"')
