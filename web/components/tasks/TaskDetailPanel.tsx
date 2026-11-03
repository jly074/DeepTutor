'use client'
import {useEffect,useState} from 'react'
import Link from 'next/link'
import {ClipboardList,FileText} from 'lucide-react'
import {useTranslation} from 'react-i18next'
import {scopedUrl} from '@/lib/workspace-scope'
import {subPanelClass} from '@/components/settings/shared'
import {taskDetailRequest,TaskDetailError,type TaskDetailData,type EvidenceChoices} from '@/lib/task-detail-api'

export default function TaskDetailPanel({taskId,workspaceId}:{taskId:string;workspaceId:string}){
 const {t}=useTranslation()
 const [data,setData]=useState<TaskDetailData|null>(null)
 const [choices,setChoices]=useState<EvidenceChoices|null>(null)
 const [source,setSource]=useState('')
 const [announcement,setAnnouncement]=useState('')
 const [consent,setConsent]=useState(false)
 const [busy,setBusy]=useState(true)
 const [error,setError]=useState('')
 const report=(e:unknown)=>setError(e instanceof TaskDetailError&&['not_found','source_changed','source_unavailable','stale_revision','already_linked','task_archived','link_limit','storage_unavailable'].includes(e.code)?e.code:'blocked')
 useEffect(()=>{
  let active=true
  Promise.all([taskDetailRequest<TaskDetailData>(workspaceId,taskId),taskDetailRequest<EvidenceChoices>(workspaceId,taskId,'evidence-choices')]).then(([d,c])=>{if(active){setData(d);setChoices(c)}}).catch(e=>{if(active)report(e)}).finally(()=>{if(active)setBusy(false)})
  return()=>{active=false}
 },[taskId,workspaceId])
 async function reload(){setBusy(true);setError('');try{setData(await taskDetailRequest(workspaceId,taskId));setChoices(await taskDetailRequest(workspaceId,taskId,'evidence-choices'));setSource('');setAnnouncement('');setConsent(false)}catch(e){report(e)}finally{setBusy(false)}}
 async function link(){
  const selected=choices?.sources[Number(source)];if(source===''||!selected)return
  setBusy(true);setError('')
  try{setData(await taskDetailRequest(workspaceId,taskId,'evidence',{provider:selected.provider,mode:selected.mode,source_id:selected.source_id,fingerprint:selected.fingerprint}));setSource('')}catch(e){report(e)}finally{setBusy(false)}
 }
 const picked=choices?.announcements.find(a=>a.id===announcement)
 async function adopt(){
  if(!picked||!data||!consent)return
  setBusy(true);setError('')
  try{setData(await taskDetailRequest(workspaceId,taskId,'deadline-source',{confirm:true,announcement_id:picked.id,announcement_revision:picked.revision,expected_updated_at:data.task.updated_at}));setChoices(await taskDetailRequest(workspaceId,taskId,'evidence-choices'));setAnnouncement('');setConsent(false)}catch(e){report(e)}finally{setBusy(false)}
 }
 const disabled=busy||!!data?.task.archived
 return <main className="mx-auto w-full max-w-3xl space-y-5 overflow-y-auto p-5 sm:p-8">
  <Link href={scopedUrl('/kanban',workspaceId)} className="text-sm underline">{t('inbox.tasks')}</Link>
  <h1 className="flex gap-2 text-2xl font-semibold"><ClipboardList size={26}/>{data?.task.title||t('detail.title')}</h1>
  <p className="break-all text-sm">{t('detail.taskId')}: {taskId}</p>
  <p className="text-sm text-muted-foreground">{t('detail.boundary')}</p>
  <button disabled={busy} onClick={()=>void reload()} className="rounded-lg border border-border px-3 py-2">{t('inbox.refresh')}</button>
  {busy&&<p role="status">{t('Loading...')}</p>}
  {error&&<p role="alert" className="text-sm text-destructive">{t(`detail.error.${error}`)}</p>}
  {data&&<>
   <section className={`${subPanelClass} space-y-2 p-4`}>
    <p>{t(data.task.archived?'inbox.archived':`inbox.task.${data.task.status}`)}</p>
    <p data-testid="task-current-deadline">{t('detail.currentDue')}: {data.task.due_date||t('inbox.unknown')}</p>
    <p className="text-sm text-muted-foreground">{t('detail.dateNotice')}</p>
   </section>
   <section className="space-y-3"><h2 className="font-semibold">{t('detail.announcements')}</h2>
    <p className="text-sm text-muted-foreground">{t('detail.slackNotice')}</p>
    {!data.announcements.length&&<p>{t('detail.missingAnnouncement')}</p>}
    {data.announcements.map(a=><article key={a.id} className={`${subPanelClass} space-y-2 p-4`}>
     <h3 className="font-medium">{a.title}</h3><p className="text-sm">{t(a.simulated?'inbox.synthetic':'inbox.manual')}</p>
     <p className="break-all text-xs">{a.source_label} · {a.source_key} · {a.id}</p><p className="whitespace-pre-wrap break-words text-sm">{a.body}</p>
     <p className="text-sm">{t('detail.sourceDue')}: {a.due_date||t('inbox.unknown')}</p>
     {a.source_url&&<a href={a.source_url} target="_blank" rel="noopener noreferrer" className="text-sm underline">{t('inbox.source')}</a>}
    </article>)}
    <Link href={scopedUrl('/learning/inbox',workspaceId)} className="text-sm underline">{t('detail.inboxLink')}</Link>
    <label className="block text-sm">{t('detail.chooseAnnouncement')}<select value={announcement} disabled={disabled} onChange={e=>{setAnnouncement(e.target.value);setConsent(false)}} className="mt-1 block w-full rounded-lg border border-border bg-background p-2"><option value="">{t('detail.select')}</option>{choices?.announcements.map(a=><option key={a.id} value={a.id}>{a.simulated?'[Synthetic] ':''}{a.source_label} / {a.source_key} / {a.due_date||t('inbox.unknown')}</option>)}</select></label>
    {picked&&<p className="text-sm">{data.task.due_date||t('inbox.unknown')} → {picked.due_date||t('inbox.unknown')}</p>}
    <label className="flex gap-2 text-sm"><input type="checkbox" checked={consent} disabled={disabled||!picked} onChange={e=>setConsent(e.target.checked)}/>{t('detail.dateConsent')}</label>
    <button disabled={disabled||!picked||!consent} onClick={()=>void adopt()} className="rounded-lg border border-border px-3 py-2 disabled:opacity-40">{t('detail.adopt')}</button>
   </section>
   <section className="space-y-3"><h2 className="font-semibold">{t('detail.history')}</h2>
    {!data.deadline_history.length&&<p className="text-sm">{t('detail.noHistory')}</p>}
    {data.deadline_history.map(h=><article key={h.seq} data-testid="deadline-history-row" className={`${subPanelClass} space-y-1 p-3 text-sm`}>
     <p>{h.old_date||t('inbox.unknown')} → {h.new_date||t('inbox.unknown')}</p><p className="break-all">{h.basis.kind==='announcement'?`${h.basis.source_label} / ${h.basis.source_key} / ${h.basis.announcement_id}`:t('detail.manualDate')}</p><p className="text-xs text-muted-foreground">#{h.seq} · {h.created_at}</p>
    </article>)}
   </section>
   <section className="space-y-3"><h2 className="font-semibold">{t('detail.sources')}</h2>
    {(choices?.announcement_limited||choices?.states.some(s=>s.limited))&&<p role="status">{t('detail.choiceLimit')}</p>}
    <p className="text-sm text-muted-foreground">{t('detail.snapshotNotice')}</p>
    <div className="flex flex-wrap gap-3 text-sm underline"><Link href={scopedUrl('/learning/drive',workspaceId)}>{t('drive.title')}</Link><Link href={scopedUrl('/learning/notion',workspaceId)}>{t('notion.title')}</Link></div>
    {choices?.states.filter(s=>s.mode==='live').map(s=><p key={s.provider} className="text-xs text-muted-foreground">{s.provider}: {t(`detail.state.${s.state}`)}</p>)}
    <label className="block text-sm">{t('detail.chooseSource')}<select value={source} disabled={disabled} onChange={e=>setSource(e.target.value)} className="mt-1 block w-full rounded-lg border border-border bg-background p-2"><option value="">{t('detail.select')}</option>{choices?.sources.map((s,i)=><option key={`${s.provider}:${s.mode}:${s.source_id}`} value={i}>{s.mode==='demo'?'[Synthetic] ':''}{s.provider}: {s.label}</option>)}</select></label>
    <button disabled={disabled||source===''} onClick={()=>void link()} className="rounded-lg border border-border px-3 py-2 disabled:opacity-40">{t('detail.link')}</button>
    {data.links.map(l=><article key={l.id} data-testid="task-evidence" className={`${subPanelClass} space-y-2 p-4`}>
     <h3 className="flex gap-2 font-medium"><FileText size={18}/>{l.snapshot.label}</h3><p className="text-sm">#{l.id} · {l.provider} · {t(l.mode==='demo'?'inbox.synthetic':'detail.savedUnverified')}</p>
     <p className="break-all text-xs">{l.snapshot.source_id} · {l.snapshot.metadata.last_edited_time||l.snapshot.metadata.modified_time||t('inbox.unknown')}</p>
     {l.open_url&&<a href={l.open_url} target="_blank" rel="noopener noreferrer" className="text-sm underline">{t('detail.openOriginal')}</a>}
     {l.provider==='drive'&&l.mode==='demo'&&<details><summary className="cursor-pointer text-sm underline">{t('detail.openDemo')}</summary><p className="mt-2 text-sm">{t('detail.demoMaterial')}</p></details>}
     {l.provider==='notion'&&<dl className="space-y-2 text-sm">{Object.entries(l.snapshot.metadata.fields||{}).map(([key,f])=><div key={key}><dt className="font-medium">{f.name} ({f.type})</dt><dd className="whitespace-pre-wrap break-words">{f.value===null?t('inbox.unknown'):typeof f.value==='string'?f.value:JSON.stringify(f.value)}</dd></div>)}</dl>}
    </article>)}
   </section>
   <section className={`${subPanelClass} space-y-3 p-4`}><h2 className="font-semibold">{t('detail.next')}</h2>
    <p className="text-sm text-muted-foreground">{t('detail.nextNotice')}</p>
    {data.next_steps.map(step=><div key={step.code} className="text-sm"><p>{t(`detail.next.${step.code}`)}</p><p className="break-all text-xs text-muted-foreground">{t('detail.evidenceIds')}: {step.evidence_ids.join(', ')||t('detail.missing')}</p></div>)}
   </section>
  </>}
 </main>
}
