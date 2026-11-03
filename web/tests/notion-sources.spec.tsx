import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import NotionSourcesPanel from '@/components/learning/NotionSourcesPanel'
import { NotionRequestError } from '@/lib/notion-sources-api'
const request = vi.hoisted(() => vi.fn())
vi.mock('@/lib/notion-sources-api', async importOriginal => ({ ...await importOriginal<typeof import('@/lib/notion-sources-api')>(), notionRequest: request }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (s: string) => s }) }))
vi.mock('@/lib/workspace-scope', () => ({ scopedUrl: (s: string) => s }))
const row = { page_id: '22222222-2222-4222-8222-222222222222', title: 'Synthetic Topic', edited_at: '2026-01-01', fingerprint: 'a'.repeat(64), issues: [], fields: { mastery: { name: 'Mastery', type: 'number', value: 42 } } }
const saved = { id: 'stable-id', label: row.title, metadata: { simulated: true, notion_page_id: row.page_id, last_edited_time: row.edited_at, fields: row.fields } }
beforeEach(() => { request.mockReset() })
it('requires explicit consent, preserves source IDs and raw mastery when saving', async () => {
  let imported = false
  request.mockImplementation(async (path, workspace, mode, body) => {
    expect(workspace).toBe('course-a')
    if(path==='/schema') return { properties: [{id:'title',name:'Topic',type:'title',supported:true},{id:'mastery',name:'Mastery',type:'number',supported:true},{id:'formula',name:'Formula',type:'formula',supported:false}] }
    if(path==='/preview') { expect(body.property_ids).toEqual(['title','mastery']); return {rows:[row],has_more:false} }
    if(path==='/snapshots') { expect(body).toMatchObject({page_id:row.page_id,fingerprint:row.fingerprint,consent:true,cursor:''}); imported=true; return saved }
    return {state:mode==='demo'?'simulated':'not_configured',sources:imported?[saved]:[]}
  })
  render(<NotionSourcesPanel workspaceId="course-a" />)
  await screen.findByText('notion.not_configured')
  fireEvent.click(screen.getByRole('button',{name:'drive.demoMode'}))
  await screen.findByText('notion.simulated')
  expect(request.mock.calls.every(c=>c[0]==='')).toBe(true)
  expect(screen.getByRole('button',{name:'notion.readSchema'})).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox',{name:'notion.consent'}))
  fireEvent.click(screen.getByRole('button',{name:'notion.readSchema'}))
  expect(await screen.findByRole('checkbox',{name:/Formula/})).toBeDisabled()
  expect(screen.getByRole('checkbox',{name:/Topic/})).toBeChecked()
  fireEvent.click(screen.getByRole('checkbox',{name:/Mastery/}))
  fireEvent.click(screen.getByRole('button',{name:'notion.preview'}))
  expect(await screen.findByTestId('notion-preview-row')).toHaveTextContent('42')
  fireEvent.click(screen.getByRole('button',{name:'notion.import'}))
  expect(await screen.findByTestId('notion-snapshot')).toHaveTextContent(row.page_id)
  expect(screen.queryByText('notion.openOriginal')).not.toBeInTheDocument()
})
it('retains saved snapshots on provider failure', async () => {
  request.mockImplementation(async path => { if(path==='/schema') throw new NotionRequestError('access_denied'); return {state:'configured_not_verified',sources:[saved]} })
  render(<NotionSourcesPanel workspaceId="course-a" />)
  await screen.findByTestId('notion-snapshot')
  fireEvent.click(screen.getByRole('checkbox',{name:'notion.consent'}))
  fireEvent.click(screen.getByRole('button',{name:'notion.readSchema'}))
  await waitFor(()=>expect(screen.getByRole('status')).toHaveTextContent('notion.readFailed'))
  expect(screen.getByRole('alert')).toHaveTextContent('notion.error.access_denied')
  expect(screen.getByTestId('notion-snapshot')).toHaveTextContent(row.page_id)
})
