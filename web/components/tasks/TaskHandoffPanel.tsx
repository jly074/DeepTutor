'use client'
import {useEffect,useState} from 'react'
import {useTranslation} from 'react-i18next'
import {subPanelClass} from '@/components/settings/shared'
import {taskDetailRequest,type TaskEvidence} from '@/lib/task-detail-api'

type Summary={format:string;id:string;issuer:string;task_id:string;version:string;status:string;issued_at:string;expires_at:string;next_step:string;reference_ids:number[]}
type Receipt={summary:Summary;accepted_at:string|null;current?:boolean}
export default function TaskHandoffPanel({taskId,workspaceId,links}:{taskId:string;workspaceId:string;links:TaskEvidence[]}){
 const {t}=useTranslation()
 const [next,setNext]=useState(''),[refs,setRefs]=useState<number[]>([]),[consent,setConsent]=useState(false)
 const [draft,setDraft]=useState<Summary|null>(null),[verified,setVerified]=useState<Receipt|null>(null),[history,setHistory]=useState<Receipt[]>([])
 const [busy,setBusy]=useState(false),[error,setError]=useState('')
 const request=<T,>(path:string,body?:unknown)=>taskDetailRequest<T>(workspaceId,taskId,path,body)
 const report=(e:unknown)=>setError(e instanceof Error&&['handoff_stale','handoff_unverified','handoff_expired','task_archived','source_unavailable','storage_unavailable'].includes(e.message)?e.message:'blocked')
 useEffect(()=>{let active=true;taskDetailRequest<{items:Receipt[]}>(workspaceId,taskId,'handoffs').then(r=>{if(active)setHistory(r.items)}).catch(()=>{if(active)setError('blocked')});return()=>{active=false}},[taskId,workspaceId,links])
 async function prepare(){setBusy(true);setError('');setDraft(null);try{setDraft(await request<Summary>('handoff-export',{consent:true,next_step:next,reference_ids:refs}))}catch(e){report(e)}finally{setBusy(false)}}
 function download(){if(!draft)return;const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`task-handoff-${draft.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 async function load(file?:File){setVerified(null);setError('');if(!file)return;setBusy(true);try{if(file.size>16384)throw new Error('blocked');const summary=JSON.parse(await file.text());setVerified(await request<Receipt>('handoff-import',{summary,confirm:false}))}catch(e){report(e)}finally{setBusy(false)}}
 async function accept(){if(!verified)return;setBusy(true);setError('');try{const result=await request<Receipt>('handoff-import',{summary:verified.summary,confirm:true});setVerified(result);setHistory((await request<{items:Receipt[]}>('handoffs')).items)}catch(e){setVerified(null);report(e)}finally{setBusy(false)}}
 return <section className={`${subPanelClass} space-y-3 p-4`}>
  <h2 className="font-semibold">{t('handoff.title')}</h2><p className="text-sm text-muted-foreground">{t('handoff.boundary')}</p>
  <label className="block text-sm">{t('handoff.next')}<textarea value={next} maxLength={500} disabled={busy} onChange={e=>{setNext(e.target.value);setConsent(false);setDraft(null)}} className="mt-1 block w-full rounded-lg border border-border bg-background p-2"/></label>
  <p className="text-sm">{t('handoff.refs')}</p>{links.map(l=><label key={l.id} className="flex gap-2 text-sm"><input type="checkbox" checked={refs.includes(l.id)} disabled={busy} onChange={e=>{setRefs(e.target.checked?[...refs,l.id]:refs.filter(id=>id!==l.id));setConsent(false);setDraft(null)}}/>#{l.id} {l.provider} ({l.mode})</label>)}
  <label className="flex gap-2 text-sm"><input type="checkbox" checked={consent} disabled={busy} onChange={e=>setConsent(e.target.checked)}/>{t('handoff.consent')}</label>
  <button disabled={busy||!consent} onClick={()=>void prepare()} className="rounded-lg border border-border px-3 py-2 disabled:opacity-40">{t('handoff.prepare')}</button>
  {draft&&<><pre data-testid="handoff-export" className="max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(draft,null,2)}</pre><button disabled={busy||!consent} onClick={download} className="rounded-lg border border-border px-3 py-2">{t('handoff.download')}</button></>}
  <label className="block text-sm">{t('handoff.import')}<input type="file" accept=".json,application/json" disabled={busy} onChange={e=>{void load(e.target.files?.[0]);e.target.value=''}} className="mt-1 block w-full text-sm"/></label>
  {verified&&<div className="space-y-2"><p>{t('handoff.verified')}</p><pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(verified.summary,null,2)}</pre><button disabled={busy||!!verified.accepted_at} onClick={()=>void accept()} className="rounded-lg border border-border px-3 py-2 disabled:opacity-40">{t(verified.accepted_at?'handoff.accepted':'handoff.accept')}</button></div>}
  {busy&&<p role="status">{t('Loading...')}</p>}{error&&<p role="alert" className="text-sm text-destructive">{t(`handoff.error.${error}`)}</p>}
  <h3 className="text-sm font-medium">{t('handoff.history')}</h3>{history.map(r=><article key={r.summary.id} data-testid="handoff-history" className="space-y-1 break-all border-t border-border pt-2 text-sm"><p>{t(r.current?'handoff.current':'handoff.historical')}</p><p>{r.summary.task_id} · {r.summary.status}</p><p>{r.summary.next_step||t('handoff.noNext')}</p><p>{t('handoff.refs')}: {r.summary.reference_ids.join(', ')||'-'}</p><details><summary>{t('handoff.source')}</summary><p>{r.summary.issuer} / {r.summary.id}</p><p>{r.summary.issued_at} → {r.summary.expires_at}</p><p>{r.summary.version}</p><p>{r.accepted_at}</p></details></article>)}
 </section>
}
