import http from './index'

// POST /solve — send solve request, returns enriched SolveResponse
export const postSolve = (payload) => http.post('/solve', payload)

// GET /plans/{id}/versions — version chain
export const getPlanVersions = (planId) => http.get(`/plans/${planId}/versions`)

// GET /plans/{baseId}/diff/{newId} — step-level diff
export const getPlanDiff = (basePlanId, newPlanId) =>
  http.get(`/plans/${basePlanId}/diff/${newPlanId}`)

// GET /solve-requests/{id} — query a specific solve request
export const getSolveRequest = (id) => http.get(`/solve-requests/${id}`)
