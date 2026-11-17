import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"open_studio/_canvas"))
"""Real FastAPI routes with a fake generator; no GPU work in automated tests."""
import asyncio
from contextlib import contextmanager
import io
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from canvas_routes import register


def uid():
    return uuid.uuid4().hex


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.jobs={}
        self.created=[]
        app=FastAPI()
        def auth(request, **kwargs):
            if request.headers.get('authorization') not in {'alice','bob'}:
                raise HTTPException(401,'登录失效')
            if kwargs.get('write') and request.headers.get('x-csrf-token')!='csrf':
                raise HTTPException(403,'CSRF')
            return {'id':request.headers['authorization']}
        def owned(key, owner):
            row=self.jobs.get(key)
            if not row or row['owner']!=owner:
                raise HTTPException(404,'任务不存在')
            return row
        fixture = self
        @contextmanager
        def database():
            class Query:
                def execute(self, _query, args):
                    self.key=args[0]
                    return self
                def fetchone(self):
                    return fixture.jobs.get(self.key)
            yield Query()
        async def create(**kwargs):
            payload=json.loads(kwargs['metadata']);self.created.append(payload)
            key=uid();self.jobs[key]={'id':key,'owner':kwargs['request'].headers['authorization'],'state':'QUEUED','stage':'等待生成','progress':0,'payload':kwargs['metadata']}
            return {'id':key}
        class Generation:
            @staticmethod
            def model_validate(value):
                return value
        self.ns=dict(app=app,DATA=self.root/'data',MATERIAL=self.root/'materials',authenticate=auth,owned_job=owned,create=create,
                      Generation=Generation,TERMINAL={'FAILED','COMPLETED_UNREVIEWED','NEEDS_ATTENTION','CANCELLED'},
                      STYLE_PROMPTS={'自定义风格':'','写实':''},VIDEO_STYLES={'写实':''},user_folder=lambda owner:owner,
                      database=database,
                      output_folder=lambda row:self.root/row['id'],clean_image=lambda raw:raw,UnidentifiedImageError=ValueError)
        if hasattr(self,"configure_ns"): self.configure_ns(self.ns)
        from canvas_h3 import compile_prompt
        app.state.h3_prompt_request_type=lambda **kwargs:kwargs
        async def prepare(_request,body):
            return {'segments':[{'seconds':body['seconds'],'prompt':compile_prompt(body['source'],body['references'],body['seconds'],body['style'])}]}
        app.state.h3_prompt_prepare=prepare
        register(self.ns)
        self.client=TestClient(app)
        self.headers={'authorization':'alice','x-csrf-token':'csrf'}
        self.node=dict(id=uid(),kind='image',x=0,y=0,title='白杯',text='a white cup',settings={})
        response=self.client.post('/api/canvases',headers=self.headers,json={'title':'私人测试','nodes':[self.node],'edges':[]})
        self.assertEqual(200,response.status_code,response.text)
        self.board=response.json()

    def generate(self, token=None, **body):
        return self.client.post(f'/api/canvases/{self.board["id"]}/nodes/{self.node["id"]}/generate',headers=self.headers,
                                json={'revision':1,'token':token or uid(),**body})

    def test_auth_csrf_and_other_owner(self):
        self.assertEqual(401,self.client.get('/api/canvases').status_code)
        self.assertEqual(403,self.client.post('/api/canvases',headers={'authorization':'alice'},json={}).status_code)
        self.assertEqual(404,self.client.get('/api/canvases/'+self.board['id'],headers={'authorization':'bob'}).status_code)

    def test_mentions_follow_node_identity_and_reject_disconnected_sources(self):
        value=self.board['document'];assets=[]
        for index in range(2):
            media=self.client.post('/api/canvases/'+self.board['id']+'/media',headers=self.headers,content=b'pretend jpeg').json()
            assets.append(dict(id=uid(),kind='asset',title='same name',x=index*30,y=0,media_id=media['media_id']))
        value['nodes']+=assets
        target=value['nodes'][0];target['kind']='video';target['text']='@参考图1 beside @参考图2'
        # Alias numbering intentionally differs from connection/upload order.
        target['settings'].update(reference_mentions={'参考图1':assets[1]['id'],'参考图2':assets[0]['id']})
        value['edges']=[{'source':a['id'],'target':target['id']} for a in assets]
        response=self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':value})
        self.assertEqual(200,response.status_code,response.text)
        generated=self.generate(revision=2)
        self.assertEqual(200,generated.status_code,generated.text)
        self.assertIn('<Picture 2> beside <Picture 1>',self.created[-1]['text']);self.assertTrue(self.created[-1]['text'].startswith('subject_definitions:'))
        self.jobs[generated.json()['job_id']]['state']='COMPLETED_UNREVIEWED'
        value['edges']=value['edges'][:1]
        response=self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':2,'document':value})
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual(422,self.generate(revision=3).status_code)
        self.assertEqual(1,len(self.created))

    def test_unknown_reference_alias_does_not_submit(self):
        value=self.board['document'];value['nodes'][0]['text']='use @参考图9'
        self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':value})
        response=self.generate(revision=2)
        self.assertEqual(422,response.status_code,response.text)
        self.assertEqual([],self.created)

    def test_duplicate_and_active_submission(self):
        token=uid();first=self.generate(token)
        self.assertEqual(200,first.status_code,first.text)
        second=self.generate(token)
        self.assertEqual(first.json()['job_id'],second.json()['job_id'])
        self.assertEqual(1,len(self.created))
        self.assertEqual(409,self.generate().status_code)
        runs=self.client.get('/api/canvases/'+self.board['id']+'/runs',headers=self.headers).json()
        self.assertEqual('QUEUED',runs[0]['job_state'])

    def test_revision_mismatch_and_unlimited_manual_generations(self):
        self.assertEqual(409,self.generate(revision=0).status_code)
        for kind in ['image','video']:
            if kind=='video':
                value=self.board['document'];value['nodes'][0]['kind']='video'
                self.board=self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':self.board['revision'],'document':value}).json()
            for _ in range(10):
                response=self.generate(revision=self.board['revision'])
                self.assertEqual(200,response.status_code,response.text)
                self.jobs[response.json()['job_id']]['state']='COMPLETED_UNREVIEWED'
        self.assertEqual(20,len(self.created))

    def test_connected_prompt_and_uploaded_reference(self):
        note=dict(id=uid(),kind='note',x=10,y=10,text='前景一只杯子')
        media=self.client.post('/api/canvases/'+self.board['id']+'/media',headers=self.headers,content=b'pretend jpeg').json()
        asset=dict(id=uid(),kind='asset',x=30,y=30,media_id=media['media_id'])
        value=self.board['document'];value['nodes'] += [note,asset]
        value['nodes'][0]['settings']['variant']='h3_image_w4a8'
        value['edges']=[{'source':note['id'],'target':self.node['id']},{'source':asset['id'],'target':self.node['id']}]
        saved=self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':value})
        self.assertEqual(200,saved.status_code,saved.text)
        self.assertEqual(200,self.generate(revision=2).status_code)
        self.assertEqual('前景一只杯子\n\na white cup',self.created[-1]['text'])
        self.assertEqual(['参考图1'],self.created[-1]['labels'])
        self.assertFalse(self.created[-1]['expedite'])
        url=f'/api/canvases/{self.board["id"]}/media/{media["media_id"]}'
        self.assertEqual(404,self.client.get(url,headers={'authorization':'bob'}).status_code)
        self.assertEqual(200,self.client.get(url,headers=self.headers).status_code)

    def test_video_segment_limit(self):
        value=self.board['document'];value['nodes'][0]['kind']='video';value['nodes'][0]['settings']['seconds']=30
        self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':value})
        self.assertEqual(422,self.generate(revision=2).status_code)
        self.assertEqual([],self.created)

    def test_pending_uncertain_never_auto_resubmits(self):
        from canvas_store import Store,fingerprint
        store=Store(self.root/'data/canvases.sqlite3')
        store.claim('alice',self.board['id'],self.node['id'],uid(),'unknown')
        self.assertEqual(409,self.generate().status_code)
        self.assertEqual([],self.created)

    def test_foreign_media_reference_rejected(self):
        key=uid();self.jobs[key]={'id':key,'owner':'bob','state':'COMPLETED_UNREVIEWED'}
        value=self.board['document'];value['nodes'].append(dict(id=uid(),kind='asset',x=1,y=2,job_id=key))
        result=self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':value})
        self.assertEqual(404,result.status_code)

    def test_malformed_document_rejected_without_500(self):
        self.assertEqual(422,self.client.post('/api/canvases',headers=self.headers,json=[]).status_code)
        self.assertEqual(422,self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json=[]).status_code)
        value=self.board['document'];value['edges']=[{'source':[],'target':self.node['id']}]
        self.assertEqual(422,self.client.post('/api/canvases',headers=self.headers,json=value).status_code)

    def test_unsupported_refs_refused_before_reading_files(self):
        value=self.board['document'];asset=dict(id=uid(),kind='asset',x=1,y=1,media_id=uid())
        folder=self.root/'materials/canvas/alice'/self.board['id'];folder.mkdir(parents=True,exist_ok=True);(folder/(asset['media_id']+'.jpg')).write_bytes(b'fixture')
        value['nodes'].append(asset);value['edges']=[{'source':asset['id'],'target':self.node['id']}]
        self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':value})
        response=self.generate(revision=2)
        self.assertEqual(422,response.status_code)
        self.assertIn('仅支持文生图',response.text)
        self.assertEqual([],self.created)

    def test_reverse_output_is_text_not_image_reference(self):
        value=self.board['document'];source=dict(id=uid(),kind='reverse',x=1,y=1,text='a ceramic cup, natural lighting',settings={})
        value['nodes'].append(source);value['edges']=[{'source':source['id'],'target':self.node['id']}]
        self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':value})
        self.assertEqual(200,self.generate(revision=2).status_code)
        self.assertEqual([],self.created[-1]['labels'])
        self.assertTrue(self.created[-1]['text'].startswith(source['text']))

    def test_unfinished_reverse_blocks_downstream(self):
        value=self.board['document'];source=dict(id=uid(),kind='reverse',x=1,y=1,text='',settings={})
        value['nodes'].append(source);value['edges']=[{'source':source['id'],'target':self.node['id']}]
        self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':value})
        response=self.generate(revision=2)
        self.assertEqual(422,response.status_code)
        self.assertEqual([],self.created)


if __name__=='__main__':
    unittest.main()
