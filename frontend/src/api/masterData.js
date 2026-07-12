import http from './index'

// ── Machine Types ────────────────────────────────────────────
let machineTypesCache = null
let machineTypesInFlight = null

const clearMachineTypesCache = () => {
  machineTypesCache = null
  machineTypesInFlight = null
}

export const getMachineTypes = ({ force = false } = {}) => {
  if (!force && machineTypesCache) return Promise.resolve(machineTypesCache)
  if (!force && machineTypesInFlight) return machineTypesInFlight
  machineTypesInFlight = http.get('/machine-types')
    .then((data) => {
      machineTypesCache = data
      return data
    })
    .finally(() => {
      machineTypesInFlight = null
    })
  return machineTypesInFlight
}
export const createMachineType = async (data) => {
  const result = await http.post('/machine-types', data)
  clearMachineTypesCache()
  return result
}
export const updateMachineType = async (id, data) => {
  const result = await http.put(`/machine-types/${id}`, data)
  clearMachineTypesCache()
  return result
}
export const deleteMachineType = async (id) => {
  const result = await http.delete(`/machine-types/${id}`)
  clearMachineTypesCache()
  return result
}

// ── Machines ─────────────────────────────────────────────────
export const getMachines = (params = {}) => http.get('/machines', { params })
export const createMachine = (data) => http.post('/machines', data)
export const updateMachine = (id, data) => http.put(`/machines/${id}`, data)
export const deleteMachine = (id) => http.delete(`/machines/${id}`)

// ── Feature Defs (StateFeatureDef per machine type) ──────────
export const getFeatureDefs = (machineTypeId) =>
  http.get(`/machine-types/${machineTypeId}/feature-defs`)
export const createFeatureDef = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/feature-defs`, data)
export const updateFeatureDef = (id, data) => http.put(`/feature-defs/${id}`, data)
export const deleteFeatureDef = (id) => http.delete(`/feature-defs/${id}`)

// ── Feature Definitions (global feature_definition table) ────
export const getFeatureDefinitions = () => http.get('/features')
export const getBlockageReasons = () => http.get('/features/blockage-reasons')
export const createFeatureDefinition = (data) => http.post('/features', data)
export const updateFeatureDefinition = (key, data) => http.put(`/features/${key}`, data)
export const deleteFeatureDefinition = (key) => http.delete(`/features/${key}`)

// ── Layered Activity Nodes ──────────────────────────────────
export const getActivityNodes = (machineTypeId) =>
  http.get(`/machine-types/${machineTypeId}/activity-nodes`)
export const createActivityNode = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/activity-nodes`, data)
export const updateActivityNode = (id, data) => http.put(`/activity-nodes/${id}`, data)
export const deleteActivityNode = (id) => http.delete(`/activity-nodes/${id}`)

// Atomic Activities
export const getAtomicActivities = (machineTypeId) =>
  http.get(`/machine-types/${machineTypeId}/atomic-activities`)
export const createAtomicActivity = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/atomic-activities`, data)
export const updateAtomicActivity = (id, data) => http.put(`/atomic-activities/${id}`, data)
export const deleteAtomicActivity = (id) => http.delete(`/atomic-activities/${id}`)
export const getActivityPackageAtomicRefs = (packageId) =>
  http.get(`/activity-nodes/${packageId}/atomic-activity-refs`)
export const createActivityPackageAtomicRef = (packageId, data) =>
  http.post(`/activity-nodes/${packageId}/atomic-activity-refs`, data)
export const deleteActivityPackageAtomicRef = (id) =>
  http.delete(`/activity-package-atomic-refs/${id}`)

// ── Layered State Nodes ─────────────────────────────────────
export const getStateNodes = (machineTypeId) =>
  http.get(`/machine-types/${machineTypeId}/state-nodes`)
export const createStateNode = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/state-nodes`, data)
export const updateStateNode = (id, data) => http.put(`/state-nodes/${id}`, data)
export const deleteStateNode = (id) => http.delete(`/state-nodes/${id}`)

