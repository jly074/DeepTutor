'use client'
import {useRef,useState} from 'react'
import {useTranslation} from 'react-i18next'
import {randomUuid} from '@/lib/random-uuid'
import {savePracticeGuidance,type PracticeGuidance} from '@/lib/practice-api'

export function GuidancePanel({id,workspaceId,data,onSaved}:{id:number;workspaceId?:string;data:PracticeGuidance;onSaved:()=>void}){
 const {t}=useTranslation()
 const [form,setForm]=useState(data.config)
 const [busy,setBusy]=useState(false)
 const [error,setError]=useState(false)
 const [locked,setLocked]=useState(false)
 const pending=useRef<(typeof form&{request_id:string})|null>(null)
 async function save(){
  if(busy)return
  setBusy(true);setError(false);setLocked(true)
  pending.current??={...form,request_id:randomUuid()}
  try{await savePracticeGuidance(id,pending.current,workspaceId);onSaved()}catch{setError(true)}finally{setBusy(false)}
 }
 return <section className="my-4 space-y-3 rounded-xl border border-border p-4 text-sm">
  <h3 className="font-semibold">{t('guidance.title')}</h3>
  <p>{t(`guidance.status.${data.status}`)}</p>
  <p className="text-xs text-muted-foreground">{t('guidance.notice')}</p>
  {data.due_at&&<p>{t('guidance.due')}: {new Date(data.due_at*1000).toLocaleString()}</p>}
  <p className="break-all text-xs">{t('guidance.evidence')}: {data.evidence_ids.join(', ')||t('Unknown')}</p>
  <details><summary>{t('guidance.edit')}</summary>
   <fieldset disabled={busy||locked} className="mt-3 space-y-3">
    <label className="block">{t('guidance.quality')}<select aria-label={t('guidance.quality')} value={form.quality} onChange={e=>setForm({...form,quality:e.target.value as typeof form.quality})} className="block rounded border bg-background p-2">{['unknown','ready','missing_image','disputed'].map(v=><option key={v} value={v}>{t('guidance.quality.'+v)}</option>)}</select></label>
    <label className="block">{t('guidance.kind')}<select aria-label={t('guidance.kind')} value={form.kind} onChange={e=>setForm({...form,kind:e.target.value as typeof form.kind})} className="block rounded border bg-background p-2">{['unknown','original','recalled','adapted','simulated'].map(v=><option key={v} value={v}>{t('guidance.kind.'+v)}</option>)}</select></label>
    <label className="block">{t('guidance.note')}<textarea maxLength={4000} value={form.note} onChange={e=>setForm({...form,note:e.target.value})} className="block w-full rounded border bg-background p-2"/></label>
    <label className="block">{t('guidance.reference')}<input maxLength={1000} value={form.reference} onChange={e=>setForm({...form,reference:e.target.value})} className="block w-full rounded border bg-background p-2"/></label>
   </fieldset>
   <button disabled={busy||!!form.note.trim()&&!form.reference.trim()} onClick={()=>void save()} className="mt-3 rounded border px-3 py-2">{t('guidance.save')}</button>
   {error&&<p role="alert">{t('guidance.error')}</p>}
  </details>
  <p>{t('guidance.kind')}: {t('guidance.kind.'+data.config.kind)}</p>
  {data.config.note&&<div><p className="whitespace-pre-wrap">{data.config.note}</p><p className="text-xs">{t('guidance.reference')}: {data.config.reference}</p></div>}
  <details><summary>{t('guidance.history')}</summary>{data.attempts.map(a=><p className="break-all" key={a.request_id}>{new Date(a.at*1000).toLocaleString()} · {a.answer} · {t(a.self_report?'guidance.self':a.correct===null?'guidance.ungraded':a.correct?'Correct':'Needs another try')} · {t(a.current_version?'guidance.current':'guidance.previous')}</p>)}</details>
 </section>
}
