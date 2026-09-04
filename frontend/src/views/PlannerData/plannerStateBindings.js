export function splitActivityRelations(preconditions = []) {
  const transitions = []
  const required = []
  for (const relation of preconditions || []) {
    if (relation.relation_role === 'transition') transitions.push({ ...relation })
    else required.push({ ...relation, relation_role: 'required' })
  }
  const compatibleTransition = transitions.length === 1 && transitions[0].binding_type !== 'state_package'
  return {
    transitionStateId: compatibleTransition ? transitions[0].state_id : null,
    legacyTransitions: compatibleTransition ? [] : transitions,
    requiredBindings: inflateRequiredBindings(required),
  }
}

export function inflateRequiredBindings(preconditions = []) {
  const packageGroups = new Map()
  const atomicBindings = []
  for (const relation of preconditions || []) {
    if (relation.binding_type === 'state_package' && relation.state_package_id) {
      if (!packageGroups.has(relation.state_package_id)) packageGroups.set(relation.state_package_id, [])
      packageGroups.get(relation.state_package_id).push(relation)
      continue
    }
    atomicBindings.push({
      binding_type: 'atomic_state',
      state_id: relation.state_id,
      covered_state_ids: [relation.state_id],
      relation_role: 'required',
      coverage_status: 'complete',
    })
  }
  const packageBindings = [...packageGroups.entries()].map(([statePackageId, relations]) => {
    const coveredIds = relations[0]?.covered_state_ids?.length
      ? [...relations[0].covered_state_ids]
      : [...new Set(relations.map((item) => item.state_id))]
    return {
      binding_type: 'state_package',
      state_package_id: statePackageId,
      covered_state_ids: coveredIds,
      relation_role: 'required',
      coverage_status: relations[0]?.coverage_status || 'complete',
      snapshot_kept: !!relations[0]?.snapshot_kept,
    }
  })
  return [...packageBindings, ...atomicBindings]
}

export function flattenRequiredBindings(bindings = []) {
  const relations = []
  for (const binding of bindings || []) {
    if (binding.binding_type === 'state_package') {
      const coveredIds = [...new Set(binding.covered_state_ids || [])]
      for (const stateId of coveredIds) {
        relations.push({
          state_id: stateId,
          relation_role: 'required',
          binding_type: 'state_package',
          state_package_id: binding.state_package_id,
          covered_state_ids: coveredIds,
          coverage_status: binding.coverage_status || 'complete',
          snapshot_kept: !!binding.snapshot_kept,
        })
      }
      continue
    }
    if (binding.state_id) relations.push({ state_id: binding.state_id, relation_role: 'required', binding_type: 'atomic_state' })
  }
  return relations
}

export function activityPreconditions({ transitionStateId, legacyTransitions = [], preserveLegacy = false, requiredBindings = [] }) {
  const transitionRelations = preserveLegacy
    ? legacyTransitions.map((item) => ({ ...item }))
    : transitionStateId
      ? [{ state_id: transitionStateId, relation_role: 'transition', binding_type: 'atomic_state' }]
      : []
  return [...transitionRelations, ...flattenRequiredBindings(requiredBindings)]
}

export function bindingStateIds(bindings = []) {
  return new Set(flattenRequiredBindings(bindings).map((item) => item.state_id))
}
