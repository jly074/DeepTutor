import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import UnsortedInbox from '@/components/learning/UnsortedInbox'
const request=vi.hoisted(()=>vi.fn())
const download=vi.hoisted(()=>vi.fn())
vi.mock('@/lib/unsorted-api',()=>({intakeRequest:request,downloadOriginal:download}))
vi.mock('@/lib/workspace-scope',()=>({scopedUrl:(x:string)=>x}))
vi.mock('react-i18next',()=>({useTranslation:()=>({t:(x:string)=>x})}))
it('requires consent and explicit classification without auto-collecting uploads',async()=>{
 const item={id:'v1',source_id:'s1',filename:'sample-a.txt',sha256:'a'.repeat(64),size_bytes:12,data_class:'synthetic',status:'pending',category:'',revision:1,created_at:1}
 let uploaded=false
 request.mockImplementation(async(ws,path,body)=>{
  expect(ws).toBe('course-a')
  if(path==='/batch'){expect(body.get('consent')).toBe('true');expect(body.getAll('files')).toHaveLength(2);uploaded=true;return {results:[{filename:item.filename,ok:true,item}]}}
  if(path==='/collect'){expect(body).toEqual({items:[{id:'v1',revision:1,category:'Manual category'}]});return {items:[]}}
  return {items:uploaded?[item]:[],next_offset:null}
 })
 render(<UnsortedInbox workspaceId="course-a"/>);
 await screen.findByText('unsorted.empty')
 fireEvent.click(screen.getByRole('button',{name:'unsorted.demo'}))
 expect(screen.getByRole('button',{name:'unsorted.upload'})).toBeDisabled()
 fireEvent.click(screen.getByLabelText('unsorted.consent'))
 fireEvent.click(screen.getByRole('button',{name:'unsorted.upload'}))
 await screen.findByTestId('intake-item')
 expect(request.mock.calls.filter(c=>c[1]==='/collect')).toHaveLength(0)
 fireEvent.click(screen.getByLabelText('sample-a.txt'))
 expect(screen.getByRole('button',{name:'unsorted.collect'})).toBeDisabled()
 fireEvent.change(screen.getByLabelText('unsorted.category'),{target:{value:'Manual category'}})
 fireEvent.click(screen.getByRole('button',{name:'unsorted.collect'}))
 await waitFor(()=>expect(request.mock.calls.filter(c=>c[1]==='/collect')).toHaveLength(1))
})
it('keeps the registry visible and explains missing original bytes',async()=>{
 request.mockReset();request.mockResolvedValue({items:[{id:'v1',source_id:'s1',filename:'synthetic.txt',sha256:'a'.repeat(64),size_bytes:1,data_class:'synthetic',status:'pending',category:'',revision:1,created_at:1}],next_offset:null})
 download.mockRejectedValueOnce(new Error('original_unavailable'))
 render(<UnsortedInbox workspaceId="course-a"/>);
 await screen.findByTestId('intake-item')
 fireEvent.click(screen.getByRole('button',{name:'unsorted.download'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('unsorted.originalUnavailable')
 expect(screen.getByTestId('intake-item')).toHaveTextContent('unsorted.pending')
})
