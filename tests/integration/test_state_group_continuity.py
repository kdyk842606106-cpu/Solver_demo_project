"""Integration coverage for state-package continuity scheduling."""

import pytest

from app.db.models import (
    ActivityNode,
    ActivityPackageAtomicRef,
    AtomicActivity,
    Machine,
    MachineState,
    MachineStateFeature,
    MachineType,
    MaintenanceIntentTemplate,
    OpRule,
    OpRuleEffect,
    OpRulePrecond,
    OpRuleResourceReq,
    Resource,
    SolveRequest,
    StateFeatureDef,
    StateNode,
    StateNodeReference,
)
from app.db.schemas import (
    LayeredExpansionRequest,
    LayeredSolveRequest,
    MaintenanceFactTemplate,
    MaintenanceSolveRequest,
)
from app.services.layered_solve import solve_layered
from app.services.layered_expansion import expand_layered_context
from app.services.maintenance_solve import solve_maintenance


pytestmark = pytest.mark.asyncio


HIGH_PARALLEL_PACKAGES = {
    "集成准备": {
        "activity_code": "MI_HP_PREP_ACT",
        "activity_name": "Integration Preparation",
        "state_code": "MI_HP_PREP_READY",
        "state_name": "Integration Preparation Ready",
        "sort_order": 10,
    },
    "结构装配": {
        "activity_code": "MI_HP_STRUCTURE_ACT",
        "activity_name": "Structure Assembly",
        "state_code": "MI_HP_STRUCTURE_DONE",
        "state_name": "Structure Assembly Complete",
        "sort_order": 20,
    },
    "传动机构装配": {
        "activity_code": "MI_HP_TRANSFER_ACT",
        "activity_name": "Transfer Mechanism Assembly",
        "state_code": "MI_HP_TRANSFER_READY",
        "state_name": "Transfer Mechanism Ready",
        "sort_order": 30,
    },
    "管路电气连接": {
        "activity_code": "MI_HP_UTILITY_ACT",
        "activity_name": "Piping and Electrical Connection",
        "state_code": "MI_HP_UTILITY_CONNECTED",
        "state_name": "Piping and Electrical Connected",
        "sort_order": 40,
    },
    "调试校准": {
        "activity_code": "MI_HP_DEBUG_ACT",
        "activity_name": "Debugging and Calibration",
        "state_code": "MI_HP_DEBUG_DONE",
        "state_name": "Debugging Complete",
        "sort_order": 50,
    },
    "验收释放": {
        "activity_code": "MI_HP_ACCEPTANCE_ACT",
        "activity_name": "Acceptance Release",
        "state_code": "MI_HP_ACCEPTED",
        "state_name": "Mechanical Integration Accepted",
        "sort_order": 60,
    },
}


HIGH_PARALLEL_SUBSYSTEMS = {
    "MI_HP_PREP_ACT": "PREPARATION",
    "MI_HP_STRUCTURE_ACT": "STRUCTURE",
    "MI_HP_TRANSFER_ACT": "TRANSFER",
    "MI_HP_UTILITY_ACT": "UTILITY",
    "MI_HP_DEBUG_ACT": "COMMISSIONING",
    "MI_HP_ACCEPTANCE_ACT": "ACCEPTANCE",
}


def _high_parallel_scheduling_config() -> dict:
    return {
        "responsible_subsystems": [
            {"code": code, "name": code.replace("_", " ").title()}
            for code in HIGH_PARALLEL_SUBSYSTEMS.values()
        ],
        "rules": [
            {
                "code": "SUBSYSTEM_CONTINUITY",
                "name": "Responsible subsystem continuity",
                "type": "group_continuity",
                "enabled": True,
                "activation_mode": "optional",
                "selector": {"match": "all"},
                "enforcement": {"mode": "soft", "priority": 2, "overridable": False},
                "parameters": {"group_by": "responsible_subsystem"},
            },
            {
                "code": "CRANE_EXCLUSIVE",
                "name": "Crane work exclusive within machine plan",
                "type": "scope_exclusivity",
                "enabled": True,
                "activation_mode": "required",
                "selector": {"required_resource_type": "OVERHEAD_CRANE"},
                "enforcement": {"mode": "hard", "overridable": False},
                "parameters": {"against": "all_other_tasks"},
                "presentation": {
                    "gantt_marker": {"text": "吊", "color": "#f59e0b"}
                },
            },
            {
                "code": "CRANE_DAY_SHIFT_ONLY",
                "name": "Crane work allowed only on day shift",
                "type": "shift_restriction",
                "enabled": True,
                "activation_mode": "required",
                "selector": {"required_resource_type": "OVERHEAD_CRANE"},
                "enforcement": {"mode": "hard", "overridable": True},
                "parameters": {"allowed_shift_codes": ["DAY_SHIFT"]},
            },
            {
                "code": "FUNCTION_TEST_EXCLUSIVE",
                "name": "Functional commissioning preferred exclusive",
                "type": "scope_exclusivity",
                "enabled": True,
                "activation_mode": "optional",
                "selector": {"effect_dimension_keys": ["mi_hp_function_test_dim"]},
                "enforcement": {
                    "mode": "soft",
                    "priority": 1,
                    "weight": 1000,
                    "overridable": False,
                },
                "parameters": {"against": "all_other_tasks"},
            },
        ],
    }


HIGH_PARALLEL_RESOURCES = {
    "PROCESS_ENGINEER": ("MI-HP-PE-01", "Process Engineer", 1),
    "SAFETY_OFFICER": ("MI-HP-SAFE-01", "Safety Officer", 1),
    "LOGISTICS": ("MI-HP-LOG-01", "Logistics Operator", 1),
    "MECH_A": ("MI-HP-MECH-A", "Mechanical Team A", 1),
    "MECH_B": ("MI-HP-MECH-B", "Mechanical Team B", 1),
    "METROLOGY": ("MI-HP-MET-01", "Metrology Team", 2),
    "CONTROL": ("MI-HP-CTRL-01", "Control Team", 1),
    "QA": ("MI-HP-QA-01", "Quality Team", 1),
    "PIPE_TEAM": ("MI-HP-PIPE-01", "Piping Team", 2),
    "ELECTRICAL": ("MI-HP-ELEC-01", "Electrical Team", 1),
    "PRECISION_RIG": ("MI-HP-RIG-01", "Precision Alignment Rig", 1),
    "OVERHEAD_CRANE": ("MI-HP-CRANE-01", "Overhead Crane", 1),
}


