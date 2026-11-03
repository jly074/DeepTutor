import { apiFetch } from '@/lib/api'
import { taskBoardUrl, type TaskCard } from '@/lib/task-board-api'
import type { Announcement } from '@/lib/announcement-inbox-api'
import type { NotionRow } from '@/lib/notion-sources-api'
export interface EvidenceChoice { provider:'drive'|'notion';mode:'demo'|'live';source_id:string;label:string;fingerprint:string }
export interface TaskEvidence {
 id:number;provider:'drive'|'notion';mode:'demo'|'live';linked_at:string;open_url:string|null;access:string;
 snapshot:{id:string;label:string;source_id:string;metadata:{fields?:NotionRow['fields'];last_edited_time?:string;modified_time?:string;version?:string;file_id?:string;notion_page_id?:string}}
}
export interface TaskDetailData {
 task:TaskCard;announcements:Announcement[];links:TaskEvidence[];
 deadline_history:{seq:number;old_date:string|null;new_date:string|null;created_at:string;basis:{kind:string;announcement_id?:string;source_label?:string;source_key?:string;source_url?:string;simulated?:boolean}}[];
 next_steps:{code:string;evidence_ids:string[]}[];
}
export interface EvidenceChoices { announcement_limited?:boolean;sources:EvidenceChoice[];announcements:Announcement[];states:{provider:string;mode:string;state:string;limited:boolean}[] }
export class TaskDetailError extends Error {constructor(public code:string){super(code)}}
export async function taskDetailRequest<T>(workspace:string,id:string,suffix='detail',body?:unknown):Promise<T>{
 const response=await apiFetch(taskBoardUrl(`/cards/${encodeURIComponent(id)}/${suffix}`,workspace),{cache:'no-store',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})})
 if(!response.ok){let code='blocked';try{code=(await response.json()).detail?.code||code}catch{/* safe generic error */}throw new TaskDetailError(code)}
 return response.json()
}
