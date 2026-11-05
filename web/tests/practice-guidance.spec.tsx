import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {GuidancePanel} from '@/components/learning/practice/GuidancePanel'
const save=vi.hoisted(()=>vi.fn())
vi.mock('@/lib/practice-api',()=>({savePracticeGuidance:save}))
vi.mock('react-i18next',()=>({useTranslation:()=>({t:(key:string)=>key})}))
const data={config:{version:0,quality:'unknown' as const,kind:'unknown' as const,note:'',reference:''},status:'needs_confirmation',mastery:'not_established',due_at:null,evidence_ids:[],saved_explanation:'',attempts:[]}
it('requires a citation and preserves exact retry identity after an uncertain response',async()=>{
 const done=vi.fn();save.mockRejectedValueOnce(new Error('response lost')).mockResolvedValueOnce(data)
 render(<GuidancePanel id={5} workspaceId="course-a" data={data} onSaved={done}/>);
 fireEvent.click(screen.getByText('guidance.edit'))
 fireEvent.change(screen.getByLabelText('guidance.note'),{target:{value:'Synthetic explanation'}})
 expect(screen.getByRole('button',{name:'guidance.save'})).toBeDisabled()
 fireEvent.change(screen.getByLabelText('guidance.reference'),{target:{value:'synthetic.pdf p2'}})
 fireEvent.click(screen.getByRole('button',{name:'guidance.save'}));await screen.findByRole('alert')
 expect(screen.getByLabelText('guidance.note')).toBeDisabled()
 fireEvent.click(screen.getByRole('button',{name:'guidance.save'}));await waitFor(()=>expect(done).toHaveBeenCalledOnce())
 expect(save.mock.calls[0]).toEqual(save.mock.calls[1]);expect(save.mock.calls[0][2]).toBe('course-a')
})
