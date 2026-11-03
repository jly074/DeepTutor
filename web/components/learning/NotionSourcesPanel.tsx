'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useTranslation } from 'react-i18next'
import { Database, FileText } from 'lucide-react'
import { subPanelClass } from '@/components/settings/shared'
import { scopedUrl } from '@/lib/workspace-scope'
import { notionRequest, NotionRequestError, type NotionMode, type NotionOverview, type NotionPreview, type NotionProperty, type NotionRow } from '@/lib/notion-sources-api'

const errors = new Set(['needs_authorization','access_denied','missing_or_unshared','rate_limited','timeout','source_changed','row_moved_or_missing','incomplete_properties','incomplete_query','invalid_properties','unsupported_property','storage_unavailable','invalid_response'])
function Fields({ fields }: { fields: NotionRow['fields'] }) {
  return <dl className="grid gap-2 text-sm">{Object.entries(fields).map(([id,field]) => <div key={id} className="min-w-0"><dt className="font-medium">{field.name} <span className="font-normal text-muted-foreground">({field.type})</span></dt><dd className="whitespace-pre-wrap break-words">{field.value === null ? '—' : typeof field.value === 'string' ? field.value : JSON.stringify(field.value)}</dd></div>)}</dl>
}
function ModeView({ workspaceId, mode }: { workspaceId: string; mode: NotionMode }) {
  const { t } = useTranslation()
  const [overview,setOverview] = useState<NotionOverview | null>(null)
  const [schema,setSchema] = useState<NotionProperty[]>([])
  const [selected,setSelected] = useState<string[]>([])
  const [preview,setPreview] = useState<NotionPreview | null>(null)
  const [cursor,setCursor] = useState('')
  const [consent,setConsent] = useState(false)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const [readable,setReadable] = useState(false)
  const report = (e: unknown) => setError(e instanceof NotionRequestError && errors.has(e.code) ? e.code : 'blocked')
  useEffect(() => {
    let active=true
    notionRequest<NotionOverview>('',workspaceId,mode).then(value=>{if(active)setOverview(value)}).catch(e=>{if(active)report(e)})
    return ()=>{active=false}
  },[workspaceId,mode])
  async function readSchema() {
    if(!consent)return
    setBusy(true);setError('')
    try {
      const result=await notionRequest<{properties:NotionProperty[]}>('/schema',workspaceId,mode,{consent:true})
      setSchema(result.properties);setSelected(result.properties.filter(p=>p.type==='title').map(p=>p.id));setPreview(null);setCursor('');setReadable(true)
    } catch(e){report(e)} finally{setBusy(false)}
  }
  async function load(next='') {
    if(!consent)return
    setBusy(true);setError('')
    try {
      const result=await notionRequest<NotionPreview>('/preview',workspaceId,mode,{consent:true,property_ids:selected,cursor:next})
      setPreview(result);setCursor(next);setReadable(true)
    } catch(e){report(e)} finally{setBusy(false)}
  }
  async function save(row:NotionRow) {
    if(!consent)return
    setBusy(true);setError('')
    try {
      await notionRequest('/snapshots',workspaceId,mode,{consent:true,property_ids:selected,cursor,page_id:row.page_id,fingerprint:row.fingerprint})
      setOverview(await notionRequest<NotionOverview>('',workspaceId,mode))
    } catch(e){report(e)} finally{setBusy(false)}
  }
  const canRead=overview && ['simulated','configured_not_verified'].includes(overview.state)
  return <div className="space-y-5">
    <p role="status" className={`${subPanelClass} p-3`}>{t(error ? 'notion.readFailed' : mode==='demo' ? 'notion.simulated' : readable ? 'notion.readable' : overview ? `notion.${overview.state}` : 'Loading...')}</p>
    {overview?.data_source_id && <p className="break-all text-xs text-muted-foreground">{t('notion.sourceId')}: {overview.data_source_id}</p>}
    <p className="text-sm text-muted-foreground">{t('notion.boundary')}</p>
    {canRead && <section className={`${subPanelClass} space-y-3 p-4`}>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={consent} disabled={busy} onChange={e=>setConsent(e.target.checked)} />{t('notion.consent')}</label>
      <button type="button" disabled={!consent||busy} onClick={()=>void readSchema()} className="rounded-lg border border-border px-4 py-2 disabled:opacity-40">{t('notion.readSchema')}</button>
      {schema.length>0 && <>
        <h2 className="font-semibold">{t('notion.selectFields')}</h2>
        <p className="text-sm text-muted-foreground">{t('notion.fieldsNotice')}</p>
        <div className="grid gap-2 sm:grid-cols-2">{schema.map(p=><label key={p.id} className="flex items-start gap-2 text-sm"><input type="checkbox" checked={selected.includes(p.id)} disabled={busy||!p.supported||p.type==='title'} onChange={e=>{setSelected(e.target.checked?[...selected,p.id]:selected.filter(id=>id!==p.id));setPreview(null);setCursor('')}} />{p.name} ({p.type}){!p.supported && ` · ${t('notion.unsupported')}`}</label>)}</div>
        <button type="button" disabled={!consent||busy||selected.length>10} onClick={()=>void load()} className="rounded-lg border border-border px-4 py-2 disabled:opacity-40">{busy?t('Loading...'):t('notion.preview')}</button>
      </>}
    </section>}
    {error && <p role="alert" className="rounded-lg border border-red-300 p-3 text-sm">{t(`notion.error.${error}`)}</p>}
    {preview && <section className="space-y-3" aria-label={t('notion.preview')}>
      <p className="text-sm text-muted-foreground">{t('notion.pageNotice')}</p>
      {preview.rows.length===0 && <p>{t('notion.empty')}</p>}
      {preview.rows.map(row=><article key={row.page_id} className={`${subPanelClass} space-y-3 p-4`} data-testid="notion-preview-row">
        <h3 className="flex items-center gap-2 font-semibold"><FileText size={18}/>{row.title||t('notion.untitled')}</h3>
        <p className="break-all text-xs text-muted-foreground">{t('notion.topicId')}: {row.page_id} · {row.edited_at}</p>
        <Fields fields={row.fields}/>
        {row.issues.length>0 && <p className="text-sm">{t('notion.incomplete')}: {row.issues.join(', ')}</p>}
        <button type="button" disabled={!consent||busy||row.issues.length>0} onClick={()=>void save(row)} className="rounded-lg border border-border px-3 py-2 disabled:opacity-40">{t('notion.import')}</button>
      </article>)}
      {preview.has_more && <button type="button" disabled={busy||!consent} onClick={()=>void load(preview.next_cursor||'')} className="rounded-lg border border-border px-4 py-2 disabled:opacity-40">{t('notion.nextPage')}</button>}
    </section>}
    <section className="space-y-3" aria-label={t('notion.saved')}><h2 className="font-semibold">{t('notion.saved')}</h2>
      <p className="text-sm text-muted-foreground">{t('notion.snapshotNotice')}</p>
      {overview?.sources.length===0 && <p>{t('notion.none')}</p>}
      {overview?.sources.map(source=><article key={source.id} className={`${subPanelClass} space-y-3 p-4`} data-testid="notion-snapshot">
        <h3 className="font-semibold">{source.label||t('notion.untitled')}</h3>
        <p className="break-all text-xs text-muted-foreground">{t('notion.topicId')}: {source.metadata.notion_page_id} · {source.metadata.last_edited_time}</p>
        <Fields fields={source.metadata.fields}/>
        {source.metadata.simulated ? <p className="text-sm">{t('notion.simulated')}</p> : <a href={`https://www.notion.so/${source.metadata.notion_page_id.replaceAll('-','')}`} target="_blank" rel="noopener noreferrer" className="text-sm underline">{t('notion.openOriginal')}</a>}
      </article>)}
    </section>
  </div>
}
export default function NotionSourcesPanel({workspaceId}:{workspaceId:string}) {
  const {t}=useTranslation();const [mode,setMode]=useState<NotionMode>('live')
  return <main className="mx-auto w-full max-w-3xl space-y-5 overflow-y-auto p-5 sm:p-8">
    <Link href={scopedUrl('/learning',workspaceId)} className="text-sm text-muted-foreground">{t('drive.back')}</Link>
    <h1 className="flex items-center gap-2 text-2xl font-semibold"><Database size={24}/>{t('notion.title')}</h1>
    <p className="text-sm text-muted-foreground">{t('notion.intro')}</p>
    <div className="flex flex-wrap gap-2"><button type="button" aria-pressed={mode==='live'} onClick={()=>setMode('live')} className="rounded-lg border border-border px-3 py-2">{t('drive.realMode')}</button><button type="button" aria-pressed={mode==='demo'} onClick={()=>setMode('demo')} className="rounded-lg border border-border px-3 py-2">{t('drive.demoMode')}</button></div>
    <ModeView key={`${workspaceId}:${mode}`} workspaceId={workspaceId} mode={mode}/>
  </main>
}
