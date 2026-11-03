import { apiFetch } from '@/lib/api'
import { taskBoardUrl } from '@/lib/task-board-api'
export interface Announcement {
  id: string; seq: number; title: string; body: string; source_label: string; source_key: string;
  source_url: string; due_date: string | null; simulated: boolean; reviewed: boolean;
  revision: number; created_at: string; task_id: string | null;
  task: { id: string; status: 'todo'|'doing'|'done'; archived: boolean } | null;
}
export interface InboxPage { items: Announcement[]; next_cursor: number | null; slack_connected: false }
export class InboxRequestError extends Error { constructor(public code: string){super(code)} }
export async function inboxRequest<T>(workspace: string, path='', method='GET', body?: unknown): Promise<T> {
  const response=await apiFetch(taskBoardUrl(`/inbox${path}`,workspace),{
    method,cache:'no-store',headers:{'Content-Type':'application/json'},
    ...(body===undefined?{}:{body:JSON.stringify(body)}),
  })
  if(!response.ok){
    let code='blocked'
    try{code=(await response.json()).detail?.code||code}catch{/* no raw server response */}
    throw new InboxRequestError(code)
  }
  return response.json()
}
