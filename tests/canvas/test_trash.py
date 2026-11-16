import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"open_studio/_canvas"))
"""Persistent trash lifecycle, conflicts, ownership and exact disk cleanup."""
import copy
import json
import sys
import types
from unittest.mock import patch
from test_routes import RouteTests, uid


class TrashTests(RouteTests):
    def move(self, nodes=None, revision=None, token=None):
        return self.client.post('/api/canvases/'+self.board['id']+'/trash',headers=self.headers,json={'revision':revision or self.board['revision'],'node_ids':nodes or [self.node['id']],'request_id':token or uid()})

    def items(self):
        return self.client.get('/api/canvas-trash',headers=self.headers).json()

    def test_persist_restore_edges_groups_and_idempotence(self):
        other=dict(self.node,id=uid());g=self.board['document'];g['nodes'].append(other);g['edges']=[{'source':self.node['id'],'target':other['id']}];g['groups']=[{'id':uid(),'title':'组','node_ids':[self.node['id'],other['id']]}]
        self.board=self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':g}).json()
        token=uid();r=self.move(token=token);self.assertEqual(200,r.status_code,r.text)
        self.assertEqual(1,len(r.json()['board']['document']['nodes']))
        self.assertEqual(200,self.move(token=token).status_code);self.assertEqual(1,len(self.items()))
        restored=self.client.post('/api/canvas-trash/'+token+'/restore',headers=self.headers)
        self.assertEqual(200,restored.status_code,restored.text)
        actual=restored.json()['document'];self.assertEqual({n['id'] for n in g['nodes']},{n['id'] for n in actual['nodes']});self.assertEqual(g['edges'],actual['edges']);self.assertEqual(set(g['groups'][0]['node_ids']),set(actual['groups'][0]['node_ids']));self.assertEqual([],self.items())

    def test_owner_csrf_revision_and_no_mutation_on_conflict(self):
        self.assertEqual(409,self.move(revision=99).status_code)
        self.assertEqual([],self.items());token=self.move().json()['trash_id']
        self.assertEqual([],self.client.get('/api/canvas-trash',headers={'authorization':'bob'}).json())
        self.assertEqual(409,self.client.post('/api/canvas-trash/'+token+'/restore',headers={'authorization':'bob','x-csrf-token':'csrf'}).status_code)
        self.assertEqual(403,self.client.post('/api/canvas-trash/purge',headers={'authorization':'alice'},json={'ids':[token]}).status_code)

    def test_uploaded_file_references_and_resumable_delete(self):
        media=uid();folder=self.root/'materials/canvas/alice'/self.board['id'];folder.mkdir(exist_ok=True,parents=True);path=folder/(media+'.jpg');path.write_bytes(b'fixture')
        graph=copy.deepcopy(self.board['document']);graph['nodes'][0]['media_id']=media;other=dict(graph['nodes'][0],id=uid());graph['nodes'].append(other)
        self.board=self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':graph}).json()
        first=self.move().json();self.board=first['board'];a=first['trash_id']
        self.assertEqual(409,self.client.post('/api/canvas-trash/purge',headers=self.headers,json={'ids':[a]}).status_code)
        second=self.move([other['id']]).json();b=second['trash_id']
        module=types.ModuleType('canvas_file_delete')
        module.erase_media=lambda *args: (_ for _ in ()).throw(RuntimeError('offline'))
        with patch.dict(sys.modules,{'canvas_file_delete':module}):
            result=self.client.post('/api/canvas-trash/purge',headers=self.headers,json={'ids':[a,b]}).json()
            self.assertEqual(2,len(result['failed']));self.assertTrue(path.exists())
            self.assertEqual(409,self.client.post('/api/canvas-trash/'+a+'/restore',headers=self.headers).status_code)
            module.erase_media=lambda *args:path.unlink(missing_ok=True)
            result=self.client.post('/api/canvas-trash/purge',headers=self.headers,json={'ids':[a,b]}).json()
            self.assertEqual(2,len(result['deleted']));self.assertFalse(path.exists());self.assertEqual([],self.items())
        self.assertEqual(409,self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':second['board']['revision'],'document':graph}).status_code)

    def test_restore_duplicate_id_keeps_trash(self):
        record=self.move().json();self.board=record['board'];graph=self.board['document'];graph['nodes']=[self.node]
        self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':self.board['revision'],'document':graph})
        self.assertEqual(409,self.client.post('/api/canvas-trash/'+record['trash_id']+'/restore',headers=self.headers).status_code)
        self.assertEqual(1,len(self.items()))


class GeneratedTrashTests(TrashTests):
    def configure_ns(self,ns):
        ns['PURGEABLE']={'FAILED','COMPLETED_UNREVIEWED'}
        self.purged=[]
        def purge(job,owner):
            self.purged.append(job);self.jobs[job]['purged_at']=1
            return {'ok':True}
        ns['purge_owned_job']=purge

    def test_generation_runs_are_purged_and_other_board_reference_blocks(self):
        job=uid();self.jobs[job]={'id':job,'owner':'alice','state':'COMPLETED_UNREVIEWED','purged_at':None}
        from canvas_store import Store
        store=Store(self.root/'data/canvases.sqlite3')
        run,_=store.claim('alice',self.board['id'],self.node['id'],uid(),'fixture');store.finish(run['token'],job)
        token=self.move().json()['trash_id']
        graph={'title':'shared','nodes':[dict(self.node,id=uid(),job_id=job)],'edges':[]}
        other=self.client.post('/api/canvases',headers=self.headers,json=graph).json()
        self.assertEqual(409,self.client.post('/api/canvas-trash/purge',headers=self.headers,json={'ids':[token]}).status_code)
        with self.assertRaises(Exception):self.ns['purge_owned_job'](job,'alice')
        second=self.client.post('/api/canvases/'+other['id']+'/trash',headers=self.headers,json={'revision':1,'node_ids':[graph['nodes'][0]['id']],'request_id':uid()}).json()['trash_id']
        result=self.client.post('/api/canvas-trash/purge',headers=self.headers,json={'ids':[token,second]})
        self.assertEqual(200,result.status_code,result.text);self.assertEqual([],result.json()['failed']);self.assertEqual([job],self.purged)
        self.assertEqual([],store.runs('alice',self.board['id']))
