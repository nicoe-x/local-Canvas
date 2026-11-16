import asyncio
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi.testclient import TestClient
from PIL import Image
from open_studio.app import create_app
from open_studio.config import endpoint
from open_studio.workflows import standard,validate,render


class FakeComfy:
    def __init__(self):
        self.posts=[];self.uncertain=False
        out=io.BytesIO();Image.new('RGB',(32,24),'blue').save(out,format='PNG');self.image=out.getvalue()
        graph=standard('fixture.safetensors')['graph']
        self.info={v['class_type']:{'input':{'required':{}}} for v in graph.values()}
        self.info['CheckpointLoaderSimple']['input']['required']['ckpt_name']=[['fixture.safetensors']]

    def __call__(self,request):
        path=request.url.path
        if path=='/system_stats':return httpx.Response(200,json={'devices':[{'name':'fixture GPU'}],'system':{'comfyui_version':'test'}})
        if path=='/object_info':return httpx.Response(200,json=self.info)
        if path=='/prompt':
            self.posts.append((request.url.host,json.loads(request.content)))
            if self.uncertain:raise httpx.ReadTimeout('fixture timeout')
            return httpx.Response(200,json={'prompt_id':'fixture-prompt'})
        if path=='/history/fixture-prompt':return httpx.Response(200,json={'fixture-prompt':{'status':{'completed':True},'outputs':{'7':{'images':[{'filename':'fixture.png','subfolder':'OpenStudio/test','type':'output'}]}}}})
        if path=='/view':return httpx.Response(200,content=self.image,headers={'content-type':'image/png'})
        if path=='/upload/image':return httpx.Response(200,json={'name':'reference.jpg','subfolder':'OpenStudio','type':'input'})
        if path=='/queue':return httpx.Response(200,json={'queue_running':[],'queue_pending':[]})
        if path=='/history':return httpx.Response(200,json={})
        return httpx.Response(404,json={})


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.fake=FakeComfy();self.app=create_app(self.root,httpx.MockTransport(self.fake),start_worker=False);self.client=TestClient(self.app)
        token=(self.root/'setup-token').read_text()
        self.assertEqual(200,self.client.post('/api/setup',json={'username':'owner','password':'test-password','token':token}).status_code)
        self.assertFalse((self.root/'setup-token').exists())
        self.headers={'x-csrf-token':self.client.post('/api/login',json={'login':'owner','password':'test-password'}).json()['csrf']}

    def connect(self):
        response=self.client.post('/api/comfy/connect',headers=self.headers,json={'url':'http://127.0.0.1:8188','headers':{'Authorization':'Bearer fixture-secret'},'verify_tls':True})
        self.assertEqual(200,response.status_code,response.text)
        return self.client.get('/api/workflows').json()['items'][0]

    def new_job(self):
        profile=self.connect();response=self.client.post('/api/jobs',headers=self.headers,json={'variant':profile['id'],'kind':'image','text':'a blue cup','steps':8,'cfg':1,'ratio':'16:9'})
        self.assertEqual(200,response.status_code,response.text);return response.json()['id'],profile

    def test_auth_and_csrf(self):
        self.assertEqual(403,self.client.post('/api/comfy/connect',json={}).status_code)
        self.assertEqual(401,TestClient(self.app).get('/api/me').status_code)
        self.assertEqual(401,self.client.post('/api/login',json={'login':'owner','password':'wrong'}).status_code)
        self.assertNotIn('test-password',(self.root/'studio.sqlite3').read_bytes().decode('latin1'))
        self.assertEqual(403,self.client.post('/api/comfy/discover',headers={**self.headers,'origin':'https://foreign.example'},json={}).status_code)

    def test_connection_models_and_secret_redaction(self):
        profile=self.connect();self.assertEqual('image',profile['kind'])
        value=self.client.get('/api/settings').json();self.assertTrue(value['comfy']['has_auth']);self.assertNotIn('fixture-secret',json.dumps(value))
        self.assertEqual(['fixture.safetensors'],self.client.get('/api/comfy/status').json()['models']['CheckpointLoaderSimple.ckpt_name'])

    def test_queue_snapshot_and_unreviewed_output(self):
        key,profile=self.new_job();user=self.client.get('/api/me').json()['id'];store=self.app.state.store
        profile['graph']['1']['inputs']['ckpt_name']='changed.safetensors';store.save_workflow(profile)
        cfg=self.app.state.config.read();cfg['comfy']['url']='http://127.0.0.2:8188';self.app.state.config.write(cfg)
        async def no_ws(_):await asyncio.sleep(100)
        with patch.object(self.app.state.engine,'watch',no_ws):asyncio.run(self.app.state.engine.run(dict(store.job(key,user))))
        self.assertEqual(1,len(self.fake.posts));self.assertEqual('127.0.0.1',self.fake.posts[0][0]);self.assertEqual('fixture.safetensors',self.fake.posts[0][1]['prompt']['1']['inputs']['ckpt_name'])
        value=self.client.get('/api/jobs/'+key).json();self.assertEqual('COMPLETED_UNREVIEWED',value['state']);self.assertFalse(value['detail']['reviewed']);self.assertNotIn('fixture-secret',json.dumps(value))
        self.assertEqual(200,self.client.get('/api/jobs/'+key+'/image').status_code)

    def test_uncertain_post_is_not_automatically_repeated(self):
        key,_=self.new_job();user=self.client.get('/api/me').json()['id'];self.fake.uncertain=True
        asyncio.run(self.app.state.engine.run(dict(self.app.state.store.job(key,user))))
        self.assertEqual('NEEDS_ATTENTION',self.app.state.store.job(key,user)['state']);self.assertEqual(1,len(self.fake.posts))
        async def restart():
            self.app.state.engine.start();await asyncio.sleep(.05);await self.app.state.engine.close()
        asyncio.run(restart());self.assertEqual(1,len(self.fake.posts))

    def test_cancel_does_not_interrupt_shared_comfy(self):
        key,_=self.new_job();self.assertEqual(200,self.client.post('/api/jobs/'+key+'/cancel',headers=self.headers).status_code)
        self.assertEqual('CANCELLED',self.client.get('/api/jobs/'+key).json()['state']);self.assertEqual([],self.fake.posts)
        self.app.state.store.update(key,state='RUNNING')
        self.assertEqual(409,self.client.post('/api/jobs/'+key+'/cancel',headers=self.headers).status_code)

    def test_workflow_and_parameter_validation(self):
        self.connect()
        self.assertEqual(422,self.client.post('/api/workflows',headers=self.headers,json={'name':'bad','kind':'image','graph':{'nodes':[]}}).status_code)
        self.assertEqual(422,self.client.post('/api/jobs',headers=self.headers,json={'text':'x','kind':'image','variant':'missing','steps':0}).status_code)

    def test_canvas_trash_local_jpeg_purge(self):
        node={'id':uuid.uuid4().hex,'kind':'asset','x':0,'y':0,'settings':{}}
        b=self.client.post('/api/canvases',headers=self.headers,json={'title':'fixture','nodes':[],'edges':[]}).json()
        result=self.client.post('/api/canvases/'+b['id']+'/media',headers=self.headers,content=self.fake.image).json();node['media_id']=result['media_id']
        b=self.client.put('/api/canvases/'+b['id'],headers=self.headers,json={'revision':b['revision'],'document':{**b['document'],'nodes':[node]}}).json()
        r=self.client.post('/api/canvases/'+b['id']+'/trash',headers=self.headers,json={'revision':b['revision'],'node_ids':[node['id']],'request_id':uuid.uuid4().hex})
        self.assertEqual(200,r.status_code,r.text);token=r.json()['trash_id']
        response=self.client.post('/api/canvas-trash/purge',headers=self.headers,json={'ids':[token]});self.assertEqual([],response.json()['failed'],response.text)
        self.assertEqual(404,self.client.get('/api/canvases/'+b['id']+'/media/'+node['media_id']).status_code)

    def test_portable_canvas_assets(self):
        response=self.client.get('/canvas');self.assertEqual(200,response.status_code);self.assertIn('/portable/canvas.js',response.text)
        self.assertEqual(200,self.client.get('/canvas-progress.js').status_code)

    def test_reference_workflow_upload_and_binding(self):
        profile=self.connect();self.fake.info.update({'LoadImage':{'input':{'required':{}}},'VAEEncode':{'input':{'required':{}}}})
        profile.pop('bindings');profile.pop('id');profile['name']='reference fixture'
        profile['graph']['8']={'class_type':'LoadImage','inputs':{'image':'old.png'}}
        profile['graph']['9']={'class_type':'VAEEncode','inputs':{'pixels':['8',0],'vae':['1',2]}}
        profile['graph']['5']['inputs']['latent_image']=['9',0]
        response=self.client.post('/api/workflows',headers=self.headers,json=profile);self.assertEqual(200,response.status_code,response.text);profile=response.json()
        payload={'variant':profile['id'],'kind':'image','text':'reference cup','ratio':'16:9'}
        self.assertEqual(422,self.client.post('/api/jobs',headers=self.headers,json=payload).status_code)
        response=self.client.post('/api/generate',headers=self.headers,data={'metadata':json.dumps(payload)},files={'images':('reference.png',self.fake.image,'image/png')})
        self.assertEqual(200,response.status_code,response.text);key=response.json()['id'];user=self.client.get('/api/me').json()['id']
        async def no_ws(_):await asyncio.sleep(100)
        with patch.object(self.app.state.engine,'watch',no_ws):asyncio.run(self.app.state.engine.run(dict(self.app.state.store.job(key,user))))
        self.assertEqual('OpenStudio/reference.jpg',self.fake.posts[0][1]['prompt']['8']['inputs']['image'])

    def test_file_purge_blocks_shared_canvas_reference_without_hiding_job(self):
        key,profile=self.new_job();user=self.client.get('/api/me').json()['id'];self.app.state.store.update(key,state='COMPLETED_UNREVIEWED')
        node={'id':uuid.uuid4().hex,'kind':'image','x':0,'y':0,'settings':{},'job_id':key}
        b=self.client.post('/api/canvases',headers=self.headers,json={'title':'shared','nodes':[node],'edges':[]});self.assertEqual(200,b.status_code,b.text)
        response=self.client.delete('/api/jobs/'+key+'/image-files',headers=self.headers);self.assertEqual(409,response.status_code)
        self.assertEqual(200,self.client.get('/api/jobs/'+key).status_code)

    def test_release_builder_excludes_private_deployment(self):
        import importlib.util,zipfile,hashlib
        path=Path(__file__).resolve().parents[1]/'scripts/build_release.py'
        spec=importlib.util.spec_from_file_location('release_builder',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        value=module.build(self.root/'release.zip')
        with zipfile.ZipFile(value['path']) as archive:
            self.assertFalse(any(n.endswith(('.sqlite3','.env','credentials.json','deploy.py','private_auth.py','canvas_file_delete.py')) for n in archive.namelist()))
            manifest=json.loads(archive.read('open-comfy-studio/MANIFEST.sha256.json'))
            for name,sha in manifest.items():self.assertEqual(sha,hashlib.sha256(archive.read('open-comfy-studio/'+name)).hexdigest())
            compose=archive.read('open-comfy-studio/compose.yaml').decode();self.assertIn('build: .',compose)


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_verifies_service_and_never_submits(self):
        from open_studio.comfy import Comfy
        from open_studio.config import Config
        with tempfile.TemporaryDirectory() as root:
            fake=FakeComfy();adapter=Comfy(Config(root),httpx.MockTransport(fake));items=await adapter.scan(ports=[8188]);self.assertTrue(items[0]['healthy']);self.assertEqual([],fake.posts)
            def auth(_):return httpx.Response(401)
            value=await Comfy(Config(root),httpx.MockTransport(auth)).inspect('http://127.0.0.1:8188');self.assertTrue(value['auth_required']);self.assertFalse(value['healthy'])
            def html(_):return httpx.Response(200,text='<html>not ComfyUI</html>')
            with self.assertRaises(ValueError):await Comfy(Config(root),httpx.MockTransport(html)).inspect('http://127.0.0.1:8188')
            with self.assertRaises(ValueError):await adapter.scan('10.0.0.0/16')

    def test_private_network_policy(self):
        for url in ['http://169.254.169.254','file:///tmp/comfy','http://8.8.8.8','http://user:pass@127.0.0.1:8188','http://127.0.0.1:8188/?token=x']:
            with self.assertRaises(ValueError):endpoint(url)
        self.assertEqual('http://127.0.0.1:8188',endpoint('http://127.0.0.1:8188'))

    def test_binding_and_frame_alignment(self):
        profile=standard('fixture.safetensors');graph=render(profile,{'text':'blue','ratio':'9:16','steps':12,'cfg':2,'seed':42},[])
        self.assertEqual('blue',graph['2']['inputs']['text']);self.assertEqual(42,graph['5']['inputs']['seed']);self.assertGreater(graph['4']['inputs']['height'],graph['4']['inputs']['width'])
        with self.assertRaises(ValueError):render(profile,{'text':'x'},['unexpected-reference'])
        profile['bindings']['positive']=[{'node':'missing','input':'text'}]
        with self.assertRaises(ValueError):validate(profile)


if __name__=='__main__':unittest.main()
