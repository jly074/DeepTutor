'use client'
import {useState} from 'react'
import {useTranslation} from 'react-i18next'
import {getAvailability,type Availability} from '../transport/api'

export function AvailabilityPanel(){
 const {t}=useTranslation()
 const [day,setDay]=useState(()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()))
 const [duration,setDuration]=useState(30)
 const [data,setData]=useState<Availability|null>(null)
 const [busy,setBusy]=useState(false)
 const [error,setError]=useState(false)
 async function calculate(){
  setBusy(true);setError(false);setData(null)
  try{setData(await getAvailability(day,'Asia/Taipei',duration))}catch{setError(true)}finally{setBusy(false)}
 }
 const show=(value:string)=>new Intl.DateTimeFormat(undefined,{timeZone:'Asia/Taipei',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value))
 return <details className="m-3 rounded-xl border border-border p-3">
  <summary className="cursor-pointer font-medium">{t('availability.title')}</summary>
  <p className="my-2 text-sm text-muted-foreground">{t('availability.notice')}</p>
  <div className="flex flex-wrap items-end gap-3">
   <label>{t('availability.date')}<input aria-label={t('availability.date')} type="date" value={day} disabled={busy} onChange={e=>{setDay(e.target.value);setData(null)}} className="block rounded border bg-background p-2"/></label>
   <label>{t('availability.duration')}<input type="number" min={1} max={540} value={duration} disabled={busy} onChange={e=>{setDuration(Number(e.target.value));setData(null)}} className="block w-24 rounded border bg-background p-2"/></label>
   <button disabled={busy||!day||duration<1||duration>540} onClick={()=>void calculate()} className="rounded border px-3 py-2 disabled:opacity-40">{t('availability.calculate')}</button>
  </div>
  {busy&&<p role="status">{t('Loading...')}</p>}
  {error&&<p role="alert">{t('availability.error')}</p>}
  {data&&<div className="mt-3 space-y-2 text-sm" data-testid="availability-result">
   <p>{data.date} · {data.tz} · {t('availability.revision')}: {data.revision} · {t('availability.busy')}: {data.busy_count}</p>
   <h3 className="font-medium">{t('availability.free')}</h3>
   {!data.free.length&&<p>{t('availability.none')}</p>}
   {data.free.map(s=><p key={s.start}>{show(s.start)} – {show(s.end)}</p>)}
   <h3 className="font-medium">{t('availability.conflicts')}</h3>
   {!data.conflicts.length&&<p>{t('availability.noConflicts')}</p>}
   {data.conflicts.map((s,i)=><div key={i} className="break-words"><p>{show(s.start)} – {show(s.end)} · {s.titles.map(title=>title||t('Untitled')).join(' / ')}</p><details className="break-all text-xs text-muted-foreground"><summary>{t('availability.evidence')}</summary>{s.occurrence_ids.join(' / ')}</details></div>)}
  </div>}
 </details>
}