HIGH_PARALLEL_EXTRA_RESOURCE_REQS = {
    "MI_A013": ["PRECISION_RIG"],
    "MI_A014": ["PRECISION_RIG"],
    "MI_A016": ["PRECISION_RIG"],
    "MI_A026": ["PRECISION_RIG"],
    "MI_A010": ["OVERHEAD_CRANE"],
    "MI_A015": ["OVERHEAD_CRANE"],
}


HIGH_PARALLEL_ACTIVITIES = [
    ("MI_A001", "Confirm work order and version", "集成准备", [], "Work order confirmed", "PROCESS_ENGINEER", 10),
    ("MI_A002", "Execute lockout tagout", "集成准备", ["MI_A001"], "Safety isolation complete", "SAFETY_OFFICER", 15),
    ("MI_A003", "Count mechanical materials", "集成准备", ["MI_A001"], "Mechanical materials complete", "LOGISTICS", 20),
    ("MI_A004", "Verify installation tools", "集成准备", ["MI_A001"], "Tools available", "MECH_A", 15),
    ("MI_A005", "Review measurement datum", "集成准备", ["MI_A001"], "Measurement datum available", "METROLOGY", 15),
    ("MI_A006", "Load control baseline", "集成准备", ["MI_A001"], "Control baseline ready", "CONTROL", 20),
    ("MI_A007", "Clean installation datum surface", "集成准备", ["MI_A002", "MI_A004"], "Datum surface clean", "MECH_A", 20),
    ("MI_A008", "Inspect incoming critical parts", "集成准备", ["MI_A003", "MI_A005"], "Critical parts accepted", "QA", 25),
    ("MI_A009", "Mark installation datum line", "结构装配", ["MI_A005", "MI_A007"], "Datum line complete", "METROLOGY", 20),
    ("MI_A010", "Install base frame", "结构装配", ["MI_A008", "MI_A009"], "Base frame installed", "MECH_A", 30),
    ("MI_A011", "Install left column", "结构装配", ["MI_A010"], "Left column installed", "MECH_A", 25),
    ("MI_A012", "Install right column", "结构装配", ["MI_A010"], "Right column installed", "MECH_B", 25),
    ("MI_A013", "Align left column", "结构装配", ["MI_A011"], "Left column qualified", "METROLOGY", 20),
    ("MI_A014", "Align right column", "结构装配", ["MI_A012"], "Right column qualified", "METROLOGY", 20),
    ("MI_A015", "Install crossbeam assembly", "结构装配", ["MI_A013", "MI_A014"], "Crossbeam installed", "MECH_A", 30),
    ("MI_A016", "Adjust guide rail straightness", "结构装配", ["MI_A015"], "Guide rail straightness qualified", "METROLOGY", 25),
    ("MI_A017", "Lock structure fasteners", "结构装配", ["MI_A016"], "Structure assembly complete", "MECH_B", 15),
    ("MI_A018", "Install atmospheric arm base", "传动机构装配", ["MI_A017"], "Atmospheric arm base installed", "MECH_A", 25),
    ("MI_A019", "Install vacuum arm base", "传动机构装配", ["MI_A017"], "Vacuum arm base installed", "MECH_B", 25),
    ("MI_A020", "Install atmospheric arm body", "传动机构装配", ["MI_A018"], "Atmospheric arm installed", "MECH_A", 35),
    ("MI_A021", "Install vacuum arm body", "传动机构装配", ["MI_A019"], "Vacuum arm installed", "MECH_B", 35),
    ("MI_A022", "Adjust atmospheric arm limit", "传动机构装配", ["MI_A020"], "Atmospheric arm limit qualified", "MECH_A", 20),
    ("MI_A023", "Adjust vacuum arm limit", "传动机构装配", ["MI_A021"], "Vacuum arm limit qualified", "MECH_B", 20),
    ("MI_A024", "Install drive motor", "传动机构装配", ["MI_A022", "MI_A023"], "Drive motor installed", "MECH_A", 25),
    ("MI_A025", "Install reducer and coupling", "传动机构装配", ["MI_A022", "MI_A023"], "Transmission chain connected", "MECH_B", 25),
    ("MI_A026", "Adjust coaxiality and belt tension", "传动机构装配", ["MI_A024", "MI_A025"], "Transfer mechanism ready", "METROLOGY", 30),
    ("MI_A027", "Install vacuum piping", "管路电气连接", ["MI_A018", "MI_A019"], "Vacuum piping installed", "PIPE_TEAM", 30),
    ("MI_A028", "Install gas and cooling piping", "管路电气连接", ["MI_A018", "MI_A019"], "Auxiliary piping installed", "PIPE_TEAM", 30),
    ("MI_A029", "Install cable carrier", "管路电气连接", ["MI_A017"], "Cable carrier installed", "ELECTRICAL", 25),
    ("MI_A030", "Connect sensor cables", "管路电气连接", ["MI_A022", "MI_A023", "MI_A029"], "Sensors connected", "ELECTRICAL", 30),
    ("MI_A031", "Connect control cabinet interface", "管路电气连接", ["MI_A006", "MI_A029", "MI_A030"], "Control interface connected", "ELECTRICAL", 25),
    ("MI_A032", "Run piping leak check", "调试校准", ["MI_A027", "MI_A028"], "Piping check passed", "QA", 25),
    ("MI_A033", "Run I/O point check", "调试校准", ["MI_A031"], "I/O check passed", "CONTROL", 30),
    ("MI_A034", "Run single-axis jog test", "调试校准", ["MI_A026", "MI_A032", "MI_A033"], "Single-axis motion passed", "CONTROL", 30),
    ("MI_A035", "Run dual-arm interlock cycle test", "验收释放", ["MI_A034"], "Dual-arm cycle passed", "CONTROL", 45),
    ("MI_A036", "Complete mechanical integration acceptance", "验收释放", ["MI_A035"], "Mechanical integration complete", "QA", 20),
]


def _high_parallel_feature_key(activity_code: str) -> str:
    return f"mi_hp_{activity_code.lower()}_done"


