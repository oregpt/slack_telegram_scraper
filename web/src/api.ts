import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_BASE,
})

export type TaskStatus = {
  status: 'running' | 'done' | 'error'
  logs: string[]
  result?: any
  error?: string
}

// Config
export async function loadConfig() {
  const { data } = await api.get('/api/config')
  return data
}

export async function saveConfig(config: any) {
  await api.post('/api/config', { config })
}

// Telegram auth
export async function tgLoginStart(payload: { api_id: number; api_hash: string; phone: string; session?: string }) {
  const { data } = await api.post('/api/telegram/login/start', payload)
  return data
}

export async function tgLoginComplete(payload: {
  api_id: number
  api_hash: string
  phone: string
  code: string
  password?: string
  session?: string
}) {
  const { data } = await api.post('/api/telegram/login/complete', payload)
  return data
}

// Exports
export async function startTelegramExport(payload: any) {
  const { data } = await api.post('/api/telegram/extract', payload)
  return data as { task_id: string }
}

export async function startSlackExport(payload: any) {
  const { data } = await api.post('/api/slack/extract', payload)
  return data as { task_id: string }
}

export async function getTask(taskId: string) {
  const { data } = await api.get(`/api/tasks/${taskId}`)
  return data as TaskStatus
}

export async function testSlack(token: string) {
  const { data } = await api.post('/api/slack/test', { token })
  return data
}

export async function testNotion(api_key: string, dest_type: string, parent_id: string) {
  const { data } = await api.post('/api/notion/test', { api_key, dest_type, parent_id })
  return data
}

export async function searchNotion(api_key: string, query: string, type?: 'database' | 'page' | 'all') {
  const { data } = await api.post('/api/notion/search', { api_key, query, type: type === 'all' ? undefined : type })
  return data as { results: { id: string; type: 'Database' | 'Page'; title: string }[] }
}

export async function listSlackChannels(token: string, query?: string, limit: number = 500) {
  const { data } = await api.post('/api/slack/channels', { token, query, limit })
  return data as { results: { id: string; name: string; is_private: boolean }[] }
}
