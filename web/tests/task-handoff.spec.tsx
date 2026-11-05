import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import TaskHandoffPanel from '@/components/tasks/TaskHandoffPanel'
const request=vi.hoisted(()=>vi.fn())
vi.mock('@/lib/task-detail-api',()=>({taskDetailRequest:request}))
vi.mock('react-i18next',()=>({useTranslation:()=>({t:(x:string)=>x})}))
const summary={id:'receipt',task_id:'task',issuer:'issuer',format:'deeptutor-task-handoff-v1',version:'a'.repeat(64),status:'todo',next_step:'',reference_ids:[],issued_at:'now',expires_at:'later'}
beforeEach(()=>{request.mockReset()})
it('requires consent, exports minimal fields, invalidates draft on editing',async()=>{
 request.mockImplementation(async(w,id,path,body)=>{expect(w).toBe('course');expect(id).toBe('task');if(path==='handoff-export'){expect(body).toEqual({consent:true,next_step:'',reference_ids:[]});return summary}return {items:[]}})
 render(<TaskHandoffPanel taskId="task" workspaceId="course" links={[]}/>);
 expect(screen.getByRole('button',{name:'handoff.prepare'})).toBeDisabled()
 expect(screen.queryByRole('button',{name:'handoff.download'})).toBeNull()
 fireEvent.click(screen.getByLabelText('handoff.consent'));fireEvent.click(screen.getByRole('button',{name:'handoff.prepare'}))
 expect(await screen.findByTestId('handoff-export')).toHaveTextContent('receipt')
 fireEvent.change(screen.getByLabelText('handoff.next'),{target:{value:'Synthetic next step'}})
 expect(screen.queryByTestId('handoff-export')).toBeNull()
 expect(screen.getByRole('button',{name:'handoff.prepare'})).toBeDisabled()
})
it('verifies before explicit acceptance and displays the recorded receipt',async()=>{
 let accepted=false
 request.mockImplementation(async(w,id,path,body)=>{
  if(path==='handoff-import'){expect(body.summary).toEqual(summary);if(body.confirm)accepted=true;return {summary,accepted_at:accepted?'now':null}}
  return {items:accepted?[{summary,accepted_at:'now',current:true}]:[]}
 })
 render(<TaskHandoffPanel taskId="task" workspaceId="course" links={[]}/>);
 fireEvent.change(screen.getByLabelText('handoff.import'),{target:{files:[{size:512,text:async()=>JSON.stringify(summary)}]}})
 await screen.findByText('handoff.verified');expect(accepted).toBe(false)
 fireEvent.click(screen.getByRole('button',{name:'handoff.accept'}))
 expect(await screen.findByTestId('handoff-history')).toHaveTextContent('task')
 expect(screen.getByRole('button',{name:'handoff.accepted'})).toBeDisabled()
})
it('removes stale preview and blocks malformed or oversized files before API',async()=>{
 request.mockImplementation(async(w,id,path,body)=>{if(path==='handoff-import'){if(body.confirm)throw new Error('handoff_stale');return {summary,accepted_at:null}}return {items:[]}})
 render(<TaskHandoffPanel taskId="task" workspaceId="course" links={[]}/>);
 const input=screen.getByLabelText('handoff.import')
 fireEvent.change(input,{target:{files:[{size:512,text:async()=>JSON.stringify(summary)}]}})
 await screen.findByText('handoff.verified');fireEvent.click(screen.getByRole('button',{name:'handoff.accept'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('handoff.error.handoff_stale')
 expect(screen.queryByRole('button',{name:'handoff.accept'})).toBeNull()
 const count=request.mock.calls.length
 for(const file of [{size:20000,text:async()=>''},{size:10,text:async()=>'{'}]){
  fireEvent.change(input,{target:{files:[file]}})
  await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('handoff.error.blocked'))
 }
 expect(request.mock.calls).toHaveLength(count)
})
it('refreshes receipt version labels when parent task detail reloads',async()=>{
 let current=true
 request.mockImplementation(async()=>({items:[{summary,accepted_at:'now',current}]}))
 const {rerender}=render(<TaskHandoffPanel taskId="task" workspaceId="course" links={[]}/>);
 expect(await screen.findByTestId('handoff-history')).toHaveTextContent('handoff.current')
 current=false
 rerender(<TaskHandoffPanel taskId="task" workspaceId="course" links={[]}/>);
 await waitFor(()=>expect(screen.getByTestId('handoff-history')).toHaveTextContent('handoff.historical'))
})