async def _seed_state_group_continuity_case(session):
    machine_type = MachineType(id=5001, code="STATE_CONT", name="State continuity")
    machine = Machine(id=5001, machine_type_id=5001, code="SC-001", name="State Continuity Machine")
    session.add_all([machine_type, machine])
    session.add_all([
        StateFeatureDef(machine_type_id=5001, feature_key="a_ready", feature_name="A Ready", value_type="enum"),
        StateFeatureDef(machine_type_id=5001, feature_key="b_ready", feature_name="B Ready", value_type="enum"),
    ])
    session.add(Resource(id=5001, machine_id=5001, code="TECH-01", name="Tech", resource_type="TECH", capacity=1))

    current = MachineState(id=5001, machine_id=5001, state_type="current", label="Current")
    session.add(current)
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=5001, feature_key="a_ready", feature_value="no"),
        MachineStateFeature(machine_state_id=5001, feature_key="b_ready", feature_value="no"),
    ])

    root_state = StateNode(
        id=5101,
        machine_type_id=5001,
        parent_id=None,
        level=1,
        code="ROOT_STATE",
        name="Root State",
        state_kind="aggregate",
    )
    child_state = StateNode(
        id=5102,
        machine_type_id=5001,
        parent_id=5101,
        level=2,
        code="CHILD_STATE",
        name="Child State",
        state_kind="aggregate",
    )
    leaf_a = StateNode(
        id=5103,
        machine_type_id=5001,
        parent_id=None,
        level=3,
        code="A_READY",
        name="A Ready",
        feature_key="a_ready",
        operator="eq",
        target_value="yes",
        state_kind="atomic",
    )
    leaf_b = StateNode(
        id=5104,
        machine_type_id=5001,
        parent_id=None,
        level=3,
        code="B_READY",
        name="B Ready",
        feature_key="b_ready",
        operator="eq",
        target_value="yes",
        state_kind="atomic",
    )
    session.add_all([root_state, child_state, leaf_a, leaf_b])
    session.add_all([
        StateNodeReference(state_node_id=5103, parent_state_node_id=5102),
        StateNodeReference(state_node_id=5104, parent_state_node_id=5102),
    ])

    activity_root = ActivityNode(
        id=5201,
        machine_type_id=5001,
        parent_id=None,
        level=1,
        code="ACT_ROOT",
        name="Activity Root",
    )
    activity_package = ActivityNode(
        id=5202,
        machine_type_id=5001,
        parent_id=5201,
        level=2,
        code="ACT_PACKAGE",
        name="Activity Package",
    )
    atomic_a = AtomicActivity(id=5301, machine_type_id=5001, code="DO_A", name="Do A")
    atomic_b = AtomicActivity(id=5302, machine_type_id=5001, code="DO_B", name="Do B")
    session.add_all([activity_root, activity_package, atomic_a, atomic_b])
    session.add_all([
        ActivityPackageAtomicRef(activity_node_id=5202, atomic_activity_id=5301, sort_order=1),
        ActivityPackageAtomicRef(activity_node_id=5202, atomic_activity_id=5302, sort_order=2),
    ])

    rule_a = OpRule(
        id=5401,
        machine_type_id=5001,
        atomic_activity_id=5301,
        code="RULE_A_READY",
        name="Make A ready",
        duration_min=10,
    )
    rule_b = OpRule(
        id=5402,
        machine_type_id=5001,
        atomic_activity_id=5302,
        code="RULE_B_READY",
        name="Make B ready",
        duration_min=10,
    )
    session.add_all([rule_a, rule_b])
    session.add_all([
        OpRuleEffect(op_rule_id=5401, feature_key="a_ready", new_value="yes"),
        OpRuleEffect(op_rule_id=5402, feature_key="b_ready", new_value="yes"),
        OpRuleResourceReq(op_rule_id=5401, resource_type="TECH", quantity=1, is_required=True),
        OpRuleResourceReq(op_rule_id=5402, resource_type="TECH", quantity=1, is_required=True),
    ])
    await session.commit()


