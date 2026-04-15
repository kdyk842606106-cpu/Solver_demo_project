import http from './index'

// ── Machine Types ────────────────────────────────────────────
export const getMachineTypes = () => http.get('/machine-types')
export const createMachineType = (data) => http.post('/machine-types', data)
export const updateMachineType = (id, data) => http.put(`/machine-types/${id}`, data)
export const deleteMachineType = (id) => http.delete(`/machine-types/${id}`)

// ── Machines ─────────────────────────────────────────────────
export const getMachines = () => http.get('/machines')
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
export const createFeatureDefinition = (data) => http.post('/features', data)
export const updateFeatureDefinition = (key, data) => http.put(`/features/${key}`, data)
export const deleteFeatureDefinition = (key) => http.delete(`/features/${key}`)

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
export const getResources = () => http.get('/resources')
export const createResource = (data) => http.post('/resources', data)
export const updateResource = (id, data) => http.put(`/resources/${id}`, data)
export const deleteResource = (id) => http.delete(`/resources/${id}`)
