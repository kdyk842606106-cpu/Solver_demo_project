const INITIAL_SOURCE_LABEL = '\u8d77\u59cb\u6761\u4ef6'
const MISSING_REALIZER_LABEL = '\u5f85\u8865\u8fbe\u6210\u6d3b\u52a8'
const REALIZER_LABEL = '\u8fbe\u6210\u6d3b\u52a8'
const MULTI_TARGET_LABEL = '\u591a\u76ee\u6807'
const MISSING_RULE_LABEL = '\u7f3a\u89c4\u5219'
const MULTI_ACTIVITY_LABEL = '\u591a\u6d3b\u52a8'
const AGGREGATE_TARGET_LABEL = '\u805a\u5408\u76ee\u6807'
const TRANSITION_COUNT_LABEL = '\u6761\u8f6c\u79fb'
const INTERNAL_TRANSITION_LABEL = '\u6761\u5185\u90e8\u8f6c\u79fb'
const PACKAGE_PRECONDITION_LABEL = '\u72b6\u6001\u5305\u524d\u7f6e'
const PACKAGE_OUTPUT_LABEL = '\u72b6\u6001\u5305\u4ea7\u51fa'
const PACKAGE_COMPLETE_LABEL = '\u5168\u90e8'
const PACKAGE_PARTIAL_LABEL = '\u90e8\u5206\u6210\u5458'
const PACKAGE_STALE_LABEL = '\u8986\u76d6\u5df2\u53d8\u66f4'
const FOLDED_PRECONDITION_LABEL = '\u6761\u6298\u53e0\u524d\u7f6e'
const FOLDED_OUTPUT_LABEL = '\u6761\u6298\u53e0\u4ea7\u51fa'

function stateNodeKey(value) {
  if (value === null || value === undefined || value === '') return null
  return String(value)
}

function graphStateNodeKey(graphId) {
  const id = String(graphId || '')
  if (!id.startsWith('state_node:')) return null
  const rawId = id.slice('state_node:'.length)
  const [stateNodeId] = rawId.split(':')
  return stateNodeKey(stateNodeId || rawId)
}

function transitionRelayGraphId(activityId) {
  return `transition_relay:${String(activityId || '')}`
}

function addTransitionWarning(warnings, label, type = 'warning') {
  if (!warnings.some((item) => item.label === label)) warnings.push({ label, type })
}

function uniqueTransitionRealizers(realizers) {
  const seen = new Set()
  const result = []
  for (const item of realizers || []) {
    if (!item?.activityId || seen.has(item.activityId)) continue
    seen.add(item.activityId)
    result.push(item)
  }
  return result
}

function uniqueTransitionEdgesByEndpoint(edges, endpointKey) {
  const seen = new Set()
  const result = []
  for (const edge of edges || []) {
    const endpoint = String(edge?.[endpointKey] || '')
    if (!endpoint || seen.has(endpoint)) continue
    seen.add(endpoint)
    result.push(edge)
  }
  return result
}

function defaultNodeLabel(node) {
  return node?.name || node?.code || node?.id || ''
}

function defaultAtomicStatePredicate(node) {
  if (!node) return false
  return node.is_leaf === true || !!node.feature_key || node.state_kind === 'atomic'
}

function isInitialTransitionSourceState(node, realizers, consumerCount, atomicPredicate) {
  return atomicPredicate(node) &&
    !realizers.length &&
    Number(consumerCount || 0) > 0 &&
    String(node?.target_value || '').toLowerCase() === 'false'
}

function transitionRealizerLabel(realizers, options = {}) {
  const nodeLabel = options.nodeLabel || defaultNodeLabel
  if (options.isInitialSource) return INITIAL_SOURCE_LABEL
  if (!realizers.length) return MISSING_REALIZER_LABEL
  if (realizers.length > 1) return `${realizers.length} \u4e2a${REALIZER_LABEL}`
  const activity = realizers[0].activity
  return activity ? nodeLabel(activity) : REALIZER_LABEL
}

function ensureListMapItem(map, key) {
  if (!map.has(key)) map.set(key, [])
  return map.get(key)
}

function edgeBinding(edge, bindingById = new Map()) {
  if (edge?.binding) return edge.binding
  return edge?.binding_id ? bindingById.get(Number(edge.binding_id)) || null : null
}

function uniqueStrings(values = []) {
  return Array.from(new Set((values || []).filter((value) => value !== null && value !== undefined && value !== '').map(String)))
}

function stateNodeForGraphId(graphId, stateNodes = []) {
  const id = String(graphId || '')
  const exact = (stateNodes || []).find((node) => String(node?.id || '') === id)
  if (exact) return exact
  const stateNodeId = graphStateNodeKey(id)
  return stateNodeId
    ? (stateNodes || []).find((node) => String(node?.state_node_id || '') === stateNodeId) || null
    : null
}