async def _seed_mechanical_integration_continuity_case(session):
    machine_type = MachineType(id=6001, code="MECH_INTEGRATION", name="Mechanical integration system")
    machine = Machine(id=6001, machine_type_id=6001, code="MI-001", name="Mechanical Integration Cell")
    session.add_all([machine_type, machine])
    session.add_all([
        StateFeatureDef(machine_type_id=6001, feature_key="base_frame_status", feature_name="Base Frame Status", value_type="enum"),
        StateFeatureDef(machine_type_id=6001, feature_key="column_alignment_status", feature_name="Column Alignment Status", value_type="enum"),
        StateFeatureDef(machine_type_id=6001, feature_key="atmospheric_arm_status", feature_name="Atmospheric Arm Status", value_type="enum"),
        StateFeatureDef(machine_type_id=6001, feature_key="vacuum_arm_status", feature_name="Vacuum Arm Status", value_type="enum"),
        StateFeatureDef(machine_type_id=6001, feature_key="standalone_status", feature_name="Standalone Status", value_type="enum"),
    ])
    session.add(Resource(id=6001, machine_id=6001, code="MECH-TEAM-01", name="Mechanical Team", resource_type="MECH_TEAM", capacity=1))

    current = MachineState(id=6001, machine_id=6001, state_type="current", label="Mechanical integration start")
    session.add(current)
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=6001, feature_key="base_frame_status", feature_value="pending"),
        MachineStateFeature(machine_state_id=6001, feature_key="column_alignment_status", feature_value="pending"),
        MachineStateFeature(machine_state_id=6001, feature_key="atmospheric_arm_status", feature_value="pending"),
        MachineStateFeature(machine_state_id=6001, feature_key="vacuum_arm_status", feature_value="pending"),
        MachineStateFeature(machine_state_id=6001, feature_key="standalone_status", feature_value="pending"),
    ])

    root_state = StateNode(
        id=6101,
        machine_type_id=6001,
        parent_id=None,
        level=1,
        code="MECH_INTEGRATION_COMPLETE",
        name="Mechanical Integration Complete",
        state_kind="aggregate",
    )
    structure_state = StateNode(
        id=6102,
        machine_type_id=6001,
        parent_id=6101,
        level=2,
        code="STRUCTURE_ASSEMBLY_COMPLETE",
        name="Structure Assembly Complete",
        state_kind="aggregate",
    )
    transfer_state = StateNode(
        id=6103,
        machine_type_id=6001,
        parent_id=6101,
        level=2,
        code="TRANSFER_MECHANISM_READY",
        name="Transfer Mechanism Ready",
        state_kind="aggregate",
    )
    standalone_state = StateNode(
        id=6151,
        machine_type_id=6001,
        parent_id=None,
        level=1,
        code="STANDALONE_COMPLETE",
        name="Standalone Complete",
        state_kind="aggregate",
    )
    leaves = [
        StateNode(
            id=6111,
            machine_type_id=6001,
            parent_id=None,
            level=3,
            code="BASE_FRAME_INSTALLED",
            name="Base Frame Installed",
            feature_key="base_frame_status",
            operator="eq",
            target_value="installed",
            state_kind="atomic",
        ),
        StateNode(
            id=6112,
            machine_type_id=6001,
            parent_id=None,
            level=3,
            code="COLUMN_ALIGNED",
            name="Column Aligned",
            feature_key="column_alignment_status",
            operator="eq",
            target_value="aligned",
            state_kind="atomic",
        ),
        StateNode(
            id=6113,
            machine_type_id=6001,
            parent_id=None,
            level=3,
            code="ATMOSPHERIC_ARM_INSTALLED",
            name="Atmospheric Arm Installed",
            feature_key="atmospheric_arm_status",
            operator="eq",
            target_value="installed",
            state_kind="atomic",
        ),
        StateNode(
            id=6114,
            machine_type_id=6001,
            parent_id=None,
            level=3,
            code="VACUUM_ARM_INSTALLED",
            name="Vacuum Arm Installed",
            feature_key="vacuum_arm_status",
            operator="eq",
            target_value="installed",
            state_kind="atomic",
        ),
        StateNode(
            id=6152,
            machine_type_id=6001,
            parent_id=None,
            level=2,
            code="STANDALONE_READY",
            name="Standalone Ready",
            feature_key="standalone_status",
            operator="eq",
            target_value="done",
            state_kind="atomic",
        ),
    ]
    session.add_all([root_state, structure_state, transfer_state, standalone_state, *leaves])
    session.add_all([
        StateNodeReference(state_node_id=6111, parent_state_node_id=6102),
        StateNodeReference(state_node_id=6112, parent_state_node_id=6102),
        StateNodeReference(state_node_id=6113, parent_state_node_id=6103),
        StateNodeReference(state_node_id=6114, parent_state_node_id=6103),
        StateNodeReference(state_node_id=6152, parent_state_node_id=6151),
    ])

    activity_root = ActivityNode(
        id=6201,
        machine_type_id=6001,
        parent_id=None,
        level=1,
        code="MECH_INTEGRATION_ACT",
        name="Mechanical Integration",
    )
    structure_package = ActivityNode(
        id=6202,
        machine_type_id=6001,
        parent_id=6201,
        level=2,
        code="STRUCTURE_ASSEMBLY_ACT",
        name="Structure Assembly",
    )
    transfer_package = ActivityNode(
        id=6203,
        machine_type_id=6001,
        parent_id=6201,
        level=2,
        code="TRANSFER_MECHANISM_ACT",
        name="Transfer Mechanism Assembly",
    )
    atomics = [
        AtomicActivity(id=6301, machine_type_id=6001, code="INSTALL_BASE_FRAME", name="Install Base Frame"),
        AtomicActivity(id=6302, machine_type_id=6001, code="ALIGN_COLUMN", name="Align Column"),
        AtomicActivity(id=6303, machine_type_id=6001, code="INSTALL_ATM_ARM", name="Install Atmospheric Arm"),
        AtomicActivity(id=6304, machine_type_id=6001, code="INSTALL_VAC_ARM", name="Install Vacuum Arm"),
        AtomicActivity(id=6305, machine_type_id=6001, code="CALIBRATE_STANDALONE", name="Calibrate Standalone"),
    ]
    session.add_all([activity_root, structure_package, transfer_package, *atomics])
    session.add_all([
        ActivityPackageAtomicRef(activity_node_id=6202, atomic_activity_id=6301, sort_order=1),
        ActivityPackageAtomicRef(activity_node_id=6202, atomic_activity_id=6302, sort_order=2),
        ActivityPackageAtomicRef(activity_node_id=6203, atomic_activity_id=6303, sort_order=1),
        ActivityPackageAtomicRef(activity_node_id=6203, atomic_activity_id=6304, sort_order=2),
    ])

    rules = [
        OpRule(id=6401, machine_type_id=6001, atomic_activity_id=6301, code="RULE_INSTALL_BASE_FRAME", name="Install base frame", duration_min=10),
        OpRule(id=6402, machine_type_id=6001, atomic_activity_id=6302, code="RULE_ALIGN_COLUMN", name="Align column", duration_min=10),
        OpRule(id=6403, machine_type_id=6001, atomic_activity_id=6303, code="RULE_INSTALL_ATM_ARM", name="Install atmospheric arm", duration_min=10),
        OpRule(id=6404, machine_type_id=6001, atomic_activity_id=6304, code="RULE_INSTALL_VAC_ARM", name="Install vacuum arm", duration_min=10),
        OpRule(id=6405, machine_type_id=6001, atomic_activity_id=6305, code="RULE_CALIBRATE_STANDALONE", name="Calibrate standalone", duration_min=10),
    ]
    session.add_all(rules)
    session.add_all([
        OpRuleEffect(op_rule_id=6401, feature_key="base_frame_status", new_value="installed"),
        OpRuleEffect(op_rule_id=6402, feature_key="column_alignment_status", new_value="aligned"),
        OpRuleEffect(op_rule_id=6403, feature_key="atmospheric_arm_status", new_value="installed"),
        OpRuleEffect(op_rule_id=6404, feature_key="vacuum_arm_status", new_value="installed"),
        OpRuleEffect(op_rule_id=6405, feature_key="standalone_status", new_value="done"),
        OpRuleResourceReq(op_rule_id=6401, resource_type="MECH_TEAM", quantity=1, is_required=True),
        OpRuleResourceReq(op_rule_id=6402, resource_type="MECH_TEAM", quantity=1, is_required=True),
        OpRuleResourceReq(op_rule_id=6403, resource_type="MECH_TEAM", quantity=1, is_required=True),
        OpRuleResourceReq(op_rule_id=6404, resource_type="MECH_TEAM", quantity=1, is_required=True),
        OpRuleResourceReq(op_rule_id=6405, resource_type="MECH_TEAM", quantity=1, is_required=True),
    ])
    await session.commit()


