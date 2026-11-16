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
        for invalid in [prompt(),valid.replace('我到了。','我马上到。'),valid.replace('[Chinese]','[English]'),valid.replace('</d>','')]:
            with self.assertRaises(ValueError):validate_result({'segments':[{'seconds':5,'prompt':invalid}]},request)

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


if __name__=='__main__':unittest.main()