function bindingCoverageSummary(edge, {
  bindingById = new Map(),
  visibleStateNodes = [],
  endpointGraphId = null,
} = {}) {
  const binding = edgeBinding(edge, bindingById)
  if (binding?.binding_type !== 'state_package') return null
  const node = stateNodeForGraphId(endpointGraphId, visibleStateNodes)
  const coveredLeafIds = uniqueStrings(binding.covered_leaf_state_ids || [])
  const totalLeafCount = Math.max(
    Number(node?.leaf_count || 0),
    Array.isArray(node?.leaf_state_ids) ? node.leaf_state_ids.length : 0,
    coveredLeafIds.length,
  )
  const coveredLeafCount = coveredLeafIds.length
  const status = String(edge?.coverage_status || binding.coverage_status || 'stale')
  const role = String(edge?.binding_role || binding.binding_role || '')
  const roleLabel = role === 'output'
    ? PACKAGE_OUTPUT_LABEL
    : PACKAGE_PRECONDITION_LABEL
  const statusLabel = status === 'complete'
    ? PACKAGE_COMPLETE_LABEL
    : status === 'partial'
      ? PACKAGE_PARTIAL_LABEL
      : status === 'draft'
        ? PACKAGE_PARTIAL_LABEL
        : PACKAGE_STALE_LABEL
  const ratio = totalLeafCount > 0 ? `${coveredLeafCount}/${totalLeafCount}` : String(coveredLeafCount)
  return {
    bindingId: binding.id || edge?.binding_id || null,
    role,
    roleLabel,
    status,
    statusLabel,
    coveredLeafIds,
    coveredLeafCount,
    totalLeafCount,
    compactLabel: `${roleLabel} \u00b7 ${statusLabel} ${ratio}`,
    detailLabel: `${roleLabel} \u00b7 ${statusLabel} ${ratio}`,
  }
}

function strongestCoverageStatus(statuses = []) {
  const priority = { draft: 4, stale: 3, partial: 2, complete: 1 }
  return (statuses || []).reduce((current, status) =>
    (priority[String(status || '')] || 0) > (priority[current] || 0) ? String(status) : current,
  'complete')
}

function buildEndpointIndexes(edges) {
  const inputsByActivity = new Map()
  const outputsByActivity = new Map()
  const outputsByActivitySet = new Map()
  const consumersByStateId = new Map()

  for (const edge of edges || []) {
    if (edge.type === 'STATE_TO_ACTIVITY' && edge.binding_role === 'input') {
      ensureListMapItem(inputsByActivity, edge.target_id).push(edge)
      const stateNodeId = graphStateNodeKey(edge.source_id)
      if (stateNodeId) consumersByStateId.set(stateNodeId, (consumersByStateId.get(stateNodeId) || 0) + 1)
    } else if (edge.type === 'ACTIVITY_TO_STATE' && edge.binding_role === 'output') {
      ensureListMapItem(outputsByActivity, edge.source_id).push(edge)
      if (!outputsByActivitySet.has(edge.source_id)) outputsByActivitySet.set(edge.source_id, new Set())
      outputsByActivitySet.get(edge.source_id).add(edge.target_id)
    }
  }

  return {
    inputsByActivity,
    outputsByActivity,
    outputsByActivitySet,
    consumersByStateId,
  }
}

function buildCanonicalStateMaps(visibleStateNodes) {
  const canonicalStateIdByGraphId = new Map()
  const visibleStateGraphIdByCanonicalId = new Map()
  for (const node of visibleStateNodes || []) {
    const graphId = String(node?.id || '')
    const canonicalId = stateNodeKey(node?.state_node_id) || graphStateNodeKey(graphId)
    if (!graphId || !canonicalId) continue
    canonicalStateIdByGraphId.set(graphId, canonicalId)
    if (!visibleStateGraphIdByCanonicalId.has(canonicalId)) {
      visibleStateGraphIdByCanonicalId.set(canonicalId, graphId)
    }
  }
  return { canonicalStateIdByGraphId, visibleStateGraphIdByCanonicalId }
}

function stateContainerCollapseKey(node) {
  return String(node?.id || node?.state_node_id || '')
}

function flattenedStatePathIds(node) {
  const pathIds = Array.isArray(node?.path_ids) ? node.path_ids : []
  if (!pathIds.length) return []
  if (pathIds.some((item) => Array.isArray(item))) {
    return pathIds
      .filter((path) => Array.isArray(path))
      .flatMap((path) => path)
      .map((id) => String(id))
  }
  return pathIds.map((id) => String(id))
}

function statePathContains(node, stateNodeId) {
  const rootId = String(stateNodeId || '')
  if (!node || !rootId) return false
  if (String(node.parent_id || '') === rootId) return true
  if (String(node.reference_parent_id || '') === rootId) return true
  if ((node.reference_parent_ids || []).some((id) => String(id) === rootId)) return true
  return flattenedStatePathIds(node).some((id) => id === rootId)
}

function isDirectStateChild(node, parentNode) {
  const parentId = String(parentNode?.state_node_id || '')
  if (!node || !parentId || String(node.state_node_id || '') === parentId) return false
  if (String(node.parent_id || '') === parentId) return true
  if (String(node.reference_parent_id || '') === parentId) return true
  if ((node.reference_parent_ids || []).some((id) => String(id) === parentId)) return true
  const path = flattenedStatePathIds(node)
  const parentIndex = path.findIndex((id) => id === parentId)
  if (parentIndex < 0) return false
  return String(path[parentIndex + 1] || '') === String(node.state_node_id || '')
}

function nearestVisibleStateProxy(hiddenNode, renderedStateNodes = []) {
  return (renderedStateNodes || [])
    .filter((candidate) =>
      candidate.id !== hiddenNode?.id &&
      candidate.state_node_id &&
      statePathContains(hiddenNode, candidate.state_node_id),
    )
    .sort((a, b) => Number(b.level || 0) - Number(a.level || 0))[0] || null
}