async def _seed_high_parallel_mechanical_integration_case(session):
    machine_type = MachineType(
        id=7001,
        code="MECH_INTEGRATION_HIGH_PARALLEL",
        name="Mechanical integration high parallel",
        scheduling_config=_high_parallel_scheduling_config(),
    )
    machine = Machine(id=7001, machine_type_id=7001, code="MI-HP-001", name="Mechanical Integration High Parallel Cell")
    session.add_all([machine_type, machine])

    function_test_template = StateFeatureDef(
        machine_type_id=7001,
        feature_key="mi_hp_function_test_dim",
        feature_name="Functional Commissioning",
        value_type="enum",
        allowed_values=["false", "true"],
        is_dimension_template=True,
    )
    session.add(function_test_template)
    await session.flush()

    for code, _, _, _, effect_name, _, _ in HIGH_PARALLEL_ACTIVITIES:
        session.add(
            StateFeatureDef(
                machine_type_id=7001,
                feature_key=_high_parallel_feature_key(code),
                feature_name=effect_name,
                value_type="enum",
                allowed_values=["false", "true"],
                dimension_template_id=(
                    function_test_template.id
                    if code in {"MI_A032", "MI_A033", "MI_A034", "MI_A035"}
                    else None
                ),
            )
        )

    for offset, (resource_type, (resource_code, resource_name, capacity)) in enumerate(HIGH_PARALLEL_RESOURCES.items(), start=1):
        session.add(
            Resource(
                id=7000 + offset,
                machine_id=7001,
                code=resource_code,
                name=resource_name,
                resource_type=resource_type,
                capacity=capacity,
                is_available=True,
            )
        )

    current = MachineState(id=7001, machine_id=7001, state_type="current", label="Mechanical integration high parallel start")
    session.add(current)
    await session.flush()
    for code, *_ in HIGH_PARALLEL_ACTIVITIES:
        session.add(
            MachineStateFeature(
                machine_state_id=7001,
                feature_key=_high_parallel_feature_key(code),
                feature_value="false",
            )
        )

    root_state = StateNode(
        id=7100,
        machine_type_id=7001,
        parent_id=None,
        level=1,
        code="MI_HP_COMPLETE",
        name="Mechanical Integration High Parallel Complete",
        state_kind="aggregate",
    )
    session.add(root_state)

    state_package_ids: dict[str, int] = {}
    for offset, package in enumerate(HIGH_PARALLEL_PACKAGES.values(), start=1):
        state_id = 7100 + offset
        state_package_ids[package["activity_code"]] = state_id
        session.add(
            StateNode(
                id=state_id,
                machine_type_id=7001,
                parent_id=7100,
                level=2,
                code=package["state_code"],
                name=package["state_name"],
                state_kind="aggregate",
                sort_order=package["sort_order"],
            )
        )

    leaf_ids: dict[str, int] = {}
    for index, (code, _, package_name, _, effect_name, _, _) in enumerate(HIGH_PARALLEL_ACTIVITIES, start=1):
        package = HIGH_PARALLEL_PACKAGES[package_name]
        leaf_id = 7200 + index
        leaf_ids[code] = leaf_id
        leaf = StateNode(
                id=leaf_id,
                machine_type_id=7001,
                parent_id=None,
                level=3,
                code=f"STATE_{code}_DONE",
                name=effect_name,
                feature_key=_high_parallel_feature_key(code),
                operator="eq",
                target_value="true",
                state_kind="atomic",
                sort_order=index,
            )
        session.add(leaf)
        session.add(
            StateNodeReference(
                state_node_id=leaf_id,
                parent_state_node_id=state_package_ids[package["activity_code"]],
                sort_order=index,
            )
        )

    activity_root = ActivityNode(
        id=7300,
        machine_type_id=7001,
        parent_id=None,
        level=1,
        code="MI_HP_ACT",
        name="Mechanical Integration High Parallel",
    )
    session.add(activity_root)

    activity_package_ids: dict[str, int] = {}
    for offset, package in enumerate(HIGH_PARALLEL_PACKAGES.values(), start=1):
        package_id = 7300 + offset
        activity_package_ids[package["activity_code"]] = package_id
        session.add(
            ActivityNode(
                id=package_id,
                machine_type_id=7001,
                parent_id=7300,
                level=2,
                code=package["activity_code"],
                name=package["activity_name"],
                sort_order=package["sort_order"],
            )
        )

    atomic_ids: dict[str, int] = {}
    rule_ids: dict[str, int] = {}
    for index, (code, name, package_name, deps, _, resource_type, duration) in enumerate(HIGH_PARALLEL_ACTIVITIES, start=1):
        atomic_id = 7400 + index
        rule_id = 7500 + index
        package = HIGH_PARALLEL_PACKAGES[package_name]
        atomic_ids[code] = atomic_id
        rule_ids[code] = rule_id
        session.add(
            AtomicActivity(
                id=atomic_id,
                machine_type_id=7001,
                code=code,
                name=name,
                sort_order=index,
                metadata_json={
                    "responsible_subsystem": HIGH_PARALLEL_SUBSYSTEMS[package["activity_code"]]
                },
            )
        )
        session.add(
            ActivityPackageAtomicRef(
                activity_node_id=activity_package_ids[package["activity_code"]],
                atomic_activity_id=atomic_id,
                sort_order=index,
            )
        )
        session.add(
            OpRule(
                id=rule_id,
                machine_type_id=7001,
                atomic_activity_id=atomic_id,
                code=f"RULE_{code}",
                name=name,
                duration_min=duration,
                is_active=True,
            )
        )
        for dep_code in deps:
            session.add(
                OpRulePrecond(
                    op_rule_id=rule_id,
                    feature_key=_high_parallel_feature_key(dep_code),
                    operator="eq",
                    feature_value="true",
                )
            )
        session.add(
            OpRuleEffect(
                op_rule_id=rule_id,
                feature_key=_high_parallel_feature_key(code),
                new_value="true",
            )
        )
        session.add(
            OpRuleResourceReq(
                op_rule_id=rule_id,
                resource_type=resource_type,
                quantity=1,
                is_required=True,
            )
        )
        for extra_resource_type in HIGH_PARALLEL_EXTRA_RESOURCE_REQS.get(code, []):
            session.add(
                OpRuleResourceReq(
                    op_rule_id=rule_id,
                    resource_type=extra_resource_type,
                    quantity=1,
                    is_required=True,
                )
            )

    await session.commit()