// ── Scope Guards ────────────────────────────────────────────
export const getScopeGuards = (activityNodeId) =>
  http.get(`/activity-nodes/${activityNodeId}/scope-guards`)
export const createScopeGuard = (activityNodeId, data) =>
  http.post(`/activity-nodes/${activityNodeId}/scope-guards`, data)
export const updateScopeGuard = (id, data) => http.put(`/scope-guards/${id}`, data)
export const deleteScopeGuard = (id) => http.delete(`/scope-guards/${id}`)

// ── Layered Expansion Preview ───────────────────────────────
export const previewLayeredExpansion = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/layered-expansion`, data)

export const checkLayeredHealth = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/layered-health-check`, data)

export const getMaintenanceIntentTemplates = (machineTypeId, params = {}) =>
  http.get(`/machine-types/${machineTypeId}/maintenance-intent-templates`, { params })
export const createMaintenanceIntentTemplate = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/maintenance-intent-templates`, data)
export const updateMaintenanceIntentTemplate = (id, data) =>
  http.put(`/maintenance-intent-templates/${id}`, data)
export const deleteMaintenanceIntentTemplate = (id) =>
  http.delete(`/maintenance-intent-templates/${id}`)

// ── Machine States ────────────────────────────────────────────
export const getStates = (machineId) => http.get(`/machines/${machineId}/states`)
export const createState = (machineId, data) =>
  http.post(`/machines/${machineId}/states`, data)
export const updateState = (id, data) => http.put(`/states/${id}`, data)
export const deleteState = (id) => http.delete(`/states/${id}`)

// ── Op Rules ─────────────────────────────────────────────────
export const getOpRules = (machineTypeId) =>
  http.get(`/machine-types/${machineTypeId}/op-rules`)
export const createOpRule = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/op-rules`, data)
export const updateOpRule = (id, data) => http.put(`/op-rules/${id}`, data)
export const deleteOpRule = (id) => http.delete(`/op-rules/${id}`)

// ── Resources ─────────────────────────────────────────────────
export const getResources = (machineId, params = {}) =>
  http.get('/resources', { params: { ...params, machine_id: machineId } })
export const createResource = (data) => http.post('/resources', data)
export const updateResource = (id, data) => http.put(`/resources/${id}`, data)
export const deleteResource = (id) => http.delete(`/resources/${id}`)

// Scenario Import
export const importScenario = (file, { dryRun = true } = {}) => {
  const form = new FormData()
  form.append('file', file)
  form.append('mode', 'scenario_upsert')
  form.append('dry_run', dryRun ? 'true' : 'false')
  return http.post('/imports/scenario', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

export const downloadScenarioTemplate = () =>
  http.get('/imports/scenario-template', { responseType: 'blob' })

// Network editor references and bindings
export const getStateNodeReferences = (machineTypeId) =>
  http.get(`/machine-types/${machineTypeId}/state-node-references`)
export const createStateNodeReference = (stateNodeId, data) =>
  http.post(`/state-nodes/${stateNodeId}/references`, data)
export const deleteStateNodeReference = (id) => http.delete(`/state-node-references/${id}`)

export const getActivityStateBindings = (machineTypeId) =>
  http.get(`/machine-types/${machineTypeId}/activity-state-bindings`)
export const createActivityStateBinding = (data) =>
  http.post('/activity-state-bindings', data)
export const updateActivityStateBinding = (id, data) =>
  http.put(`/activity-state-bindings/${id}`, data)
export const deleteActivityStateBinding = (id) => http.delete(`/activity-state-bindings/${id}`)
export const refreshActivityStateBindingCoverage = (id) =>
  http.post(`/activity-state-bindings/${id}/refresh-coverage`)
export const previewNetworkEditorGraph = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/network-editor/graph`, data)
export const validateNetworkEditor = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/network-editor/validate`, data)
export const analyzeNetworkEditorImpact = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/network-editor/impact`, data, { silentError: true })
export const precheckNetworkEditorSolver = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/network-editor/solver-precheck`, data)
export const commitNetworkEditorDraft = (machineTypeId, data) =>
  http.post(`/machine-types/${machineTypeId}/network-editor/commit`, data, { silentError: true })
