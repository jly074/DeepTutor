import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import TaskDetailPanel from '@/components/tasks/TaskDetailPanel'
import {TaskDetailError} from '@/lib/task-detail-api'
const request=vi.hoisted(()=>vi.fn())
vi.mock('@/lib/task-detail-api',async original=>({...await original<typeof import('@/lib/task-detail-api')>(),taskDetailRequest:request}))
vi.mock('react-i18next',()=>({useTranslation:()=>({t:(s:string)=>s})}))
vi.mock('@/lib/workspace-scope',()=>({scopedUrl:(s:string)=>s}))
beforeEach(()=>{request.mockReset()})
const data={task:{id:'task-1',title:'Synthetic coursework',due_date:null,status:'todo',archived:false,updated_at:'old'},announcements:[],links:[],deadline_history:[],next_steps:[{code:'confirm_deadline',evidence_ids:[]}]}
const choices={sources:[{provider:'drive',mode:'demo',source_id:'source-1',label:'Synthetic material',fingerprint:'a'.repeat(64)}],announcements:[{id:'notice-2',revision:1,source_label:'Synthetic source',source_key:'v2',due_date:'2026-12-12',simulated:true}],states:[]}
it('never automatically links or changes dates and requires explicit confirmation',async()=>{
 request.mockImplementation(async(w,id,suffix='detail',body)=>{
  expect(w).toBe('course-a');expect(id).toBe('task-1')
  if(suffix==='evidence-choices')return choices
  if(suffix==='deadline-source'){expect(body).toEqual({confirm:true,announcement_id:'notice-2',announcement_revision:1,expected_updated_at:'old'});return {...data,task:{...data.task,due_date:'2026-12-12'}}}
  return data
 })
 render(<TaskDetailPanel taskId="task-1" workspaceId="course-a"/>)
 await screen.findByText('Synthetic coursework')
 expect(request.mock.calls.every(c=>!c[3])).toBe(true)
 expect(screen.getByTestId('task-current-deadline')).toHaveTextContent('inbox.unknown')
 expect(screen.getByText('detail.next.confirm_deadline')).toBeVisible()
 fireEvent.change(screen.getByLabelText('detail.chooseAnnouncement'),{target:{value:'notice-2'}})
 expect(screen.getByRole('button',{name:'detail.adopt'})).toBeDisabled()
 fireEvent.click(screen.getByRole('checkbox',{name:'detail.dateConsent'}))
 fireEvent.click(screen.getByRole('button',{name:'detail.adopt'}))
 await waitFor(()=>expect(screen.getByTestId('task-current-deadline')).toHaveTextContent('2026-12-12'))
})
it('selects only saved IDs and retains evidence on stale-source failure',async()=>{
 request.mockImplementation(async(_w,_id,suffix='detail',body)=>{
  if(suffix==='evidence-choices')return choices
  if(suffix==='evidence'){expect(body).toEqual({provider:'drive',mode:'demo',source_id:'source-1',fingerprint:'a'.repeat(64)});throw new TaskDetailError('source_changed')}
  return data
 })
 render(<TaskDetailPanel taskId="task-1" workspaceId="course-a"/>)
 await screen.findByText('Synthetic coursework')
 fireEvent.change(screen.getByLabelText('detail.chooseSource'),{target:{value:'0'}})
 fireEvent.click(screen.getByRole('button',{name:'detail.link'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('detail.error.source_changed')
 expect(screen.getByTestId('task-current-deadline')).toHaveTextContent('inbox.unknown')
 expect(screen.getByText('detail.missingAnnouncement')).toBeVisible()
})
