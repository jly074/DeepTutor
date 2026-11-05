'use client'
import {useEffect,useState} from 'react'
import Link from 'next/link'
import {ClipboardCheck} from 'lucide-react'
import {useTranslation} from 'react-i18next'
import {subPanelClass} from '@/components/settings/shared'
import {scopedUrl} from '@/lib/workspace-scope'
import {readReadiness,type Readiness} from '@/lib/automation-readiness-api'
export default function AutomationReadiness({workspaceId}:{workspaceId:string}){
 const {t}=useTranslation()
 const [data,setData]=useState<Readiness|null>(null),[busy,setBusy]=useState(true),[failed,setFailed]=useState(false)
 useEffect(()=>{let active=true;readReadiness(workspaceId).then(r=>{if(active)setData(r)}).catch(()=>{if(active)setFailed(true)}).finally(()=>{if(active)setBusy(false)});return()=>{active=false}},[workspaceId])
 async function refresh(){setBusy(true);setFailed(false);setData(null);try{setData(await readReadiness(workspaceId))}catch{setFailed(true)}finally{setBusy(false)}}
 return <main className="mx-auto w-full max-w-3xl space-y-5 overflow-y-auto p-5 sm:p-8">
  <Link href={scopedUrl('/learning',workspaceId)} className="text-sm underline">{t('navigation.learning')}</Link>
  <h1 className="flex gap-2 text-2xl font-semibold"><ClipboardCheck/>{t('succession.title')}</h1>
  <p className="text-sm text-muted-foreground">{t('succession.boundary')}</p>
  <p className="rounded-lg border border-border p-3 text-sm">{t('succession.notifications')}</p>
  <button disabled={busy} onClick={()=>void refresh()} className="rounded-lg border border-border px-3 py-2 disabled:opacity-40">{t('succession.refresh')}</button>
  {busy&&<p role="status">{t('Loading...')}</p>}{failed&&<p role="alert">{t('succession.error')}</p>}
  {data&&<>
   <p className="break-all text-xs text-muted-foreground">{t('succession.observed')}: {data.observed_at}</p>
   <section className={`${subPanelClass} space-y-2 p-4`}><h2 className="font-semibold">{t('succession.local')}</h2><p className="text-sm">{t('succession.localNotice')}</p>
    {data.local_tasks.state==='available'&&data.local_tasks.counts?<dl data-testid="readiness-counts" className="flex flex-wrap gap-4 text-sm">{Object.entries(data.local_tasks.counts).map(([key,count])=><div key={key}><dt>{t(`succession.count.${key}`)}</dt><dd>{count}</dd></div>)}</dl>:<p role="alert">{t('succession.localError')}</p>}
   </section>
   {data.rows.map(row=><section key={row.id} data-testid="readiness-row" className={`${subPanelClass} space-y-3 p-4`}>
    <h2 className="font-semibold">{t(`succession.role.${row.id}`)}</h2><p className="text-sm">{t(`succession.capability.${row.id}`)}</p>
    <dl className="space-y-1 text-sm"><div><dt className="inline font-medium">{t('succession.v2')}: </dt><dd className="inline">{t(`succession.state.${row.v2_state}`)}</dd></div><div><dt className="inline font-medium">{t('succession.v3')}: </dt><dd className="inline">{t(`succession.state.${row.v3_state}`)}</dd></div><div><dt className="inline font-medium">{t('succession.external')}: </dt><dd className="inline">{t(`succession.state.${row.external_connection}`)}</dd></div><div><dt className="inline font-medium">{t('succession.writer')}: </dt><dd className="inline">{t(`succession.state.${row.sole_writer}`)}</dd></div></dl>
    <p className="text-sm">{t('succession.synthetic')}</p><p className="text-sm font-medium">{t('succession.notReady')}</p>
    <h3 className="text-sm font-medium">{t('succession.gaps')}</h3><ul className="list-disc space-y-1 pl-5 text-sm">{row.gaps.map(g=><li key={g}>{t(`succession.gap.${g}`)}</li>)}</ul>
    <Link href={scopedUrl(row.route,workspaceId)} className="inline-block text-sm underline">{t('succession.open')}</Link>
    <details className="text-xs"><summary>{t('succession.evidence')}</summary><p className="break-all">{row.evidence_doc}</p><p>{t('succession.inventoryNotice')}</p></details>
   </section>)}
  </>}
 </main>
}