function buildStateGroupProjections({
  visibleStateNodes = [],
  renderedStateNodes = [],
  expandedStateGraphIds = [],
  collapsedStateContainerKeys = [],
  relayGroups = [],
} = {}) {
  const renderedIds = new Set((renderedStateNodes || []).map((node) => String(node?.id || '')).filter(Boolean))
  const expandedIds = new Set((expandedStateGraphIds || []).map((id) => String(id || '')).filter(Boolean))
  const collapsedKeys = new Set((collapsedStateContainerKeys || []).map((id) => String(id || '')).filter(Boolean))
  const transitionPairs = []
  for (const group of relayGroups || []) {
    for (const inputId of group.inputStateIds || []) {
      for (const outputId of group.outputStateIds || []) {
        transitionPairs.push({
          sourceId: String(inputId || ''),
          targetId: String(outputId || ''),
        })
      }
    }
  }

  const groups = new Map()
  for (const node of visibleStateNodes || []) {
    if (!node?.state_node_id || node.is_leaf) continue
    const graphId = String(node.id || `state_node:${node.state_node_id}`)
    const childNodes = (visibleStateNodes || []).filter((candidate) => isDirectStateChild(candidate, node))
    const descendantNodes = (visibleStateNodes || []).filter((candidate) =>
      candidate.id !== node.id &&
      candidate.state_node_id !== node.state_node_id &&
      statePathContains(candidate, node.state_node_id),
    )
    if (!childNodes.length && !descendantNodes.length) continue
    const descendantIds = new Set(descendantNodes.map((candidate) => String(candidate.id || '')).filter(Boolean))
    const transitionBearingIds = new Set()
    const incoming = new Map()
    const outgoing = new Map()
    for (const pair of transitionPairs) {
      const sourceInside = descendantIds.has(pair.sourceId)
      const targetInside = descendantIds.has(pair.targetId)
      if (sourceInside) transitionBearingIds.add(pair.sourceId)
      if (targetInside) transitionBearingIds.add(pair.targetId)
      if (sourceInside && targetInside && pair.sourceId !== pair.targetId) {
        outgoing.set(pair.sourceId, (outgoing.get(pair.sourceId) || 0) + 1)
        incoming.set(pair.targetId, (incoming.get(pair.targetId) || 0) + 1)
      }
    }
    const transitionBearing = Array.from(transitionBearingIds)
    const roots = transitionBearing.filter((id) => !(incoming.get(id) > 0))
    const leaves = transitionBearing.filter((id) => !(outgoing.get(id) > 0))
    const expanded = renderedIds.has(graphId) &&
      !collapsedKeys.has(stateContainerCollapseKey(node)) &&
      (expandedIds.has(graphId) || childNodes.some((child) => renderedIds.has(String(child.id || ''))))
    groups.set(graphId, {
      graphId,
      bodyId: node.state_node_id,
      kind: 'state_package',
      expanded,
      parentGroupId: parentStateGroupGraphId(node, visibleStateNodes),
      childGraphIds: childNodes.map((child) => String(child.id || '')).filter(Boolean),
      rootStateGraphIds: roots,
      leafStateGraphIds: leaves,
      boundaryInputGraphIds: roots,
      boundaryOutputGraphIds: leaves,
      proxyEdgeIds: [],
    })
  }
  return groups
}

function parentStateGroupGraphId(node, visibleStateNodes = []) {
  const candidates = []
  if (node?.primary_parent_graph_id) candidates.push(String(node.primary_parent_graph_id))
  if (node?.parent_graph_id) candidates.push(String(node.parent_graph_id))
  if (node?.parent_id) candidates.push(`state_node:${node.parent_id}`)
  for (const parentId of node?.reference_parent_ids || []) candidates.push(`state_node:${parentId}`)
  return candidates.find((id) =>
    id &&
    id !== String(node?.id || '') &&
    (visibleStateNodes || []).some((candidate) => String(candidate.id || '') === id),
  ) || null
}

function projectionGroupIdForNode(node) {
  if (!node?.id || node.is_leaf === true) return null
  return String(node.id)
}

function resolveProjectionEndpoint(graphId, { renderedStateNodes = [], visibleStateNodes = [] } = {}) {
  const id = String(graphId || '')
  if (!id.startsWith('state_node:')) return { id, hidden: false, kind: 'activity' }
  const rendered = stateNodeForGraphId(id, renderedStateNodes)
  if (rendered) {
    return {
      id: String(rendered.id || id),
      hidden: false,
      remapped: String(rendered.id || id) !== id,
      originalId: id,
      node: rendered,
      kind: 'state',
      groupId: projectionGroupIdForNode(rendered),
    }
  }
  const hiddenNode = stateNodeForGraphId(id, visibleStateNodes)
  const proxy = hiddenNode ? nearestVisibleStateProxy(hiddenNode, renderedStateNodes) : null
  if (!proxy) return null
  return {
    id: String(proxy.id || ''),
    hidden: true,
    hiddenId: id,
    hiddenNode,
    node: proxy,
    kind: 'state',
    groupId: String(proxy.id || ''),
  }
}

