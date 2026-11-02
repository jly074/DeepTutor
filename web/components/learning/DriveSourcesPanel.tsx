'use client'

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Link from 'next/link'
import { scopedUrl } from '@/lib/workspace-scope'
import { driveRequest, DriveRequestError, type DriveMode, type DriveState, type DriveFile, type DriveOverview } from '@/lib/drive-sources-api'

const stateLabels: Record<DriveState, string> = {
  not_connected: 'drive.notConnected', needs_authorization: 'drive.needsAuthorization',
  mock: 'drive.simulated', queryable: 'drive.queryable', blocked: 'drive.blocked',
}

function DriveModeView({ workspaceId, mode }: { workspaceId: string; mode: DriveMode }) {
  const { t } = useTranslation()
  const [overview, setOverview] = useState<DriveOverview | null>(null)
  const [state, setState] = useState<DriveState | null>(null)
  const [folder, setFolder] = useState('')
  const [files, setFiles] = useState<DriveFile[]>([])
  const [busy, setBusy] = useState(false)
  const [listed, setListed] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    driveRequest<DriveOverview>('', workspaceId, mode, { signal: controller.signal }).then(result => {
      setOverview(result); setState(result.state); setFolder(result.allowed_folders[0] || '')
    }).catch(error => { if (!controller.signal.aborted) setState(error instanceof DriveRequestError ? error.state : 'blocked') })
    return () => controller.abort()
  }, [workspaceId, mode])
  async function refresh() {
    setBusy(true); setFiles([]); setListed(false)
    try {
      const result = await driveRequest<DriveFile[]>(`/files?folder_id=${encodeURIComponent(folder)}`, workspaceId, mode)
      setFiles(result); setListed(true); setState(mode === 'demo' ? 'mock' : 'queryable')
    } catch (error) { setState(error instanceof DriveRequestError ? error.state : 'blocked') }
    finally { setBusy(false) }
  }
  async function save(fileId: string) {
    setBusy(true)
    try {
      await driveRequest('/sources', workspaceId, mode, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_id: folder, file_id: fileId }),
      })
      setOverview(await driveRequest<DriveOverview>('', workspaceId, mode))
    } catch (error) { setState(error instanceof DriveRequestError ? error.state : 'blocked') }
    finally { setBusy(false) }
  }
  return <div className="space-y-5">
    <p role="status" className="rounded-lg border border-border p-3 font-medium">{state ? t(stateLabels[state]) : t('Loading...')}</p>
    <p className="text-sm text-muted-foreground">{mode === 'demo' ? t('drive.demoNotice') : t('drive.liveNotice')}</p>
    <p className="text-sm text-muted-foreground">{t('drive.metadataOnly')}</p>
    {overview && <>
      <label className="block text-sm">{t('drive.allowedFolder')}
        <select aria-label={t('drive.allowedFolder')} value={folder} disabled={busy || !overview.allowed_folders.length}
          onChange={event => { setFolder(event.target.value); setFiles([]); setListed(false) }} className="mt-2 block w-full rounded-lg border border-border bg-background p-2">
          {!overview.allowed_folders.length && <option value="">{t('drive.noFolder')}</option>}
          {overview.allowed_folders.map(id => <option key={id} value={id}>{id}</option>)}
        </select>
      </label>
      <button type="button" disabled={busy || !folder} onClick={() => void refresh()} className="rounded-lg border border-border px-4 py-2 disabled:opacity-40">{busy ? t('Loading...') : t('drive.refresh')}</button>
      {listed && files.length === 0 && <p>{t('drive.empty')}</p>}
      <ul className="space-y-3">{files.map(file => <li key={file.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-3">
        <div className="min-w-0 break-words"><p>{file.name}</p><p className="text-xs text-muted-foreground">{file.mimeType} · {file.modifiedTime || t('Unknown')}</p></div>
        <button type="button" disabled={busy} onClick={() => void save(file.id)} className="rounded-lg bg-primary px-3 py-2 text-primary-foreground disabled:opacity-40">{t('drive.save')}</button>
      </li>)}</ul>
      <section aria-label={t('drive.saved')} className="space-y-3">
        <h2 className="font-semibold">{t('drive.saved')}</h2>
        {!overview.sources.length && <p className="text-sm text-muted-foreground">{t('drive.noneSaved')}</p>}
        {overview.sources.map(source => <article key={source.id} className="rounded-lg border border-border p-3" data-testid="saved-drive-source">
          <p className="break-words font-medium">{source.label}</p>
          <p className="text-sm text-muted-foreground">{source.metadata.simulated ? t('drive.simulated') : t('drive.remoteReference')} · {t('drive.notDownloaded')}</p>
        </article>)}
      </section>
    </>}
  </div>
}

export default function DriveSourcesPanel({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<DriveMode>('live')
  return <main className="mx-auto w-full max-w-3xl space-y-5 overflow-y-auto p-5 sm:p-8">
    <Link href={scopedUrl('/learning', workspaceId)} className="text-sm text-muted-foreground">{t('drive.back')}</Link>
    <h1 className="text-2xl font-semibold">{t('drive.title')}</h1>
    <p className="text-sm text-muted-foreground">{t('drive.workspaceNotice')}</p>
    <div className="flex flex-wrap gap-2">
      <button type="button" aria-pressed={mode === 'live'} onClick={() => setMode('live')} className="rounded-lg border border-border px-3 py-2">{t('drive.realMode')}</button>
      <button type="button" aria-pressed={mode === 'demo'} onClick={() => setMode('demo')} className="rounded-lg border border-border px-3 py-2">{t('drive.demoMode')}</button>
    </div>
    <DriveModeView key={`${workspaceId}:${mode}`} workspaceId={workspaceId} mode={mode} />
  </main>
}
