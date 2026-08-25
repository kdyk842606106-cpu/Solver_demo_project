import axios from 'axios'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '../utils/errorCodes'

const http = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const data = error.response?.data
    const detail = data?.detail
    const nested = data?.error_message && typeof data.error_message === 'object' ? data.error_message : null
    const detailCode = typeof detail === 'string' && /^[A-Z0-9_]+$/.test(detail) ? detail : null
    const errorCode = nested?.error_code ?? detail?.error_code ?? data?.error_code ?? detailCode
    const status = error.response?.status
    const message = (errorCode ? getErrorMessage(errorCode) : '') ||
      nested?.error_message || nested?.message ||
      (typeof data?.error_message === 'string' ? data.error_message : '') ||
      (typeof detail === 'string' ? detail : detail?.message) ||
      (status ? `HTTP ${status}` : '') ||
      error.message ||
      '请求失败'
    const normalizedError = new Error(message)
    normalizedError.status = status
    normalizedError.errorCode = errorCode
    normalizedError.response = error.response
    normalizedError.data = data
    if (!error.config?.silentError) {
      ElMessage.error(message)
    }
    return Promise.reject(normalizedError)
  },
)

export default http