function endpointProjectionRows(edges, endpointKey, options = {}) {
  const groups = new Map()
  for (const edge of edges || []) {
    const originalId = String(edge?.[endpointKey] || '')
    const endpoint = resolveProjectionEndpoint(originalId, options)
    if (!endpoint?.id) continue
    const key = String(endpoint.id)
    if (!groups.has(key)) {
      groups.set(key, {
        endpoint,
        edges: [],
        originalIds: new Set(),
        groupIds: new Set(),
        packageCoverageSummaries: [],
      })
    }
    const group = groups.get(key)
    group.edges.push(edge)
    group.originalIds.add(originalId)
    if (endpoint.groupId) group.groupIds.add(endpoint.groupId)
    const summary = bindingCoverageSummary(edge, {
      bindingById: options.bindingById,
      visibleStateNodes: options.visibleStateNodes,
      endpointGraphId: originalId,
    })
    if (summary && !group.packageCoverageSummaries.some((item) => String(item.bindingId) === String(summary.bindingId))) {
      group.packageCoverageSummaries.push(summary)
    }
  }

  return Array.from(groups.values()).map((group) => {
    const first = group.edges[0] || {}
    const roleIsInput = endpointKey === 'source_id'
    const count = group.edges.length
    const packageSummaries = group.packageCoverageSummaries
    let displayLabel = ''
    if (packageSummaries.length === 1) {
      displayLabel = packageSummaries[0].compactLabel
    } else if (packageSummaries.length > 1) {
      const roleLabel = roleIsInput ? PACKAGE_PRECONDITION_LABEL : PACKAGE_OUTPUT_LABEL
      displayLabel = `\u542b ${packageSummaries.length} \u4e2a${roleLabel}`
    } else if (group.endpoint.hidden) {
      displayLabel = `${count} ${roleIsInput ? FOLDED_PRECONDITION_LABEL : FOLDED_OUTPUT_LABEL}`
    }
    return {
      ...first,
      [endpointKey]: group.endpoint.id,
      projectionEndpoint: group.endpoint,
      projectionOriginalEndpointIds: Array.from(group.originalIds),
      projectionGroupIds: Array.from(group.groupIds),
      endpointHidden: group.endpoint.hidden,
      aggregateEdges: group.edges,
      dependencyCount: count,
      packageBindingCount: packageSummaries.length,
      packageCoverageSummaries: packageSummaries,
      displayLabel,
    }
  })
}

function relayProjectionEdgeMetadata(item, group, direction) {
  const isInput = direction === 'input'
  const endpoint = item.projectionEndpoint || {}
  const originalIds = item.projectionOriginalEndpointIds || []
  const hiddenIds = endpoint.hidden ? originalIds : []
  const packageCoverageTitle = (item.packageCoverageSummaries || []).map((summary) => summary.detailLabel).join('\uff0c')
  const titleParts = [
    item.displayLabel,
    packageCoverageTitle,
    group.label,
  ].filter(Boolean)
  const metadata = {
    coverage_status: strongestCoverageStatus([
      item.coverage_status,
      ...(item.packageCoverageSummaries || []).map((summary) => summary.status),
    ]),
    displayLabel: item.displayLabel || '',
    title: titleParts.join(' \u00b7 '),
    packageCoverageLabel: item.displayLabel || '',
    packageCoverageTitle,
    packageCoverageSummaries: item.packageCoverageSummaries || [],
    packageBindingCount: Number(item.packageBindingCount || 0),
    dependencyCount: Number(item.dependencyCount || 1),
    underlyingTransitionIds: [group.id],
    underlyingActivityIds: [group.activityId],
    underlyingBindingIds: uniqueStrings((item.aggregateEdges || []).map((edge) => edge.binding_id)),
    projectionGroupIds: item.projectionGroupIds || [],
  }
  if (!endpoint.hidden) return metadata
  return {
    ...metadata,
    aggregate: true,
    projectionProxy: true,
    isCollapsedProxy: true,
    isPackageTransitionProxy: false,
    collapsedEdges: item.aggregateEdges || [],
    collapsedEdgeCount: Number(item.dependencyCount || 1),
    aggregateCount: Number(item.dependencyCount || 1),
    aggregateEdges: item.aggregateEdges || [],
    aggregateLabel: item.displayLabel || '',
    proxySourceId: isInput ? item.source_id : group.relayId,
    proxyTargetId: isInput ? group.relayId : item.target_id,
    hiddenSourceId: isInput ? hiddenIds[0] || null : null,
    hiddenTargetId: isInput ? null : hiddenIds[0] || null,
    hiddenSourceIds: isInput ? hiddenIds : [],
    hiddenTargetIds: isInput ? [] : hiddenIds,
  }
}

function buildTransitionBackboneEdges(relayGroups = []) {
  const result = []
  const seen = new Set()
  for (const group of relayGroups || []) {
    for (const input of group.inputs || []) {
      const key = `${input.source_id}->${group.relayId}:${group.activityId}`
      if (seen.has(`in:${key}`)) continue
      seen.add(`in:${key}`)
      result.push({
        id: `state-flow-relay-in:${key}`,
        source_id: input.source_id,
        target_id: group.relayId,
        type: 'STATE_TO_ACTIVITY',
        binding_id: input.binding_id || null,
        binding_role: 'transition_precondition',
        source_kind: 'state_transition_relay',
        isTransitionRelayEdge: true,
        flowActivityId: group.activityId,
        flowRelayId: group.relayId,
        flowInputEdgeId: input.id,
        flowRealizerLabel: group.label,
        projectionTransitionId: group.id,
        ...relayProjectionEdgeMetadata(input, group, 'input'),
      })
    }
    for (const output of group.outputs || []) {
      const key = `${group.relayId}->${output.target_id}:${group.activityId}`
      if (seen.has(`out:${key}`)) continue
      seen.add(`out:${key}`)
      result.push({
        id: `state-flow-relay-out:${key}`,
        source_id: group.relayId,
        target_id: output.target_id,
        type: 'ACTIVITY_TO_STATE',
        binding_id: output.binding_id || null,
        binding_role: 'transition_realizer',
        source_kind: 'state_transition_relay',
        isTransitionRelayEdge: true,
        flowActivityId: group.activityId,
        flowRelayId: group.relayId,
        flowOutputEdgeId: output.id,
        flowRealizerLabel: group.label,
        projectionTransitionId: group.id,
        ...relayProjectionEdgeMetadata(output, group, 'output'),
      })
    }
  }
  return result
}

