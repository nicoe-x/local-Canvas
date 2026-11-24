import copy
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'open_studio/_canvas'))
import test_routes as routes


class VideoResampleRoutes(routes.RouteTests):
    def configure_ns(self, ns):
        self.derived=[]
        def create(owner, job, options):
            self.derived.append((owner,job,options));key=routes.uid()
            self.jobs[key]={'id':key,'owner':owner,'state':'QUEUED','stage':'等待二采','progress':0,
                            'payload':json.dumps({'kind':'video'})}
            return {'id':key}
        ns['app'].state.h3_video_resample=create

    def setup_resample(self):
        job=routes.uid();self.jobs[job]={'id':job,'owner':'alice','state':'COMPLETED_UNREVIEWED',
                                       'payload':json.dumps({'kind':'video','seconds':5,'style':'写实'})}
        source=copy.deepcopy(self.node);source.update(id=routes.uid(),kind='video',job_id=job)
        target=copy.deepcopy(self.node);target.update(kind='video',text='',settings={
            'video_resample':{'source':source['id'],'steps':8,'denoise':.25}})
        value=self.board['document'];value['nodes']=[source,target]
        value['edges']=[{'source':source['id'],'target':target['id']}]
        result=self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':value})
        self.assertEqual(200,result.status_code,result.text)
        return source,target,job

    def test_resample_queues_owned_source_and_replay_is_idempotent(self):
        source,target,job=self.setup_resample();token=routes.uid()
        first=self.generate(token,revision=2);self.assertEqual(200,first.status_code,first.text)
        second=self.generate(token,revision=2);self.assertEqual(first.json()['job_id'],second.json()['job_id'])
        self.assertEqual(1,len(self.derived));self.assertEqual(('alice',job),self.derived[0][:2])
        self.assertEqual({'text':'','steps':8,'denoise':.25,'seed':None},self.derived[0][2])
        self.assertEqual([],self.created)
        self.assertEqual(409,self.generate(revision=2).status_code)

    def test_disconnected_source_rejected_before_job_creation(self):
        self.setup_resample();value=self.board['document'];value['edges']=[]
        self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':2,'document':value})
        self.assertEqual(422,self.generate(revision=3).status_code);self.assertEqual([],self.derived)

    def test_other_owner_and_unfinished_video_cannot_be_sampled(self):
        _,_,job=self.setup_resample();self.jobs[job]['state']='RUNNING'
        self.assertEqual(422,self.generate(revision=2).status_code)
        self.jobs[job]['state']='COMPLETED_UNREVIEWED';self.jobs[job]['owner']='bob'
        self.assertEqual(404,self.generate(revision=2).status_code);self.assertEqual([],self.derived)

    def test_missing_adapter_and_stale_revision_do_not_queue(self):
        self.setup_resample();self.assertEqual(409,self.generate(revision=1).status_code)
        self.ns['app'].state.h3_video_resample=None
        self.assertEqual(501,self.generate(revision=2).status_code);self.assertEqual([],self.derived)

    def test_settings_reject_paths_unknown_keys_boolean_and_non_video_nodes(self):
        source,target,_=self.setup_resample()
        for change in [{'source':'../video.mp4'},{'steps':True},{'steps':33},{'denoise':0},
                       {'denoise':True},{'path':'/tmp/source.mp4'}]:
            value=copy.deepcopy(self.board['document']);value['nodes'][1]['settings']['video_resample'].update(change)
            response=self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':2,'document':value})
            self.assertEqual(422,response.status_code,response.text)
        self.assertEqual([],self.derived)

    def test_capability_is_server_advertised(self):
        self.assertTrue(self.client.get('/api/canvas-config',headers=self.headers).json()['video_resample'])

    def test_plain_edit_request_uses_local_converter_before_queue(self):
        self.setup_resample();value=self.board['document'];value['nodes'][1]['text']='让衣服纹理更清楚'
        self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':2,'document':value})
        response=self.generate(revision=3);self.assertEqual(200,response.status_code,response.text)
        self.assertTrue(self.derived[0][2]['text'].startswith('subject_definitions:'))
        self.assertIn('<Picture 1>',self.derived[0][2]['text'])
