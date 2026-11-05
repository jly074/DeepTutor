'use client'
import {useEffect,useState} from 'react'
import Link from 'next/link'
import {FolderInput} from 'lucide-react'
import {useTranslation} from 'react-i18next'
import {scopedUrl} from '@/lib/workspace-scope'
import {intakeRequest,downloadOriginal,type IntakeVersion,type IntakePage,type IntakeResult} from '@/lib/unsorted-api'
export default function UnsortedInbox({workspaceId}:{workspaceId:string}){
 const {t}=useTranslation()
 const [items,setItems]=useState<IntakeVersion[]>([])
 const [next,setNext]=useState<number|null>(null)
 const [files,setFiles]=useState<File[]>([])
 const [dataClass,setDataClass]=useState('synthetic')
 const [consent,setConsent]=useState(false)
 const [target,setTarget]=useState<IntakeVersion|null>(null)
 const [selected,setSelected]=useState<string[]>([])
 const [category,setCategory]=useState('')
 const [results,setResults]=useState<IntakeResult[]>([])
 const [busy,setBusy]=useState(false)
 const [error,setError]=useState('')
 async function load(offset=0){const r=await intakeRequest<IntakePage>(workspaceId,'/items?offset='+offset);setItems(old=>offset?[...old,...r.items]:r.items);setNext(r.next_offset);setSelected([])}
 useEffect(()=>{let live=true;intakeRequest<IntakePage>(workspaceId,'/items').then(r=>{if(live){setItems(r.items);setNext(r.next_offset)}}).catch(()=>{if(live)setError('request_failed')});return()=>{live=false}},[workspaceId])
 async function action(fn:()=>Promise<void>){if(busy)return;setBusy(true);setError('');try{await fn()}catch(e){setError(e instanceof Error&&e.message==='original_unavailable'?'original_unavailable':'request_failed')}finally{setBusy(false)}}
 async function upload(){
  const body=new FormData();files.forEach(f=>body.append('files',f));body.append('consent',String(consent));body.append('data_class',dataClass);if(target)body.append('source_id',target.source_id)
  const r=await intakeRequest<{results:IntakeResult[]}>(workspaceId,'/batch',body);setResults(r.results);await load()
 }
 async function collect(){await intakeRequest(workspaceId,'/collect',{items:items.filter(i=>selected.includes(i.id)).map(i=>({id:i.id,revision:i.revision,category}))});await load()}
 return <main className="mx-auto w-full max-w-3xl space-y-5 overflow-y-auto p-5 sm:p-8">
  <Link href={scopedUrl('/learning',workspaceId)} className="text-sm underline">{t('drive.back')}</Link>
  <h1 className="flex gap-2 text-2xl font-semibold"><FolderInput/>{t('unsorted.title')}</h1>
  <p className="text-sm text-muted-foreground">{t('unsorted.boundary')}</p>
  <div className="space-y-3 rounded-xl border p-4">
   <button disabled={busy} onClick={()=>{setFiles([new File(['Synthetic sample A. No real coursework.'],'sample-a.txt'),new File(['Synthetic sample B. No inferred course.'],'sample-b.txt')]);setDataClass('synthetic');setTarget(null);setConsent(false)}} className="underline">{t('unsorted.demo')}</button>
   {target&&<p>{t('unsorted.newVersion')}: {target.filename}<button onClick={()=>{setTarget(null);setFiles([]);setConsent(false)}} disabled={busy} className="ml-3 underline">{t('Cancel')}</button></p>}
   <label className="block">{t('unsorted.files')}<input key={target?.id||'batch'} aria-label={t('unsorted.files')} type="file" multiple={!target} disabled={busy} onChange={e=>{setFiles(Array.from(e.target.files||[]));setConsent(false)}} className="block max-w-full text-sm"/></label>
   <p className="break-all text-xs">{files.map(f=>f.name).join(', ')}</p>
   <label>{t('unsorted.dataClass')}<select aria-label={t('unsorted.dataClass')} disabled={busy} value={dataClass} onChange={e=>{setDataClass(e.target.value);setConsent(false)}} className="ml-2 rounded border bg-background p-2"><option value="synthetic">{t('unsorted.synthetic')}</option><option value="approved_non_sensitive">{t('unsorted.approved')}</option></select></label>
   <label className="flex gap-2 text-sm"><input type="checkbox" checked={consent} disabled={busy} onChange={e=>setConsent(e.target.checked)}/>{t('unsorted.consent')}</label>
   <button disabled={busy||!consent||!files.length||files.length>10||!!target&&files.length!==1} onClick={()=>void action(upload)} className="rounded border px-3 py-2 disabled:opacity-40">{t('unsorted.upload')}</button>
  </div>
  {error&&<p role="alert">{t(error==='original_unavailable'?'unsorted.originalUnavailable':'unsorted.error')}</p>}{busy&&<p role="status">{t('Loading...')}</p>}
  {results.map((r,i)=><p key={i} className="break-words text-sm" role={r.ok?'status':'alert'}>{r.filename}: {t(r.ok?r.duplicate?'unsorted.duplicate':'unsorted.registered':'unsorted.failed')}{!r.ok&&<span> ({r.code})</span>}</p>)}
  <div className="flex flex-wrap items-end gap-3"><button disabled={busy} onClick={()=>void action(()=>load())} className="underline">{t('inbox.refresh')}</button><label>{t('unsorted.category')}<input value={category} maxLength={100} disabled={busy} onChange={e=>setCategory(e.target.value)} className="block rounded border bg-background p-2"/></label><button disabled={busy||!selected.length||!category.trim()} onClick={()=>void action(collect)} className="rounded border px-3 py-2 disabled:opacity-40">{t('unsorted.collect')}</button></div>
  {!items.length&&!busy&&!error&&<p>{t('unsorted.empty')}</p>}
  {items.map(item=><article key={item.id} data-testid="intake-item" className="space-y-2 rounded-xl border p-4">
   <label className="flex gap-2 break-all font-medium"><input type="checkbox" disabled={busy} checked={selected.includes(item.id)} onChange={e=>setSelected(old=>e.target.checked?[...old,item.id]:old.filter(id=>id!==item.id))}/>{item.filename}</label>
   <p>{t('unsorted.'+item.status)} · {t(item.data_class==='synthetic'?'unsorted.synthetic':'unsorted.approved')} · {item.category||t('Unknown')}</p>
   <details className="break-all text-xs text-muted-foreground"><summary>{t('unsorted.trace')}</summary><p>{t('unsorted.source')}: {item.source_id}</p><p>{t('unsorted.version')}: {item.sha256}</p><p>{item.size_bytes} {t('unsorted.bytes')} · {new Date(item.created_at*1000).toLocaleString()}</p></details>
   <div className="flex flex-wrap gap-3 text-sm underline"><button disabled={busy} onClick={()=>void action(()=>downloadOriginal(workspaceId,item))}>{t('unsorted.download')}</button><button disabled={busy} onClick={()=>{setTarget(item);setFiles([]);setConsent(false)}}>{t('unsorted.newVersion')}</button></div>
  </article>)}
  {next!==null&&<button disabled={busy} onClick={()=>void action(()=>load(next))}>{t('inbox.more')}</button>}
 </main>
}