function projectRelayVisibility({
  semanticRelayGroups = [],
  visibleStateNodes = [],
  renderedStateNodes = [],
  bindingById = new Map(),
} = {}) {
  const relayGroups = []
  const foldedRelayGroups = []
  const options = { visibleStateNodes, renderedStateNodes, bindingById }
  for (const group of semanticRelayGroups || []) {
    const resolvedOutputs = (group.outputs || []).map((edge) => ({
      edge,
      endpoint: resolveProjectionEndpoint(edge.target_id, options),
    })).filter((item) => item.endpoint)
    if (!resolvedOutputs.length) continue
    const targetVisible = resolvedOutputs.some((item) => !item.endpoint.hidden)
    if (!targetVisible) {
      foldedRelayGroups.push(group)
      continue
    }
    const inputs = endpointProjectionRows(group.inputs, 'source_id', options)
    const outputs = endpointProjectionRows(group.outputs, 'target_id', options)
    if (!inputs.length || !outputs.length) continue
    relayGroups.push({
      ...group,
      inputs,
      outputs,
      inputStateIds: inputs.map((edge) => edge.source_id),
      outputStateIds: outputs.map((edge) => edge.target_id),
      visibleTargetStateIds: outputs.filter((edge) => !edge.endpointHidden).map((edge) => edge.target_id),
    })
  }
  return { relayGroups, foldedRelayGroups }
}

function foldedRelayProxyCandidates(groups, options = {}) {
  const candidates = []
  for (const group of groups || []) {
    const inputs = (group.inputs || []).map((edge) => ({
      edge,
      endpoint: resolveProjectionEndpoint(edge.source_id, options),
      packageCoverage: bindingCoverageSummary(edge, {
        bindingById: options.bindingById,
        visibleStateNodes: options.visibleStateNodes,
        endpointGraphId: edge.source_id,
      }),
    })).filter((item) => item.endpoint)
    const outputs = (group.outputs || []).map((edge) => ({
      edge,
      endpoint: resolveProjectionEndpoint(edge.target_id, options),
      packageCoverage: bindingCoverageSummary(edge, {
        bindingById: options.bindingById,
        visibleStateNodes: options.visibleStateNodes,
        endpointGraphId: edge.target_id,
      }),
    })).filter((item) => item.endpoint)
    for (const input of inputs) {
      for (const output of outputs) {
        const coverageSummaries = [input.packageCoverage, output.packageCoverage].filter(Boolean)
        candidates.push({
          id: `projection-dependency:${group.id}:${input.edge.id || input.edge.source_id}:${output.edge.id || output.edge.target_id}`,
          source_id: input.endpoint.id,
          target_id: output.endpoint.id,
          originalSourceId: input.edge.source_id,
          originalTargetId: output.edge.target_id,
          hiddenSourceId: input.endpoint.hidden ? input.edge.source_id : null,
          hiddenTargetId: output.endpoint.hidden ? output.edge.target_id : null,
          projectionGroupIds: uniqueStrings([input.endpoint.groupId, output.endpoint.groupId]),
          projectionTransitionId: group.id,
          flowActivityId: group.activityId,
          flowRelayId: group.relayId,
          flowRealizerLabel: group.label,
          underlyingBindingIds: uniqueStrings([input.edge.binding_id, output.edge.binding_id]),
          packageCoverageSummaries: coverageSummaries,
          packageBindingIds: uniqueStrings(coverageSummaries.map((summary) => summary.bindingId)),
          coverage_status: strongestCoverageStatus([
            input.edge.coverage_status,
            output.edge.coverage_status,
            ...coverageSummaries.map((summary) => summary.status),
          ]),
          dependencyKey: `${group.id}:${input.edge.id || input.edge.source_id}:${output.edge.id || output.edge.target_id}`,
          collapsedEdges: [input.edge, output.edge],
        })
      }
    }
  }
  return candidates
}

function compactPackageCoverageLabel(summaries = []) {
  const unique = []
  for (const summary of summaries || []) {
    const key = String(summary?.bindingId || summary?.detailLabel || '')
    if (!key || unique.some((item) => String(item.bindingId || item.detailLabel || '') === key)) continue
    unique.push(summary)
  }
  if (unique.length === 1) return unique[0].compactLabel
  if (unique.length > 1) return `\u542b ${unique.length} \u4e2a\u72b6\u6001\u5305\u7ed1\u5b9a`
  return ''
}

