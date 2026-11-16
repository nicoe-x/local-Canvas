import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"open_studio/_canvas"))
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from canvas_store import Store, Conflict
import test_routes


class ProjectStoreTests(unittest.TestCase):
    def test_legacy_migration_and_move_preserves_graph_and_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'old.sqlite3'
            key='1'*32
            graph={'title':'旧画布','nodes':[{'id':'2'*32,'kind':'note','text':'原内容'}],'edges':[]}
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE canvases (id TEXT PRIMARY KEY,owner TEXT NOT NULL,revision INTEGER NOT NULL,document TEXT NOT NULL,updated REAL NOT NULL)')
                db.execute('INSERT INTO canvases VALUES (?,?,1,?,0)',(key,'alice',json.dumps(graph)))
            db.close()
            store=Store(path)
            self.assertIsNone(store.get('alice',key)['project_id'])
            project=store.create_project('alice','项目 A')
            run,_=store.claim('alice',key,'2'*32,'3'*32,'fingerprint')
            moved=store.move('alice',key,project['id'],1)
            self.assertEqual(graph,moved['document'])
            self.assertEqual(1,len(store.runs('alice',key)))
            self.assertEqual([],store.list('alice','unclassified'))
            self.assertEqual(key,store.list('alice',project['id'])[0]['id'])
            with self.assertRaises(Conflict):store.move('alice',key,None,1)
            with self.assertRaises(KeyError):store.create('bob',{'title':'bad','nodes':[],'edges':[]},project['id'])
            with self.assertRaises(ValueError):store.create_project('alice','项目 A')
            self.assertEqual([],store.projects('bob')['items'])
            store.move('alice',key,None,2)
            self.assertEqual(key,store.list('alice','unclassified')[0]['id'])


class ProjectRouteTests(test_routes.RouteTests):
    def test_projects_csrf_ownership_filter_and_snapshot(self):
        client=self.client;headers=self.headers
        self.assertEqual(403,client.post('/api/canvas-projects',headers={'authorization':'alice'},json={'name':'A'}).status_code)
        self.assertEqual(422,client.post('/api/canvas-projects',headers=headers,json={'name':'A','owner':'bob'}).status_code)
        project=client.post('/api/canvas-projects',headers=headers,json={'name':'A'}).json()
        key=project['id']
        other={'authorization':'bob','x-csrf-token':'csrf'}
        self.assertEqual(404,client.get('/api/canvases?project_id='+key,headers=other).status_code)
        self.assertEqual(404,client.put('/api/canvas-projects/'+key,headers=other,json={'name':'stolen'}).status_code)
        response=client.post('/api/canvases',headers=headers,json={'title':'项目画布','nodes':[],'edges':[],'project_id':key})
        self.assertEqual(200,response.status_code,response.text)
        board=response.json()
        self.assertEqual(1,len(client.get('/api/canvases?project_id='+key,headers=headers).json()))
        endpoint='/api/canvases/'+board['id']+'/project'
        self.assertEqual(404,client.put(endpoint,headers=other,json={'project_id':None,'revision':1}).status_code)
        self.assertEqual(200,client.put(endpoint,headers=headers,json={'project_id':None,'revision':1}).status_code)
        self.assertEqual(409,client.put(endpoint,headers=headers,json={'project_id':key,'revision':1}).status_code)
        snapshot=json.loads((self.root/'materials/canvas/alice'/board['id']/'board.json').read_text(encoding='utf8'))
        self.assertIsNone(snapshot['project_id'])
        self.assertEqual(2,snapshot['revision'])
        self.assertEqual([],client.get('/api/canvases?project_id='+key,headers=headers).json())
