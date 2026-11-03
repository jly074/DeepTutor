'use client'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { browserStorage } from '@/shared/storage'
import { driveRequest } from '@/lib/drive-sources-api'
import { scopedUrl } from '@/lib/workspace-scope'
import { subPanelClass, inputClass } from '@/components/settings/shared'

type Status = { state: 'not_configured' | 'authentication_required' | 'storage_unavailable' | 'needs_authorization' | 'connected'; expires_at?: number }
export default function DriveAuthorization({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<Status | null>(null)
  const [folder, setFolder] = useState('')
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  useEffect(() => {
    let active = true
    async function load() {
      try {
        if (browserStorage.readRaw('session', 'drive.oauth.failure')) {
          browserStorage.removeRaw('session', 'drive.oauth.failure'); if (active) setError(true)
        }
        const raw = browserStorage.readRaw('session', 'drive.oauth.callback')
        if (raw) {
          const pendingRaw = browserStorage.readRaw('session', 'drive.oauth.pending') || 'null'
          // Consume before parsing/yielding: corrupt data and strict effects cannot replay.
          browserStorage.removeRaw('session', 'drive.oauth.callback'); browserStorage.removeRaw('session', 'drive.oauth.pending')
          const pending = JSON.parse(pendingRaw)
          const callback = JSON.parse(raw)
          if (!pending || pending.workspace !== workspaceId || pending.state !== callback.state || pending.expires <= Date.now()) throw new Error()
          await driveRequest('/oauth/complete', workspaceId, 'live', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...callback, browser_nonce: pending.nonce }) })
          window.location.replace(scopedUrl('/learning/drive', workspaceId)); return
        }
        const result = await driveRequest<Status>('/oauth/status', workspaceId, 'live')
        if (active) setStatus(result)
      } catch {
        if (active) setError(true)
        try {
          const result = await driveRequest<Status>('/oauth/status', workspaceId, 'live')
          if (active) setStatus(result)
        } catch { /* Keep the safe error when even status is unavailable. */ }
      }
    }
    void load()
    return () => { active = false }
  }, [workspaceId])
  async function start() {
    if (!consent || !/^[A-Za-z0-9_-]{1,200}$/.test(folder)) return
    setBusy(true); setError(false)
    try {
      const nonce = crypto.randomUUID().replaceAll('-', '') + crypto.randomUUID().replaceAll('-', '')
      const result = await driveRequest<{ state: string; authorization_url: string }>('/oauth/start', workspaceId, 'live', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ folder_id: folder, browser_nonce: nonce, consent: true }) })
      const url = new URL(result.authorization_url)
      if (url.origin !== 'https://accounts.google.com' || url.pathname !== '/o/oauth2/v2/auth') throw new Error()
      if (!browserStorage.writeRaw('session', 'drive.oauth.pending', JSON.stringify({ state: result.state, nonce, workspace: workspaceId, expires: Date.now() + 600000 }))) throw new Error()
      window.location.assign(url.href)
    } catch { setError(true); setBusy(false) }
  }
  async function disconnect() {
    setBusy(true); setError(false)
    try {
      await driveRequest('/oauth/disconnect', workspaceId, 'live', { method: 'POST' })
      browserStorage.removeRaw('session', 'drive.oauth.pending'); browserStorage.removeRaw('session', 'drive.oauth.callback')
      window.location.replace(scopedUrl('/learning/drive', workspaceId))
    } catch { setError(true); setBusy(false) }
  }
  return <section className={`${subPanelClass} space-y-3 p-4`} aria-label={t('driveAuth.title')}>
    <h2 className="font-semibold">{t('driveAuth.title')}</h2>
    <p>{t(status ? `driveAuth.${status.state}` : 'Loading...')}</p>
    <p className="text-sm text-muted-foreground">{t('driveAuth.scope')}</p>
    {status?.state === 'needs_authorization' && <>
      <label className="block text-sm">{t('driveAuth.folder')}<input value={folder} onChange={e => setFolder(e.target.value)} maxLength={200} disabled={busy} className={`${inputClass} mt-2`} /></label>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} disabled={busy} />{t('driveAuth.consent')}</label>
      <button type="button" disabled={busy || !consent || !/^[A-Za-z0-9_-]{1,200}$/.test(folder)} onClick={() => void start()} className="rounded-lg border border-border px-4 py-2 disabled:opacity-40">{t('driveAuth.connect')}</button>
    </>}
    {status?.state === 'connected' && <>
      <p className="text-sm">{t('driveAuth.expiry')} {status.expires_at ? new Date(status.expires_at * 1000).toLocaleString() : ''}</p>
      <p className="text-sm text-muted-foreground">{t('driveAuth.disconnectNotice')}</p>
      <button type="button" disabled={busy} onClick={() => void disconnect()} className="rounded-lg border border-border px-4 py-2">{t('driveAuth.disconnect')}</button>
    </>}
    {error && <p role="alert">{t('driveAuth.error')}</p>}
  </section>
}