function packageProxyEdge(group, nodeLabelForGraphId = null) {
  const labelForGraphId = nodeLabelForGraphId || ((id) => String(id || ''))
  const transitionIds = uniqueStrings(group.edges.map((edge) => edge.projectionTransitionId))
  const activityIds = uniqueStrings(group.edges.map((edge) => edge.flowActivityId))
  const bindingIds = uniqueStrings(group.edges.flatMap((edge) => edge.underlyingBindingIds || []))
  const dependencyKeys = uniqueStrings(group.edges.map((edge) => edge.dependencyKey))
  const coverageSummaries = group.edges.flatMap((edge) => edge.packageCoverageSummaries || [])
  const packageBindingIds = uniqueStrings(coverageSummaries.map((summary) => summary.bindingId))
  const transitionCount = transitionIds.length
  const dependencyCount = dependencyKeys.length
  const internal = group.sourceId === group.targetId
  const coverageLabel = compactPackageCoverageLabel(coverageSummaries)
  const label = internal
    ? `${transitionCount} ${INTERNAL_TRANSITION_LABEL}`
    : `${transitionCount} ${TRANSITION_COUNT_LABEL}${coverageLabel ? ` \u00b7 ${coverageLabel}` : ''}`
  const activityLabels = uniqueStrings(group.edges.map((edge) => edge.flowRealizerLabel)).slice(0, 3)
  const coverageDetails = uniqueStrings(coverageSummaries.map((summary) => summary.detailLabel))
  const titleParts = [
    `${labelForGraphId(group.sourceId)} -> ${labelForGraphId(group.targetId)}`,
    `${transitionCount} ${TRANSITION_COUNT_LABEL}\uff0c${dependencyCount} \u6761\u524d\u7f6e\u4f9d\u8d56`,
    activityLabels.length ? `\u8fbe\u6210\u6d3b\u52a8\uff1a${activityLabels.join('\uff0c')}` : '',
    coverageDetails.join('\uff0c'),
  ].filter(Boolean)
  const hiddenSourceIds = uniqueStrings(group.edges.map((edge) => edge.hiddenSourceId))
  const hiddenTargetIds = uniqueStrings(group.edges.map((edge) => edge.hiddenTargetId))
  const projectionGroupIds = uniqueStrings(group.edges.flatMap((edge) => edge.projectionGroupIds || []))
  return {
    id: `projection-package-proxy:${group.key}`,
    source_id: group.sourceId,
    target_id: group.targetId,
    type: 'STATE_FLOW',
    binding_role: 'transition_proxy',
    source_kind: 'state_transition_projection',
    coverage_status: strongestCoverageStatus(group.edges.map((edge) => edge.coverage_status)),
    proxySourceId: group.sourceId,
    proxyTargetId: group.targetId,
    hiddenSourceId: hiddenSourceIds[0] || null,
    hiddenTargetId: hiddenTargetIds[0] || null,
    hiddenSourceIds,
    hiddenTargetIds,
    collapsedEdges: group.edges,
    collapsedEdgeCount: transitionCount,
    aggregateCount: transitionCount,
    aggregateEdges: group.edges,
    aggregateLabel: label,
    displayLabel: label,
    title: titleParts.join(' \u00b7 '),
    aggregate: true,
    isCollapsedProxy: true,
    isCollapsedInternalProxy: internal,
    isPackageTransitionProxy: true,
    projectionProxy: true,
    projectionGroupIds,
    underlyingTransitionIds: transitionIds,
    underlyingActivityIds: activityIds,
    underlyingBindingIds: bindingIds,
    transitionCount,
    dependencyCount,
    packageBindingCount: packageBindingIds.length,
    packageCoverageSummaries: coverageSummaries,
  }
}

function buildPackageProxyEdges({
  foldedRelayGroups = [],
  visibleStateNodes = [],
  renderedStateNodes = [],
  bindingById = new Map(),
  nodeLabelForGraphId = null,
} = {}) {
  const candidates = foldedRelayProxyCandidates(foldedRelayGroups, {
    visibleStateNodes,
    renderedStateNodes,
    bindingById,
  })
  const groups = new Map()
  for (const edge of candidates) {
    const key = `${edge.source_id}->${edge.target_id}`
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        sourceId: edge.source_id,
        targetId: edge.target_id,
        edges: [],
      })
    }
    groups.get(key).edges.push(edge)
  }
  return Array.from(groups.values()).map((group) => packageProxyEdge(group, nodeLabelForGraphId))
}

function assignProxyEdgesToGroups(proxyEdges = [], groupsByGraphId = new Map()) {
  for (const edge of proxyEdges || []) {
    for (const groupId of edge.projectionGroupIds || []) {
      const group = groupsByGraphId.get(groupId)
      if (group && !group.proxyEdgeIds.includes(edge.id)) group.proxyEdgeIds.push(edge.id)
    }
  }
}

function transitionSourceStatusFromItems(items = []) {
  return (items || []).some((item) => {
    const edge = item?.edge || item
    const binding = item?.binding
    return edge?.coverage_status === 'draft' ||
      edge?.is_draft ||
      edge?.is_pending ||
      String(edge?.id || '').startsWith('draft') ||
      String(edge?.draft_change_id || '') ||
      binding?.coverage_status === 'draft'
  }) ? 'draft' : 'committed'
}

