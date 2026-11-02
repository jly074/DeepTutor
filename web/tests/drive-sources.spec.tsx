import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import DriveSourcesPanel from '@/components/learning/DriveSourcesPanel'
import { DriveRequestError } from '@/lib/drive-sources-api'
const request = vi.hoisted(() => vi.fn())
vi.mock('@/lib/drive-sources-api', async importOriginal => ({
  ...await importOriginal<typeof import('@/lib/drive-sources-api')>(), driveRequest: request,
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (s: string) => s }) }))
vi.mock('@/lib/workspace-scope', () => ({ scopedUrl: (s: string) => s }))
beforeEach(() => { request.mockReset() })
it('starts disconnected and only lists after an explicit demo refresh', async () => {
  request.mockImplementation(async (_path, _workspace, mode) => ({
    state: mode === 'demo' ? 'mock' : 'not_connected', simulated: mode === 'demo',
    allowed_folders: mode === 'demo' ? ['demo-course'] : [], sources: [],
  }))
  render(<DriveSourcesPanel workspaceId="course-a" />)
  expect(await screen.findByText('drive.notConnected')).toBeVisible()
  expect(screen.getByRole('button', { name: 'drive.refresh' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'drive.demoMode' }))
  expect(await screen.findByText('drive.simulated')).toBeVisible()
  expect(screen.getByText('drive.demoNotice')).toBeVisible()
  expect(screen.getByRole('button', { name: 'drive.refresh' })).toBeEnabled()
  expect(request.mock.calls.every(call => call[0] === '')).toBe(true)
})
it('saves a reference with explicit workspace and shows no teaching content', async () => {
  let saved = false
  request.mockImplementation(async (path, workspace, mode) => {
    expect(workspace).toBe('course-a')
    if (path.startsWith('/files')) return [{ id: 'one', name: 'Synthetic.pdf', mimeType: 'application/pdf', modifiedTime: '' }]
    if (path === '/sources') { saved = true; return {} }
    return { state: mode === 'demo' ? 'mock' : 'not_connected', allowed_folders: mode === 'demo' ? ['demo-course'] : [], sources: saved ? [{ id: 'source-one', label: 'Synthetic.pdf', available: false, metadata: { simulated: true } }] : [] }
  })
  render(<DriveSourcesPanel workspaceId="course-a" />)
  await screen.findByText('drive.notConnected')
  fireEvent.click(screen.getByRole('button', { name: 'drive.demoMode' }))
  await screen.findByText('drive.simulated')
  fireEvent.click(screen.getByRole('button', { name: 'drive.refresh' }))
  await screen.findByText('Synthetic.pdf')
  fireEvent.click(screen.getByRole('button', { name: 'drive.save' }))
  expect(await screen.findByTestId('saved-drive-source')).toHaveTextContent('drive.notDownloaded')
  expect(request.mock.calls.find(call => call[0] === '/sources')?.[3].body).toBe(JSON.stringify({ folder_id: 'demo-course', file_id: 'one' }))
})
it('shows safe failure while preserving saved references', async () => {
  request.mockImplementation(async path => {
    if (path.startsWith('/files')) throw new DriveRequestError('blocked')
    return { state: 'mock', allowed_folders: ['demo-course'], sources: [{ id: 'saved', label: 'Saved synthetic.pdf', metadata: { simulated: true } }] }
  })
  render(<DriveSourcesPanel workspaceId="course-a" />)
  await screen.findByTestId('saved-drive-source')
  fireEvent.click(screen.getByRole('button', { name: 'drive.refresh' }))
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('drive.blocked'))
  expect(screen.getByTestId('saved-drive-source')).toHaveTextContent('Saved synthetic.pdf')
})