async def test_layered_state_group_continuity_returns_parent_and_child_groups(db_session):
    await _seed_state_group_continuity_case(db_session)

    result = await solve_layered(
        LayeredSolveRequest(
            machine_id=5001,
            current_state_id=5001,
            target_state_node_ids=[5101],
            activity_scope_node_ids=[5201],
            objectives=[
                {"type": "minimize_makespan", "weight": 1.0},
                {"type": "minimize_state_group_span", "weight": 1.0},
                {"type": "minimize_state_group_gaps", "weight": 1.0},
                {"type": "minimize_state_group_interruptions", "weight": 1.0},
            ],
        ),
        db_session,
    )

    assert result["status"] == "done"
    continuity = result["diagnostics"]["schedule"]["state_group_continuity"]
    group_codes = {group["state_group_code"] for group in continuity["groups"]}
    assert {"ROOT_STATE", "CHILD_STATE"} <= group_codes
    assert continuity["objective_weights"]["minimize_state_group_span"] == 1.0
    assert all(task["state_continuity_groups"] for task in result["schedule"]["tasks"])


async def test_layered_expansion_uses_canonical_atomic_scope_and_deprecates_package_scope(db_session):
    await _seed_state_group_continuity_case(db_session)

    explicit = await expand_layered_context(
        db_session,
        5001,
        LayeredExpansionRequest(atomic_activity_scope_ids=[5301]),
    )
    assert [item["atomic_activity_id"] for item in explicit["candidate_activities"]] == [5301]
    assert all(
        precondition["source_type"] == "self_activity_rule"
        for rule in explicit["effective_rules"]
        for precondition in rule["preconditions"]
    )

    compatibility = await expand_layered_context(
        db_session,
        5001,
        LayeredExpansionRequest(activity_scope_node_ids=[5201]),
    )
    assert {item["atomic_activity_id"] for item in compatibility["candidate_activities"]} == {
        5301,
        5302,
    }
    assert any(
        item["code"] == "ACTIVITY_PACKAGE_SCOPE_DEPRECATED"
        for item in compatibility["diagnostics"]
    )


async def test_registered_state_package_continuity_rule_compiles_existing_groups(db_session):
    await _seed_state_group_continuity_case(db_session)

    result = await solve_layered(
        LayeredSolveRequest(
            machine_id=5001,
            current_state_id=5001,
            target_state_node_ids=[5101],
            activity_scope_node_ids=[5201],
            constraints={
                "scheduling_rules": {
                    "active_rule_codes": ["STATE_PACKAGE_CONTINUITY"],
                }
            },
            objectives=[{"type": "minimize_makespan", "weight": 1.0}],
        ),
        db_session,
    )

    assert result["status"] == "done"
    diagnostics = result["diagnostics"]["schedule"]
    scheduling_rules = diagnostics["scheduling_rules"]
    assert scheduling_rules["active_rule_codes"] == ["STATE_PACKAGE_CONTINUITY"]
    assert scheduling_rules["violations"] == []
    assert scheduling_rules["continuity_groups"]
    assert all(
        group["group_key"].startswith("STATE_PACKAGE_CONTINUITY:state_package:")
        for group in scheduling_rules["continuity_groups"]
    )
    assert any(
        item.get("rule_code") == "STATE_PACKAGE_CONTINUITY"
        for item in diagnostics["objective_terms"]
    )
    state_groups = diagnostics["state_group_continuity"]["groups"]
    assert {
        "ROOT_STATE",
        "CHILD_STATE",
    } <= {group["state_group_code"] for group in state_groups}
    assert all(task["calendar_pause_min"] == 0 for task in result["schedule"]["tasks"])


async def test_layered_strategy_a_replan_preserves_state_group_membership(db_session):
    await _seed_state_group_continuity_case(db_session)

    objectives = [
        {"type": "minimize_makespan", "weight": 1.0},
        {"type": "minimize_state_group_span", "weight": 1.0},
        {"type": "minimize_state_group_gaps", "weight": 1.0},
        {"type": "minimize_state_group_interruptions", "weight": 1.0},
    ]
    initial = await solve_layered(
        LayeredSolveRequest(
            machine_id=5001,
            current_state_id=5001,
            target_state_node_ids=[5101],
            activity_scope_node_ids=[5201],
            objectives=objectives,
        ),
        db_session,
    )
    assert initial["status"] == "done"
    blocked_task = initial["schedule"]["tasks"][0]

    replanned = await solve_layered(
        LayeredSolveRequest(
            machine_id=5001,
            current_state_id=5001,
            target_state_node_ids=[5101],
            activity_scope_node_ids=[5201],
            objectives=objectives,
            parent_plan_id=initial["candidate_plan_id"],
            blockage_constraints={
                "strategy": "A",
                "blocked_step_id": blocked_task["step_id"],
                "blocked_op_rule_id": blocked_task["op_rule_id"],
                "strategy_a": {"not_before_offset": 25},
            },
        ),
        db_session,
    )

    assert replanned["status"] == "done"
    delayed_task = next(
        task for task in replanned["schedule"]["tasks"]
        if task["op_rule_id"] == blocked_task["op_rule_id"]
    )
    assert delayed_task["step_role"] == "delayed"
    assert delayed_task["not_before"] == 25
    assert delayed_task["start_min"] >= 25
    assert all(task["state_continuity_groups"] for task in replanned["schedule"]["tasks"])
    group_codes = {
        group["state_group_code"]
        for task in replanned["schedule"]["tasks"]
        for group in task["state_continuity_groups"]
    }
    assert {"ROOT_STATE", "CHILD_STATE"} <= group_codes
    continuity = replanned["diagnostics"]["schedule"]["state_group_continuity"]
    assert continuity["group_count"] >= 2


