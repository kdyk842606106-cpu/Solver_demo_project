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
    const errorCode = data?.error_code ?? data?.detail?.error_code
    const status = error.response?.status
    const message = getErrorMessage(errorCode) ||
      data?.error_message ||
      data?.detail ||
      (status ? `HTTP ${status}` : '') ||
      error.message ||
      '请求失败'
    ElMessage.error(message)
    return Promise.reject(new Error(message))
  },
)

export default http
