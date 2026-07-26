import { request } from './client'
import type { DashboardStats } from '@/types'

export function getDashboardStats(signal?: AbortSignal): Promise<DashboardStats> {
  return request<DashboardStats>('/dashboard', { signal })
}