async def test_layered_state_group_continuity_uses_state_reference_path(db_session):
    await _seed_state_group_continuity_case(db_session)

    db_session.add(StateFeatureDef(machine_type_id=5001, feature_key="c_ready", feature_name="C Ready", value_type="enum"))
    current = await db_session.get(MachineState, 5001)
    assert current is not None
    db_session.add(MachineStateFeature(machine_state_id=5001, feature_key="c_ready", feature_value="no"))
    library_leaf = StateNode(
        id=5105,
        machine_type_id=5001,
        parent_id=None,
        level=1,
        code="C_READY",
        name="C Ready",
        feature_key="c_ready",
        operator="eq",
        target_value="yes",
        state_kind="atomic",
    )
    db_session.add(library_leaf)
    db_session.add(StateNodeReference(state_node_id=5105, parent_state_node_id=5102, sort_order=3))
    atomic_c = AtomicActivity(id=5303, machine_type_id=5001, code="DO_C", name="Do C")
    rule_c = OpRule(
        id=5403,
        machine_type_id=5001,
        atomic_activity_id=5303,
        code="RULE_C_READY",
        name="Make C ready",
        duration_min=10,
    )
    db_session.add_all([atomic_c, rule_c])
    db_session.add_all([
        ActivityPackageAtomicRef(activity_node_id=5202, atomic_activity_id=5303, sort_order=3),
        OpRuleEffect(op_rule_id=5403, feature_key="c_ready", new_value="yes"),
        OpRuleResourceReq(op_rule_id=5403, resource_type="TECH", quantity=1, is_required=True),
    ])
    await db_session.commit()

    result = await solve_layered(
        LayeredSolveRequest(
            machine_id=5001,
            current_state_id=5001,
            target_state_node_ids=[5101],
            activity_scope_node_ids=[5201],
            objectives=[
                {"type": "minimize_makespan", "weight": 1.0},
                {"type": "minimize_state_group_span", "weight": 1.0},
            ],
        ),
        db_session,
    )

    assert result["status"] == "done"
    referenced_goal = next(
        goal for goal in result["layered"]["goal_facts"]
        if goal["state_node_id"] == 5105
    )
    assert [item["code"] for item in referenced_goal["source_path"]] == ["ROOT_STATE", "CHILD_STATE", "C_READY"]

    referenced_task = next(
        task for task in result["schedule"]["tasks"]
        if task["op_rule_code"] == "RULE_C_READY"
    )
    group_codes = {group["state_group_code"] for group in referenced_task["state_continuity_groups"]}
    assert {"ROOT_STATE", "CHILD_STATE"} <= group_codes


async def test_mechanical_integration_state_packages_are_compacted(db_session):
    await _seed_mechanical_integration_continuity_case(db_session)

    result = await solve_layered(
        LayeredSolveRequest(
            machine_id=6001,
            current_state_id=6001,
            target_state_node_ids=[6101],
            activity_scope_node_ids=[6201],
            objectives=[
                {"type": "minimize_makespan", "weight": 1.0},
                {"type": "minimize_state_group_span", "weight": 1.0},
                {"type": "minimize_state_group_gaps", "weight": 1.0},
                {"type": "minimize_state_group_interruptions", "weight": 1.0},
            ],
        ),
        db_session,
    )

    assert result["status"] == "done"
    continuity = result["diagnostics"]["schedule"]["state_group_continuity"]
    groups = {group["state_group_code"]: group for group in continuity["groups"]}
    assert {
        "MECH_INTEGRATION_COMPLETE",
        "STRUCTURE_ASSEMBLY_COMPLETE",
        "TRANSFER_MECHANISM_READY",
    } <= set(groups)
    assert groups["MECH_INTEGRATION_COMPLETE"]["task_count"] == 4
    assert groups["STRUCTURE_ASSEMBLY_COMPLETE"]["task_count"] == 2
    assert groups["TRANSFER_MECHANISM_READY"]["task_count"] == 2
    assert groups["STRUCTURE_ASSEMBLY_COMPLETE"]["is_compact"]
    assert groups["TRANSFER_MECHANISM_READY"]["is_compact"]
    assert groups["STRUCTURE_ASSEMBLY_COMPLETE"]["parent_state_group_id"] == 6101
    assert groups["TRANSFER_MECHANISM_READY"]["parent_state_group_id"] == 6101

    tasks_by_code = {task["op_rule_code"]: task for task in result["schedule"]["tasks"]}
    assert {
        "RULE_INSTALL_BASE_FRAME",
        "RULE_ALIGN_COLUMN",
        "RULE_INSTALL_ATM_ARM",
        "RULE_INSTALL_VAC_ARM",
    } == set(tasks_by_code)
    for task in tasks_by_code.values():
        group_codes = {group["state_group_code"] for group in task["state_continuity_groups"]}
        assert "MECH_INTEGRATION_COMPLETE" in group_codes
        assert group_codes & {"STRUCTURE_ASSEMBLY_COMPLETE", "TRANSFER_MECHANISM_READY"}


async def test_high_parallel_mechanical_integration_solves_full_atomic_sequence(db_session):
    await _seed_high_parallel_mechanical_integration_case(db_session)

    result = await solve_layered(
        LayeredSolveRequest(
            machine_id=7001,
            current_state_id=7001,
            target_state_node_ids=[7100],
            activity_scope_node_ids=[7300],
            objectives=[{"type": "minimize_makespan", "weight": 1.0}],
        ),
        db_session,
    )

    assert result["status"] == "done"
    tasks = result["schedule"]["tasks"]
    tasks_by_code = {
        task["op_rule_code"].removeprefix("RULE_"): task
        for task in tasks
    }
    expected_codes = {item[0] for item in HIGH_PARALLEL_ACTIVITIES}
    assert set(tasks_by_code) == expected_codes
    assert len(tasks_by_code) == 36

    def overlaps(left_code: str, right_code: str) -> bool:
        left = tasks_by_code[left_code]
        right = tasks_by_code[right_code]
        return left["start_min"] < right["end_min"] and right["start_min"] < left["end_min"]

    def resource_types(activity_code: str) -> set[str]:
        return {
            req["resource_type"]
            for req in tasks_by_code[activity_code]["resource_reqs"]
        }

    assert overlaps("MI_A002", "MI_A003")
    assert overlaps("MI_A004", "MI_A005")
    assert overlaps("MI_A011", "MI_A012")
    assert not overlaps("MI_A013", "MI_A014")
    assert "PRECISION_RIG" in resource_types("MI_A013")
    assert "PRECISION_RIG" in resource_types("MI_A014")
    assert "PRECISION_RIG" in resource_types("MI_A016")
    assert "PRECISION_RIG" in resource_types("MI_A026")
    assert overlaps("MI_A018", "MI_A019")
    assert overlaps("MI_A020", "MI_A021")
    assert overlaps("MI_A024", "MI_A025")
    assert overlaps("MI_A027", "MI_A028")
    assert overlaps("MI_A027", "MI_A020")
    assert result["schedule"]["parallel_groups"]

    scheduling_rules = result["diagnostics"]["schedule"]["scheduling_rules"]
    assert {"CRANE_EXCLUSIVE", "CRANE_DAY_SHIFT_ONLY"} <= set(
        scheduling_rules["active_rule_codes"]
    )
    active_rules = {rule["code"]: rule for rule in scheduling_rules["active_rules"]}
    assert active_rules["CRANE_EXCLUSIVE"]["presentation"] == {
        "gantt_marker": {"text": "吊", "color": "#f59e0b"}
    }
    crane_tasks = [
        task
        for task in tasks
        if any(
            req["resource_type"] == "OVERHEAD_CRANE"
            for req in task["resource_reqs"]
        )
    ]
    assert {task["op_rule_code"] for task in crane_tasks} == {
        "RULE_MI_A010",
        "RULE_MI_A015",
    }
    assert all(
        not (
            crane["start_min"] < other["end_min"]
            and other["start_min"] < crane["end_min"]
        )
        for crane in crane_tasks
        for other in tasks
        if other["step_order"] != crane["step_order"]
    )
    assert all(task["responsible_subsystem"] for task in tasks)
    assert sum(
        "mi_hp_function_test_dim" in task["effect_dimension_keys"]
        for task in tasks
    ) == 4

    continuity = result["diagnostics"]["schedule"]["state_group_continuity"]
    group_codes = {group["state_group_code"] for group in continuity["groups"]}
    assert {
        "MI_HP_COMPLETE",
        "MI_HP_PREP_READY",
        "MI_HP_STRUCTURE_DONE",
        "MI_HP_TRANSFER_READY",
        "MI_HP_UTILITY_CONNECTED",
        "MI_HP_DEBUG_DONE",
        "MI_HP_ACCEPTED",
    } <= group_codes

    health = result["layered"]["preflight_health"]
    assert health["blocking_count"] == 0


