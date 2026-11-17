import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from open_studio.app import create_app
from open_studio.h3_prompts import PromptRequest, plan, validate_result


def prompt(dialogue=''):
    return ('integrated_multimodal_description: [Shot 1] Live-action, a woman holds a phone. '
            + dialogue + ' No subtitles or captions.\n\noverall_soundscape: Quiet room ambience.\n\nnon_diegetic_music: N/A')


class FormatTests(unittest.TestCase):
    def test_duration_plan_never_leaves_tiny_tail(self):
        for duration in range(4,91):
            parts=plan(duration)
            self.assertEqual(duration,sum(parts))
            self.assertTrue(all(4<=item<=15 for item in parts))

    def test_dialogue_exact_once_and_order(self):
        request=PromptRequest(source='她说：“我到了。”',seconds=5)
        valid=prompt('(S1) [calm] says: <d>[Chinese] 我到了。</d>')
        self.assertFalse(validate_result({'segments':[{'seconds':5,'prompt':valid}]},request)['reviewed'])
        for invalid in [prompt(),valid.replace('我到了。','我马上到。'),valid.replace('[Chinese]','[English]'),valid.replace('</d>',''),valid.replace('(S1)','')]:
            with self.assertRaises(ValueError):validate_result({'segments':[{'seconds':5,'prompt':invalid}]},request)

    def test_verbatim_dialogue_wrappers_are_canonicalized_without_rewriting(self):
        request=PromptRequest(source='她说：“我到了。”',seconds=5)
        for dialogue in ['<d> [Chinese] “我到了。” </d>','<d>我到了。</d>']:
            value=validate_result({'segments':[{'seconds':5,'prompt':prompt('(S1) says: '+dialogue)}]},request)
            self.assertIn('<d>[Chinese] 我到了。</d>',value['segments'][0]['prompt'])
        with self.assertRaises(ValueError):
            validate_result({'segments':[{'seconds':5,'prompt':prompt('<d>我马上到。</d>')}]},request)

    def test_reject_broken_template_and_hallucinated_references(self):
        request=PromptRequest(source='A woman holds a phone.',seconds=5)
        for invalid in [prompt().replace('non_diegetic_music: N/A','non_diegetic_music: Piano'),
                        prompt().replace('No subtitles or captions.',''),prompt()+'\nsummary: extra',
                        prompt().replace('a woman','<Subject 1>'),prompt().replace('a woman','<Picture 1>'),
                        '```\n'+prompt()+'\n```', prompt().replace('[Shot 1]','[Shot 2]')]:
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                validate_result({'segments':[{'seconds':5,'prompt':invalid}]},request)

    def test_local_cut_time_and_budget(self):
        request=PromptRequest(source='A woman holds a phone.',seconds=10)
        valid=prompt().replace('No subtitles','[Shot 2] At 00:05.000, the camera cuts to her hands. No subtitles')
        validate_result({'segments':[{'seconds':10,'prompt':valid}]},request)
        for time in ['00:01.000','00:10.000','00:07.600','00:65.000']:
            with self.assertRaises(ValueError):validate_result({'segments':[{'seconds':10,'prompt':valid.replace('00:05.000',time)}]},request)

    def test_reference_mode_uses_six_fields(self):
        request=PromptRequest(source='The woman walks.',seconds=5,references=['林薇'])
        valid='subject_definitions: <Subject 1> is the woman in <Picture 1>.\nsummary: Ref2VA, five seconds.\nretention_analysis: Preserve her identity and clothes throughout Shot 1.\ndetailed_description: [Shot 1] <Subject 1> walks slowly. No subtitles or captions.\noverall_soundscape: Footsteps.\nnon_diegetic_music: N/A'
        validate_result({'segments':[{'seconds':5,'prompt':valid}]},request)
        with self.assertRaises(ValueError):validate_result({'segments':[{'seconds':5,'prompt':valid.replace('<Picture 1>','<Picture 2>')}]},request)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.requests=[];self.result={'segments':[{'seconds':5,'prompt':prompt()}]}
        def service(request):
            self.requests.append(request)
            return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(self.result)}}]})
        self.app=create_app(self.temp.name,httpx.MockTransport(service),start_worker=False)
        self.client=TestClient(self.app)
        token=(Path(self.temp.name)/'setup-token').read_text()
        self.client.post('/api/setup',json={'username':'owner','password':'test-password','token':token})
        self.headers={'x-csrf-token':self.client.post('/api/login',json={'login':'owner','password':'test-password'}).json()['csrf']}
        self.body={'source':'A woman holds a phone.','seconds':5,'style':'Live-action'}

    def test_requires_auth_csrf_and_configuration(self):
        self.assertEqual(401,TestClient(self.app).post('/api/prompts/h3',json=self.body).status_code)
        self.assertEqual(403,self.client.post('/api/prompts/h3',json=self.body).status_code)
        with patch.dict(os.environ,{'STUDIO_TEXT_URL':'','STUDIO_TEXT_MODEL':''}):
            self.assertEqual(501,self.client.post('/api/prompts/h3',headers=self.headers,json=self.body).status_code)
        self.assertFalse(self.requests)

    def test_convert_does_not_submit_comfy_or_create_jobs(self):
        with patch.dict(os.environ,{'STUDIO_TEXT_URL':'http://localhost:1234/v1','STUDIO_TEXT_MODEL':'local-text','STUDIO_TEXT_KEY':'test-secret'}):
            response=self.client.post('/api/prompts/h3',headers=self.headers,json=self.body)
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual('/v1/chat/completions',self.requests[0].url.path)
        self.assertNotIn('test-secret',response.text)
        self.assertEqual(0,self.client.get('/api/jobs').json()['total'])
        self.result['segments'][0]['prompt']='bad format'
        with patch.dict(os.environ,{'STUDIO_TEXT_URL':'http://localhost:1234/v1','STUDIO_TEXT_MODEL':'local-text'}):
            self.assertEqual(422,self.client.post('/api/prompts/h3',headers=self.headers,json=self.body).status_code)

    def test_face_guidance_reaches_converter_without_overriding_authored_composition(self):
        # A text-only converter must receive the constraints and the original
        # shot separately; passing a person name is not visual face inspection.
        source='二维动画，全景全身，女子在夜晚庭院散步，不切镜。'
        self.result={'segments':[{'seconds':5,'prompt':prompt().replace('Live-action, a woman holds a phone.',
            '2D animation, continuous wide full-body shot of a woman walking in a night courtyard.')}]}
        with patch.dict(os.environ,{'STUDIO_TEXT_URL':'http://localhost:1234/v1','STUDIO_TEXT_MODEL':'local-text'}):
            response=self.client.post('/api/prompts/h3',headers=self.headers,json={**self.body,'source':source,'style':'二维动画'})
        self.assertEqual(200,response.status_code,response.text)
        sent=json.loads(self.requests[0].content)['messages']
        data=json.loads(sent[1]['content'])
        self.assertEqual(source,data['source']);self.assertEqual('二维动画',data['style'])
        self.assertEqual([],data['reference_mapping'])
        for rule in ['Preserve explicitly requested wide shots', 'soft reflected fill',
                     'never turn animation into live action', 'not image pixels',
                     'do not claim to have inspected a face']:
            self.assertIn(rule,sent[0]['content'])
        self.assertIn('continuous wide full-body',response.json()['segments'][0]['prompt'])
        self.assertEqual(0,self.client.get('/api/jobs').json()['total'])

    def test_h3_video_template_is_not_prefixed_with_style(self):
        from open_studio.workflows import standard
        profile=standard('fixture.safetensors');profile['kind']='video'
        profile=self.app.state.store.save_workflow(profile)
        self.app.state.config.write({'comfy':{'url':'http://localhost:8188'}})
        text=prompt()
        response=self.client.post('/api/jobs',headers=self.headers,json={'kind':'video','variant':profile['id'],'text':text,'style':'写实'})
        self.assertEqual(200,response.status_code,response.text)
        job=self.client.get('/api/jobs/'+response.json()['id']).json()
        self.assertEqual(text,job['payload']['text'])

    def test_input_limits_and_saved_source_roundtrip(self):
        self.assertEqual(422,self.client.post('/api/prompts/h3',headers=self.headers,json={**self.body,'seconds':91}).status_code)
        self.assertEqual(422,self.client.post('/api/prompts/h3',headers=self.headers,json={**self.body,'references':['x'*201]}).status_code)
        import uuid
        node={'id':uuid.uuid4().hex,'kind':'note','title':'H3 提示词转换','text':'','x':0,'y':0,'settings':{'h3_prompt':self.body}}
        response=self.client.post('/api/canvases',headers=self.headers,json={'title':'test','nodes':[node],'edges':[]})
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual(self.body,response.json()['document']['nodes'][0]['settings']['h3_prompt'])

    def test_local_adapter_precedes_static_mount_and_never_falls_back(self):
        from fastapi import FastAPI,HTTPException
        from fastapi.staticfiles import StaticFiles
        from open_studio.h3_prompt_routes import register
        app=FastAPI();app.mount('/',StaticFiles(directory=self.temp.name))
        calls=[]
        def convert(messages):
            calls.append(messages)
            return self.result
        register(app,lambda *args,**kwargs:{'id':'local-owner'},converter=convert)
        client=TestClient(app)
        self.assertEqual(200,client.post('/api/prompts/h3',json=self.body).status_code)
        self.assertEqual(1,len(calls))
        def busy(messages):raise HTTPException(409,'GPU busy')
        other=FastAPI();register(other,lambda *args,**kwargs:{'id':'owner'},converter=busy)
        self.assertEqual(409,TestClient(other).post('/api/prompts/h3',json=self.body).status_code)
        self.assertFalse(self.requests)

    def test_plain_video_text_is_converted_before_submission_and_retry_is_cached(self):
        import uuid
        from open_studio.workflows import standard
        profile=standard('fixture.safetensors');profile['kind']='video';profile=self.app.state.store.save_workflow(profile)
        self.app.state.config.write({'comfy':{'url':'http://localhost:8188'}})
        def video(text):return {'id':uuid.uuid4().hex,'kind':'video','title':'auto','x':0,'y':0,'text':text,'settings':{'variant':profile['id'],'seconds':5,'style':'写实'}}
        node=video(self.body['source'])
        board=self.client.post('/api/canvases',headers=self.headers,json={'title':'automatic','nodes':[node],'edges':[]}).json()
        endpoint='/api/canvases/'+board['id']+'/nodes/'+node['id']+'/generate';body={'revision':1,'token':uuid.uuid4().hex}
        with patch.dict(os.environ,{'STUDIO_TEXT_URL':'http://localhost:1234/v1','STUDIO_TEXT_MODEL':'local-text'}):
            first=self.client.post(endpoint,headers=self.headers,json=body)
            second=self.client.post(endpoint,headers=self.headers,json=body)
        self.assertEqual(200,first.status_code,first.text);self.assertEqual(first.json()['job_id'],second.json()['job_id'])
        self.assertEqual(1,len(self.requests));self.assertEqual(prompt(),self.client.get('/api/jobs/'+first.json()['job_id']).json()['payload']['text'])
        self.result={'segments':[{'seconds':5,'prompt':'invalid model output'}]}
        other=video('A woman opens a window.')
        board=self.client.post('/api/canvases',headers=self.headers,json={'title':'invalid','nodes':[other],'edges':[]}).json()
        with patch.dict(os.environ,{'STUDIO_TEXT_URL':'http://localhost:1234/v1','STUDIO_TEXT_MODEL':'local-text'}):
            failed=self.client.post('/api/canvases/'+board['id']+'/nodes/'+other['id']+'/generate',headers=self.headers,json={'revision':1,'token':uuid.uuid4().hex})
        self.assertEqual(422,failed.status_code,failed.text);self.assertEqual(1,self.client.get('/api/jobs').json()['total'])

    def test_face_repair_requires_backend_capability_and_persists_boolean(self):
        import uuid
        from open_studio.workflows import standard
        profile=standard('fixture.safetensors');profile['kind']='video';profile=self.app.state.store.save_workflow(profile)
        self.app.state.config.write({'comfy':{'url':'http://localhost:8188'}})
        node={'id':uuid.uuid4().hex,'kind':'video','title':'face','x':0,'y':0,'text':prompt(),
              'settings':{'variant':profile['id'],'seconds':5,'style':'写实','face_repair':True}}
        graph={'title':'face','nodes':[node],'edges':[]}
        saved=self.client.post('/api/canvases',headers=self.headers,json=graph)
        self.assertEqual(200,saved.status_code,saved.text);board=saved.json()
        endpoint='/api/canvases/'+board['id']+'/nodes/'+node['id']+'/generate'
        response=self.client.post(endpoint,headers=self.headers,json={'revision':1,'token':uuid.uuid4().hex})
        self.assertEqual(501,response.status_code);self.assertEqual(0,self.client.get('/api/jobs').json()['total'])
        self.app.state.h3_face_repair=True
        response=self.client.post(endpoint,headers=self.headers,json={'revision':1,'token':uuid.uuid4().hex})
        self.assertEqual(200,response.status_code,response.text)
        job=self.client.get('/api/jobs/'+response.json()['job_id']).json()
        self.assertIs(True,job['payload']['face_repair'])
        node['settings']['face_repair']='true'
        self.assertEqual(422,self.client.post('/api/canvases',headers=self.headers,json=graph).status_code)

    def test_native_node_persists_output_and_sends_only_selected_prompt(self):
        import uuid
        from open_studio.workflows import standard
        profile=standard('fixture.safetensors');profile['kind']='video';profile=self.app.state.store.save_workflow(profile)
        self.app.state.config.write({'comfy':{'url':'http://localhost:8188'}})
        h3={'id':uuid.uuid4().hex,'kind':'h3prompt','x':0,'y':0,'title':'H3 提示词节点1','text':prompt(),
            'settings':{'h3_prompt':self.body,'h3_result':{'segments':[{'seconds':5,'prompt':prompt()}],'selected':0,'model':'fixture','references':[],'input_source':self.body['source']}}}
        video={'id':uuid.uuid4().hex,'kind':'video','x':400,'y':0,'title':'视频节点1','text':'',
               'settings':{'variant':profile['id'],'seconds':5,'style':'写实'}}
        graph={'title':'native','nodes':[h3,video],'edges':[{'source':h3['id'],'target':video['id']}]}
        saved=self.client.post('/api/canvases',headers=self.headers,json=graph)
        self.assertEqual(200,saved.status_code,saved.text);board=saved.json()
        stored=self.client.get('/api/canvases/'+board['id']).json()['document']['nodes'][0]
        self.assertEqual('h3prompt',stored['kind']);self.assertEqual(prompt(),stored['settings']['h3_result']['segments'][0]['prompt'])
        url='/api/canvases/'+board['id']+'/nodes/'+video['id']+'/generate'
        response=self.client.post(url,headers=self.headers,json={'revision':1,'token':uuid.uuid4().hex})
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual(prompt(),self.client.get('/api/jobs/'+response.json()['job_id']).json()['payload']['text'])
        for change in ['unconverted','duration','source']:
            copy=json.loads(json.dumps(graph));source,target=copy['nodes']
            if change=='unconverted':source['text']='';source['settings'].pop('h3_result')
            elif change=='duration':target['settings']['seconds']=10
            else:source['settings']['h3_prompt']['source']='changed source'
            new=self.client.post('/api/canvases',headers=self.headers,json=copy).json()
            response=self.client.post('/api/canvases/'+new['id']+'/nodes/'+video['id']+'/generate',headers=self.headers,json={'revision':1,'token':uuid.uuid4().hex})
            self.assertEqual(422,response.status_code,(change,response.text))
        self.assertEqual(1,self.client.get('/api/jobs').json()['total'])


if __name__=='__main__':unittest.main()
