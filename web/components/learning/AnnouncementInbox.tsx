'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Inbox } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { scopedUrl } from '@/lib/workspace-scope'
import { subPanelClass } from '@/components/settings/shared'
import { inboxRequest, InboxRequestError, type Announcement, type InboxPage } from '@/lib/announcement-inbox-api'

const empty={title:'',body:'',source_label:'',source_key:'',source_url:'',due_date:'',simulated:false}
export default function AnnouncementInbox({workspaceId}:{workspaceId:string}) {
  const {t}=useTranslation()
  const [form,setForm]=useState(empty)
  const [consent,setConsent]=useState(false)
  const [items,setItems]=useState<Announcement[]>([])
  const [cursor,setCursor]=useState<number|null>(null)
  const [busy,setBusy]=useState(true)
  const [error,setError]=useState('')
  const [message,setMessage]=useState('')
  const report=(e:unknown)=>setError(e instanceof InboxRequestError&&['source_conflict','stale_revision','not_found','storage_unavailable'].includes(e.code)?e.code:'blocked')
  useEffect(()=>{
    let active=true
    inboxRequest<InboxPage>(workspaceId).then(p=>{if(active){setItems(p.items);setCursor(p.next_cursor)}}).catch(e=>{if(active)report(e)}).finally(()=>{if(active)setBusy(false)})
    return()=>{active=false}
  },[workspaceId])
  async function load(more=false){
    setBusy(true);setError('')
    try{const p=await inboxRequest<InboxPage>(workspaceId,more?`?before=${cursor}`:'');setItems(prev=>more?[...prev,...p.items.filter(r=>!prev.some(x=>x.id===r.id))]:p.items);setCursor(p.next_cursor)}catch(e){report(e)}finally{setBusy(false)}
  }
  async function receive(){
    if(!consent)return
    setBusy(true);setError('');setMessage('')
    try{
      const result=await inboxRequest<{item:Announcement;duplicate:boolean}>(workspaceId,'','POST',{...form,due_date:form.due_date||null,consent:true})
      setItems(prev=>[result.item,...prev.filter(r=>r.id!==result.item.id)])
      setMessage(result.duplicate?'inbox.duplicate':'inbox.received')
    }catch(e){report(e)}finally{setBusy(false)}
  }
  async function change(item:Announcement,task=false){
    setBusy(true);setError('');setMessage('')
    try{
      const row=await inboxRequest<Announcement>(workspaceId,`/${item.id}${task?'/task':''}`,task?'POST':'PATCH',task?{revision:item.revision}:{revision:item.revision,reviewed:!item.reviewed})
      setItems(prev=>prev.map(r=>r.id===row.id?row:r));setMessage(task?'inbox.taskCreated':'inbox.reviewSaved')
    }catch(e){report(e)}finally{setBusy(false)}
  }
  return <main className="mx-auto w-full max-w-3xl space-y-5 overflow-y-auto p-5 sm:p-8">
    <Link href={scopedUrl('/learning',workspaceId)} className="text-sm text-muted-foreground">{t('drive.back')}</Link>
    <h1 className="flex items-center gap-2 text-2xl font-semibold"><Inbox size={24}/>{t('inbox.title')}</h1>
    <p className="text-sm text-muted-foreground">{t('inbox.boundary')}</p>
    <div className="flex flex-wrap gap-3"><button disabled={busy} onClick={()=>void load()} className="rounded-lg border border-border px-3 py-2">{t('inbox.refresh')}</button><Link className="rounded-lg border border-border px-3 py-2" href={scopedUrl('/kanban',workspaceId)}>{t('inbox.tasks')}</Link></div>
    <form className={`${subPanelClass} space-y-3 p-4`} onSubmit={e=>{e.preventDefault();void receive()}}>
      <button type="button" disabled={busy} className="text-sm underline" onClick={()=>{setForm({title:'Synthetic announcement',body:'Synthetic exercise: review chapter A. No actual deadline.',source_label:'Synthetic course',source_key:'synthetic-announcement-1',source_url:'',due_date:'',simulated:true});setConsent(false)}}>{t('inbox.demo')}</button>
      <p className="text-sm font-medium">{t(form.simulated?'inbox.synthetic':'inbox.manual')}</p>
      {(['title','source_label','source_key','source_url','due_date'] as const).map(key=><label key={key} className="block text-sm">{t(key==='title'?'inbox.titleField':`inbox.${key}`)}<input required={!['source_url','due_date'].includes(key)} type={key==='due_date'?'date':key==='source_url'?'url':'text'} maxLength={key==='title'?148:key==='source_url'?2048:200} value={form[key]} disabled={busy} onChange={e=>setForm({...form,[key]:e.target.value})} className="mt-1 block w-full rounded-lg border border-border bg-transparent p-2"/></label>)}
      <p className="text-xs text-muted-foreground">{t('inbox.keyNotice')}</p>
      <label className="block text-sm">{t('inbox.body')}<textarea required maxLength={8000} rows={4} value={form.body} disabled={busy} onChange={e=>setForm({...form,body:e.target.value})} className="mt-1 block w-full rounded-lg border border-border bg-transparent p-2"/></label>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={consent} disabled={busy} onChange={e=>setConsent(e.target.checked)}/>{t('inbox.consent')}</label>
      <div className="flex gap-3"><button disabled={busy||!consent} className="rounded-lg border border-border px-3 py-2 disabled:opacity-40">{t('inbox.receive')}</button><button type="button" disabled={busy} onClick={()=>{setForm(empty);setConsent(false)}} className="text-sm underline">{t('inbox.clear')}</button></div>
    </form>
    {busy&&<p role="status">{t('Loading...')}</p>}
    {error&&<p role="alert">{t(`inbox.error.${error}`)}</p>}
    {message&&<p role="status">{t(message)}</p>}
    <p className="text-sm text-muted-foreground">{t('inbox.convertNotice')}</p>
    {!busy&&!items.length&&!error&&<p>{t('inbox.empty')}</p>}
    {items.map(item=><article key={item.id} data-testid="inbox-item" className={`${subPanelClass} space-y-3 p-4`}>
      <h2 className="break-words font-semibold">{item.title}</h2>
      <p className="text-sm">{t(item.simulated?'inbox.synthetic':'inbox.manual')} · {t(item.reviewed?'inbox.reviewed':'inbox.unread')}</p>
      <p className="break-all text-xs text-muted-foreground">{item.source_label} · {item.source_key} · {item.created_at}</p>
      <p className="whitespace-pre-wrap break-words text-sm">{item.body}</p>
      <p className="text-sm">{t('inbox.due_date')}: {item.due_date||t('inbox.unknown')}</p>
      {item.source_url&&<a href={item.source_url} target="_blank" rel="noopener noreferrer" className="text-sm underline">{t('inbox.source')}</a>}
      <div className="flex flex-wrap gap-3"><button disabled={busy} onClick={()=>void change(item)} className="rounded-lg border border-border px-3 py-2">{t(item.reviewed?'inbox.markUnread':'inbox.markReviewed')}</button>
      {!item.task_id?<button disabled={busy} onClick={()=>void change(item,true)} className="rounded-lg border border-border px-3 py-2">{t('inbox.convert')}</button>:<p className="break-all text-sm">{t('inbox.taskId')}: {item.task_id} · {item.task?t(item.task.archived?'inbox.archived':`inbox.task.${item.task.status}`):t('inbox.taskUnavailable')}</p>}</div>
    </article>)}
    {cursor!==null&&<button disabled={busy} onClick={()=>void load(true)} className="rounded-lg border border-border px-3 py-2">{t('inbox.more')}</button>}
  </main>
}