async def test_high_parallel_combined_integration_rules_meet_quality_expectations(db_session):
    await _seed_high_parallel_mechanical_integration_case(db_session)

    result = await solve_layered(
        LayeredSolveRequest(
            machine_id=7001,
            current_state_id=7001,
            target_state_node_ids=[7100],
            activity_scope_node_ids=[7300],
            constraints={
                "scheduling_rules": {
                    "active_rule_codes": [
                        "SUBSYSTEM_CONTINUITY",
                        "FUNCTION_TEST_EXCLUSIVE",
                    ]
                }
            },
            objectives=[{"type": "minimize_makespan", "weight": 1.0}],
        ),
        db_session,
    )

    assert result["status"] == "done"
    tasks = result["schedule"]["tasks"]
    diagnostics = result["diagnostics"]["schedule"]["scheduling_rules"]
    assert {
        "SUBSYSTEM_CONTINUITY",
        "CRANE_EXCLUSIVE",
        "CRANE_DAY_SHIFT_ONLY",
        "FUNCTION_TEST_EXCLUSIVE",
    } <= set(diagnostics["active_rule_codes"])
    assert diagnostics["violations"] == []

    function_tasks = [
        task
        for task in tasks
        if "mi_hp_function_test_dim" in task["effect_dimension_keys"]
    ]
    assert len(function_tasks) == 4
    assert all(
        not (
            function_task["start_min"] < other["end_min"]
            and other["start_min"] < function_task["end_min"]
        )
        for function_task in function_tasks
        for other in tasks
        if other["step_order"] != function_task["step_order"]
    )

    subsystem_tasks: dict[str, list[dict]] = {}
    for task in tasks:
        subsystem_tasks.setdefault(task["responsible_subsystem"], []).append(task)
    assert set(subsystem_tasks) == set(HIGH_PARALLEL_SUBSYSTEMS.values())
    assert all(
        max(task["end_min"] for task in group)
        - min(task["start_min"] for task in group)
        <= sum(task["duration_min"] for task in group)
        for group in subsystem_tasks.values()
    )


async def test_layered_solve_empty_activity_scope_uses_all_atomic_activities(db_session):
    await _seed_mechanical_integration_continuity_case(db_session)

    result = await solve_layered(
        LayeredSolveRequest(
            machine_id=6001,
            current_state_id=6001,
            target_state_node_ids=[6151],
            activity_scope_node_ids=[],
            objectives=[
                {"type": "minimize_makespan", "weight": 1.0},
                {"type": "minimize_state_group_span", "weight": 1.0},
            ],
        ),
        db_session,
    )

    assert result["status"] == "done"
    assert result["layered"]["activity_scope_defaulted"] is True
    assert result["layered"]["requested_activity_scope_node_ids"] == []
    assert result["layered"]["activity_scope_node_ids"] == []
    assert result["layered"]["effective_model_version"].startswith("sha256:")
    solve_request = await db_session.get(SolveRequest, result["solve_request_id"])
    assert solve_request is not None
    assert (
        solve_request.overrides["effective_model_version"]
        == result["layered"]["effective_model_version"]
    )
    assert solve_request.overrides["effective_model_snapshot"]["schema_version"] == "effective-model/v1"
    assert {task["op_rule_code"] for task in result["schedule"]["tasks"]} == {"RULE_CALIBRATE_STANDALONE"}
    assert "CALIBRATE_STANDALONE" in {
        item["activity_node_code"] for item in result["layered"]["candidate_activities"]
    }

    scoped_result = await solve_layered(
        LayeredSolveRequest(
            machine_id=6001,
            current_state_id=6001,
            target_state_node_ids=[6151],
            activity_scope_node_ids=[6201],
            objectives=[
                {"type": "minimize_makespan", "weight": 1.0},
                {"type": "minimize_state_group_span", "weight": 1.0},
            ],
        ),
        db_session,
    )

    assert scoped_result["status"] == "failed"
    assert scoped_result["error_code"] == "NO_SOLUTION"


async def test_maintenance_direct_desired_fact_does_not_create_state_groups(db_session):
    await _seed_state_group_continuity_case(db_session)
    template = MaintenanceIntentTemplate(
        id=5501,
        machine_type_id=5001,
        scope_activity_node_id=5201,
        issue_type="DIRECT",
        name="Direct fact intent",
        target_state_node_ids=[],
        candidate_activity_scope_ids=[5201],
        desired_fact_templates=[],
    )
    db_session.add(template)
    await db_session.commit()

    result = await solve_maintenance(
        MaintenanceSolveRequest(
            machine_id=5001,
            current_state_id=5001,
            intent_template_ids=[5501],
            extra_desired_facts=[
                MaintenanceFactTemplate(feature_key="a_ready", operator="eq", value="yes"),
            ],
            objectives=[
                {"type": "minimize_makespan", "weight": 1.0},
                {"type": "minimize_state_group_span", "weight": 1.0},
            ],
        ),
        db_session,
    )

    assert result["status"] == "done"
    continuity = result["diagnostics"]["schedule"]["state_group_continuity"]
    assert continuity["group_count"] == 0
    assert all(not task["state_continuity_groups"] for task in result["schedule"]["tasks"])
