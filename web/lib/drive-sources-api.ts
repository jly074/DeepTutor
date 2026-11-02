import { apiFetch, apiUrl } from '@/lib/api'
import { scopedUrl } from '@/lib/workspace-scope'

export type DriveMode = 'live' | 'demo'
export type DriveState = 'not_connected' | 'needs_authorization' | 'mock' | 'queryable' | 'blocked'
export interface DriveSource {
  id: string
  label: string
  source_id: string
  available: boolean
  metadata: { simulated: boolean; file_id: string; folder_id: string; version: string }
}
export interface DriveFile { id: string; name: string; mimeType: string; modifiedTime: string; version: string }
export interface DriveOverview { state: DriveState; simulated: boolean; allowed_folders: string[]; sources: DriveSource[] }
export class DriveRequestError extends Error {
  constructor(public state: DriveState) { super(state) }
}
export async function driveRequest<T>(path: string, workspace: string, mode: DriveMode, init?: RequestInit): Promise<T> {
  const url = new URL(`/api/drive-sources${path}`, 'http://workspace.local')
  url.searchParams.set('mode', mode)
  const response = await apiFetch(apiUrl(scopedUrl(`${url.pathname}${url.search}`, workspace)), {
    cache: 'no-store', skipAuthRedirect: true, ...init,
  })
  if (!response.ok) throw new DriveRequestError(response.status === 401 ? 'needs_authorization' : 'blocked')
  return response.json()
}
