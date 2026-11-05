import {apiFetch} from '@/shared/api/client'
import {taskBoardUrl} from '@/lib/task-board-api'
export interface IntakeVersion {id:string;source_id:string;filename:string;sha256:string;size_bytes:number;data_class:string;status:'pending'|'collected';category:string;revision:number;created_at:number}
export interface IntakePage {items:IntakeVersion[];next_offset:number|null}
export interface IntakeResult {filename:string;ok:boolean;duplicate?:boolean;item?:IntakeVersion;code?:string}
export async function intakeRequest<T>(workspace:string,path:string,body?:FormData|object):Promise<T>{
 const form=body instanceof FormData
 const response=await apiFetch(taskBoardUrl('/intake'+path,workspace),{cache:'no-store',method:body?'POST':'GET',...(body?{body:form?body:JSON.stringify(body),headers:form?{}:{'Content-Type':'application/json'}}:{})})
 if(!response.ok){const detail=await response.json().catch(()=>({}));throw new Error(detail?.detail?.code==='original_unavailable'?'original_unavailable':'request_failed')}
 return response.json()
}
export async function downloadOriginal(workspace:string,item:IntakeVersion){
 const r=await apiFetch(taskBoardUrl('/intake/original/'+encodeURIComponent(item.id),workspace),{cache:'no-store'})
 if(!r.ok)throw new Error('original_unavailable')
 const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download=item.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