function statePackagePath(node) {
  const pathIds = flattenedStatePathIds(node)
  const stateId = stateNodeKey(node?.state_node_id)
  const normalized = pathIds.length ? pathIds : (stateId ? [stateId] : [])
  return normalized.filter((id, index) => normalized.indexOf(id) === index)
}

function buildSelectedDetails({
  visibleStateNodes = [],
  transitionsByStateId = new Map(),
  preconditionsByActivityId = new Map(),
} = {}) {
  const detailsByStateId = new Map()
  const detailsByGraphId = new Map()
  for (const node of visibleStateNodes || []) {
    const stateNodeId = stateNodeKey(node?.state_node_id)
    const displayStateGraphId = String(node?.id || '')
    if (!stateNodeId || !displayStateGraphId) continue
    const transition = transitionsByStateId.get(stateNodeId) || null
    const realizers = transition?.realizers || []
    const preconditions = []
    const seen = new Set()
    for (const realizer of realizers) {
      for (const item of preconditionsByActivityId.get(realizer.activityId) || []) {
        const key = `${item.stateNodeId}:${realizer.activityId}`
        if (seen.has(key)) continue
        seen.add(key)
        preconditions.push({
          ...item,
          activity: realizer.activity,
          activityId: realizer.activityId,
          sourceStatus: transitionSourceStatusFromItems([item]),
        })
      }
    }
    const sourceStatus = transitionSourceStatusFromItems([
      ...realizers,
      ...preconditions,
    ])
    const detail = {
      stateNodeId,
      canonicalStateId: stateNodeId,
      canonicalStateGraphId: `state_node:${stateNodeId}`,
      displayStateGraphId,
      state: node,
      stateKind: node?.state_kind || (node?.feature_key ? 'atomic' : 'aggregate'),
      packagePathStateIds: statePackagePath(node),
      referencePathStateIds: (node?.reference_parent_ids || []).map((id) => String(id)),
      referenceId: node?.reference_id || null,
      transition,
      realizerActivities: realizers,
      preconditions,
      warnings: transition?.warnings || [],
      sourceStatus,
    }
    detailsByStateId.set(stateNodeId, detail)
    detailsByGraphId.set(displayStateGraphId, detail)
  }
  return { detailsByStateId, detailsByGraphId }
}

function buildRelayGroups({
  inputsByActivity,
  outputsByActivity,
  visibleStateNodes,
  nodeLabelForGraphId,
} = {}) {
  const visibleStateIds = new Set((visibleStateNodes || []).map((node) => String(node.id)))
  const groups = []
  const labelForGraphId = nodeLabelForGraphId || ((id) => String(id || ''))
  const activityIds = new Set([
    ...Array.from(inputsByActivity?.keys?.() || []),
    ...Array.from(outputsByActivity?.keys?.() || []),
  ])

  for (const activityId of Array.from(activityIds).sort((a, b) =>
    labelForGraphId(a).localeCompare(labelForGraphId(b), 'zh-Hans-CN') || String(a).localeCompare(String(b)),
  )) {
    const inputs = uniqueTransitionEdgesByEndpoint(
      (inputsByActivity.get(activityId) || []).filter((edge) => visibleStateIds.has(String(edge.source_id))),
      'source_id',
    )
    const outputs = uniqueTransitionEdgesByEndpoint(
      (outputsByActivity.get(activityId) || []).filter((edge) => visibleStateIds.has(String(edge.target_id))),
      'target_id',
    )
    if (!inputs.length || !outputs.length) continue
    const relayId = transitionRelayGraphId(activityId)
    groups.push({
      id: relayId,
      relayId,
      activityId,
      label: labelForGraphId(activityId),
      inputs,
      outputs,
      inputStateIds: inputs.map((edge) => edge.source_id),
      outputStateIds: outputs.map((edge) => edge.target_id),
      canonicalInputStateIds: inputs.map((edge) => graphStateNodeKey(edge.source_id)).filter(Boolean),
      canonicalOutputStateIds: outputs.map((edge) => graphStateNodeKey(edge.target_id)).filter(Boolean),
      opRuleIds: [...inputs, ...outputs].map((edge) => edge.op_rule_id).filter(Boolean),
      sourceBindingIds: [...inputs, ...outputs].map((edge) => edge.binding_id).filter(Boolean),
      draftChangeIds: [...inputs, ...outputs].map((edge) => edge.draft_change_id).filter(Boolean),
      coverage_status: [...inputs, ...outputs].some((edge) => edge.coverage_status === 'draft') ? 'draft' : 'complete',
    })
  }
  return groups
}

