import {fireEvent,render,screen} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import AutomationReadiness from '@/components/learning/AutomationReadiness'
const read=vi.hoisted(()=>vi.fn())
vi.mock('@/lib/automation-readiness-api',()=>({readReadiness:read}))
vi.mock('react-i18next',()=>({useTranslation:()=>({t:(s:string)=>s})}))
vi.mock('@/lib/workspace-scope',()=>({scopedUrl:(path:string,workspace:string)=>path+'?dt_workspace='+workspace}))
const data={observed_at:'synthetic-time',local_tasks:{state:'available',counts:{todo:2,doing:1,done:0,archived:0}},rows:[{id:'morning',route:'/kanban',evidence_doc:'docs/example.md',v2_state:'unverified',v3_state:'partial_code',external_connection:'unverified',sole_writer:'unconfirmed',gaps:['sole_writer','rollback']}]}
beforeEach(()=>{read.mockReset()})
it('shows unknown legacy state and local counts without activation controls',async()=>{
 read.mockResolvedValue(data)
 render(<AutomationReadiness workspaceId="course"/>);
 expect(await screen.findByTestId('readiness-counts')).toHaveTextContent('2')
 expect(read).toHaveBeenCalledWith('course')
 expect(screen.getByTestId('readiness-row')).toHaveTextContent('succession.notReady')
 expect(screen.getByTestId('readiness-row')).toHaveTextContent('succession.synthetic')
 expect(screen.getAllByRole('button')).toHaveLength(1)
 expect(screen.getByRole('link',{name:'succession.open'})).toHaveAttribute('href','/kanban?dt_workspace=course')
})
it('keeps checklist on local store error and does not show false zero counts',async()=>{
 read.mockResolvedValue({...data,local_tasks:{state:'unavailable',counts:null}})
 render(<AutomationReadiness workspaceId="course"/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('succession.localError')
 expect(screen.queryByTestId('readiness-counts')).toBeNull()
 expect(screen.getByTestId('readiness-row')).toBeVisible()
})
it('clears old observations on failed refresh and retries without automatic polling',async()=>{
 read.mockResolvedValueOnce(data).mockRejectedValueOnce(new Error('private diagnostics')).mockResolvedValueOnce(data)
 render(<AutomationReadiness workspaceId="course"/>);
 await screen.findByTestId('readiness-counts')
 fireEvent.click(screen.getByRole('button',{name:'succession.refresh'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('succession.error')
 expect(screen.queryByTestId('readiness-counts')).toBeNull()
 expect(screen.queryByText('private diagnostics')).toBeNull()
 fireEvent.click(screen.getByRole('button',{name:'succession.refresh'}))
 await screen.findByTestId('readiness-counts')
 expect(read).toHaveBeenCalledTimes(3)
})
