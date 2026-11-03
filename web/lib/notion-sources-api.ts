import { apiFetch, apiUrl } from '@/lib/api'
import { scopedUrl } from '@/lib/workspace-scope'
export type NotionMode = 'live' | 'demo'
export interface NotionProperty { id: string; name: string; type: string; supported: boolean }
export interface NotionRow { page_id: string; edited_at: string; title: string; fields: Record<string, { name: string; type: string; value: unknown }>; issues: string[]; fingerprint: string }
export interface NotionSnapshot { id: string; source_id: string; label: string; available: boolean; metadata: { simulated: boolean; notion_page_id: string; data_source_id: string; last_edited_time: string; fingerprint: string; fields: NotionRow['fields'] } }
export interface NotionOverview { state: string; simulated: boolean; data_source_id: string; sources: NotionSnapshot[] }
export interface NotionPreview { rows: NotionRow[]; next_cursor: string | null; has_more: boolean; simulated: boolean }
export class NotionRequestError extends Error { constructor(public code: string) { super(code) } }
export async function notionRequest<T>(path: string, workspace: string, mode: NotionMode, body?: unknown): Promise<T> {
  const response = await apiFetch(apiUrl(scopedUrl(`/api/notion-sources${path}?mode=${mode}`, workspace)), {
    cache: 'no-store', skipAuthRedirect: true,
    ...(body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  })
  if (!response.ok) {
    let code = 'blocked'
    try { code = (await response.json()).detail?.code || code } catch { /* never display raw response */ }
    throw new NotionRequestError(code)
  }
  return response.json()
}