export function buildStateTransitionProjection({
  edges = [],
  visibleStateNodes = [],
  renderedStateNodes = null,
  expandedStateGraphIds = [],
  collapsedStateContainerKeys = [],
  activityByGraphId = new Map(),
  bindingById = new Map(),
  fallbackActivityGraphNode = () => null,
  fallbackStateGraphNode = () => null,
  nodeLabel = defaultNodeLabel,
  nodeLabelForGraphId = null,
  isAtomicStateNode = defaultAtomicStatePredicate,
} = {}) {
  const { canonicalStateIdByGraphId, visibleStateGraphIdByCanonicalId } = buildCanonicalStateMaps(visibleStateNodes)
  const {
    inputsByActivity,
    outputsByActivity,
    outputsByActivitySet,
    consumersByStateId,
  } = buildEndpointIndexes(edges)
  const realizersByStateId = new Map()

  for (const edge of edges || []) {
    if (edge.type !== 'ACTIVITY_TO_STATE' || edge.binding_role !== 'output') continue
    const stateNodeId = graphStateNodeKey(edge.target_id)
    if (!stateNodeId) continue
    const activity = activityByGraphId.get(edge.source_id) || fallbackActivityGraphNode(edge.source_id)
    ensureListMapItem(realizersByStateId, stateNodeId).push({
      edge,
      activity,
      activityId: edge.source_id,
      binding: edgeBinding(edge, bindingById),
    })
  }

  const transitionsByStateId = new Map()
  const warningsByStateId = new Map()
  for (const node of visibleStateNodes || []) {
    const stateNodeId = stateNodeKey(node?.state_node_id)
    if (!stateNodeId) continue
    const realizers = uniqueTransitionRealizers(realizersByStateId.get(stateNodeId) || [])
    const consumerCount = consumersByStateId.get(stateNodeId) || 0
    const isInitialSource = isInitialTransitionSourceState(node, realizers, consumerCount, isAtomicStateNode)
    const preconditionKeys = new Set()
    const warnings = []
    for (const realizer of realizers) {
      for (const inputEdge of inputsByActivity.get(realizer.activityId) || []) {
        const stateNodeKeyValue = graphStateNodeKey(inputEdge.source_id)
        if (stateNodeKeyValue) preconditionKeys.add(String(stateNodeKeyValue))
      }
      if ((outputsByActivitySet.get(realizer.activityId)?.size || 0) > 1) {
        addTransitionWarning(warnings, MULTI_TARGET_LABEL)
      }
      if (realizer.activity?.atomic_activity_id && !realizer.binding?.op_rule_id && !realizer.edge?.op_rule_id) {
        addTransitionWarning(warnings, MISSING_RULE_LABEL)
      }
    }
    if (isAtomicStateNode(node) && !realizers.length && !isInitialSource) {
      addTransitionWarning(warnings, MISSING_REALIZER_LABEL)
    }
    if (realizers.length > 1) {
      addTransitionWarning(warnings, MULTI_ACTIVITY_LABEL)
    }
    if (!isAtomicStateNode(node) && realizers.length) {
      addTransitionWarning(warnings, AGGREGATE_TARGET_LABEL)
    }
    const transition = {
      stateNodeId,
      displayStateGraphId: String(node.id || ''),
      canonicalStateGraphId: `state_node:${stateNodeId}`,
      realizers,
      realizerIds: realizers.map((item) => item.activityId),
      realizerLabel: transitionRealizerLabel(realizers, { isInitialSource, nodeLabel }),
      preconditionCount: preconditionKeys.size,
      consumerCount,
      isInitialSource,
      warnings,
    }
    transitionsByStateId.set(stateNodeId, transition)
    warningsByStateId.set(stateNodeId, warnings)
  }

  const preconditionsByActivityId = new Map()
  for (const [activityId, inputs] of inputsByActivity.entries()) {
    preconditionsByActivityId.set(activityId, inputs.map((edge) => {
      const stateNodeId = graphStateNodeKey(edge.source_id)
      return {
        edge,
        binding: edgeBinding(edge, bindingById),
        stateNodeId,
        state: visibleStateNodes.find((node) => String(node.id) === String(edge.source_id)) ||
          fallbackStateGraphNode(edge.source_id) ||
          null,
      }
    }))
  }

  const semanticRelayGroups = buildRelayGroups({
    inputsByActivity,
    outputsByActivity,
    visibleStateNodes,
    nodeLabelForGraphId,
  })
  const { relayGroups, foldedRelayGroups } = projectRelayVisibility({
    semanticRelayGroups,
    visibleStateNodes,
    renderedStateNodes: renderedStateNodes || visibleStateNodes,
    bindingById,
  })
  const backboneEdges = buildTransitionBackboneEdges(relayGroups)
  const groupsByGraphId = buildStateGroupProjections({
    visibleStateNodes,
    renderedStateNodes: renderedStateNodes || visibleStateNodes,
    expandedStateGraphIds,
    collapsedStateContainerKeys,
    relayGroups: semanticRelayGroups,
  })
  const packageProxyEdges = buildPackageProxyEdges({
    foldedRelayGroups,
    visibleStateNodes,
    renderedStateNodes: renderedStateNodes || visibleStateNodes,
    bindingById,
    nodeLabelForGraphId,
  })
  const relayProxyEdges = backboneEdges.filter((edge) => edge.isCollapsedProxy)
  const proxyEdges = [...packageProxyEdges, ...relayProxyEdges]
  const visibleEdges = [...backboneEdges, ...packageProxyEdges]
  assignProxyEdgesToGroups(proxyEdges, groupsByGraphId)
  const { detailsByStateId, detailsByGraphId } = buildSelectedDetails({
    visibleStateNodes,
    transitionsByStateId,
    preconditionsByActivityId,
  })

  return {
    transitionsByStateId,
    detailsByStateId,
    detailsByGraphId,
    selectedDetails: detailsByStateId,
    semanticRelayGroups,
    relayGroups,
    backboneEdges,
    proxyEdges,
    visibleEdges,
    groupsByGraphId,
    canonicalStateIdByGraphId,
    visibleStateGraphIdByCanonicalId,
    warningsByStateId,
    realizersByStateId,
    outputsByActivityId: outputsByActivitySet,
    preconditionsByActivityId,
    consumersByStateId,
  }
}
