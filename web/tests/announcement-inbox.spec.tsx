import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import AnnouncementInbox from '@/components/learning/AnnouncementInbox'
import {InboxRequestError} from '@/lib/announcement-inbox-api'
const request=vi.hoisted(()=>vi.fn())
vi.mock('@/lib/announcement-inbox-api',async original=>({...await original<typeof import('@/lib/announcement-inbox-api')>(),inboxRequest:request}))
vi.mock('react-i18next',()=>({useTranslation:()=>({t:(s:string)=>s})}))
vi.mock('@/lib/workspace-scope',()=>({scopedUrl:(s:string)=>s}))
beforeEach(()=>{request.mockReset()})
const row={id:'one',title:'Synthetic announcement',body:'Original synthetic text',source_label:'Course',source_key:'1',source_url:'',due_date:null,simulated:true,reviewed:false,revision:1,task_id:null,task:null}
it('loads saved data only, requires consent, and creates task only on explicit click',async()=>{
 request.mockImplementation(async(workspace,path='',method='GET',body)=>{
  expect(workspace).toBe('course-a')
  if(method==='GET')return{items:[],next_cursor:null,slack_connected:false}
  if(path==='/one/task'){expect(body).toEqual({revision:1});return{...row,task_id:'task-one',task:{id:'task-one',status:'todo',archived:false}}}
  expect(body.simulated).toBe(true);expect(body.consent).toBe(true);return{item:row,duplicate:false}
 })
 render(<AnnouncementInbox workspaceId="course-a"/> )
 await waitFor(()=>expect(request).toHaveBeenCalledTimes(1))
 fireEvent.click(screen.getByRole('button',{name:'inbox.demo'}))
 expect(request).toHaveBeenCalledTimes(1)
 expect(screen.getByRole('button',{name:'inbox.receive'})).toBeDisabled()
 fireEvent.click(screen.getByRole('checkbox',{name:'inbox.consent'}))
 fireEvent.click(screen.getByRole('button',{name:'inbox.receive'}))
 await screen.findByTestId('inbox-item')
 expect(request.mock.calls.filter(c=>c[1]?.endsWith('/task'))).toHaveLength(0)
 fireEvent.click(screen.getByRole('button',{name:'inbox.convert'}))
 expect(await screen.findByText(/task-one/)).toBeVisible()
 expect(screen.queryByRole('button',{name:'inbox.convert'})).not.toBeInTheDocument()
})
it('preserves a typed correction and old item on source conflict',async()=>{
 request.mockImplementation(async(_w,_p,method='GET')=>{if(method==='POST')throw new InboxRequestError('source_conflict');return{items:[row],next_cursor:null}})
 render(<AnnouncementInbox workspaceId="course-a"/> )
 await screen.findByTestId('inbox-item')
 fireEvent.click(screen.getByRole('button',{name:'inbox.demo'}))
 fireEvent.change(screen.getByLabelText('inbox.body'),{target:{value:'Correction'}})
 fireEvent.click(screen.getByRole('checkbox',{name:'inbox.consent'}))
 fireEvent.click(screen.getByRole('button',{name:'inbox.receive'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('inbox.error.source_conflict')
 expect(screen.getByLabelText('inbox.body')).toHaveValue('Correction')
 expect(screen.getByTestId('inbox-item')).toHaveTextContent('Original synthetic text')
})
