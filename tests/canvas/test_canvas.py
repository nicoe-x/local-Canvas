import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"open_studio/_canvas"))
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from canvas_store import Store, Conflict, document, fingerprint
from canvas_store import validate_stage


def uid():
    return uuid.uuid4().hex


def node(kind="image"):
    return dict(id=uid(), kind=kind, x=20, y=50, title="测试", text="白色陶瓷杯", settings={})


class CanvasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "canvases.sqlite3")
        self.value = dict(title="私人画布", nodes=[node()], edges=[])
        self.board = self.store.create("alice", self.value)

    def test_zoom_800_percent_persists_and_out_of_range_rejected(self):
        value={**self.value,'viewport':{'x':0,'y':0,'zoom':8}}
        saved=self.store.save('alice',self.board['id'],1,value)
        self.assertEqual(8,self.store.get('alice',saved['id'])['document']['viewport']['zoom'])
        for zoom in [8.01,.149,True,float('inf')]:
            value['viewport']['zoom']=zoom
            with self.assertRaises(ValueError):document(value)

    def test_owner_isolation(self):
        self.assertEqual([], self.store.list("bob"))
        with self.assertRaises(KeyError):
            self.store.get("bob", self.board["id"])
        with self.assertRaises(Conflict):
            self.store.save("bob", self.board["id"], 1, self.value)

    def test_durable_content_and_revision(self):
        self.value["nodes"][0]["x"] = 180
        saved = self.store.save("alice", self.board["id"], 1, self.value)
        self.assertEqual(2, saved["revision"])
        restored = Store(self.store.path).get("alice", self.board["id"])
        self.assertEqual(180, restored["document"]["nodes"][0]["x"])
        with self.assertRaises(Conflict):
            self.store.save("alice", self.board["id"], 1, self.value)

    def test_cycle_duplicate_and_foreign_edges(self):
        a, b = node(), node()
        self.value["nodes"] = [a,b]
        for edges in [[dict(source=a["id"],target=a["id"])],
                      [dict(source=a["id"],target=b["id"]),dict(source=b["id"],target=a["id"])],
                      [dict(source=a["id"],target=uid())],
                      [dict(source=a["id"],target=b["id"])]*2]:
            self.value["edges"] = edges
            with self.assertRaises(ValueError):
                document(self.value)

    def test_untrusted_paths_owner_and_nan_rejected(self):
        for key, value in [("owner","bob"),("output_path","/tmp/test")]:
            with self.assertRaises(ValueError):
                document({**self.value,key:value})
        for value in [float("nan"),float("inf"),True,100001]:
            self.value["nodes"][0]["x"] = value
            with self.assertRaises(ValueError):
                document(self.value)

    def test_attempts_and_idempotency(self):
        key, nid, token = self.board["id"], self.value["nodes"][0]["id"], uid()
        first, claimed = self.store.claim("alice",key,nid,token,"v1")
        self.assertTrue(claimed)
        same, claimed = self.store.claim("alice",key,nid,token,"v1")
        self.assertFalse(claimed)
        with self.assertRaises(Conflict):
            self.store.claim("alice",key,nid,uid(),"v1")
        self.store.finish(token, uid())
        second = uid()
        self.store.claim("alice",key,nid,second,"v1")
        self.store.finish(second, uid())
        for _ in range(10):
            token=uid()
            run,claimed=self.store.claim("alice",key,nid,token,"v1")
            self.assertTrue(claimed)
            self.store.finish(token,uid())
            replay,claimed=self.store.claim("alice",key,nid,token,"v1")
            self.assertFalse(claimed)
            self.assertEqual(token,replay['token'])
        self.store.claim("alice",key,nid,uid(),"v2")

    def test_rejected_validation_does_not_count(self):
        key,nid,token = self.board["id"],self.value["nodes"][0]["id"],uid()
        self.store.claim("alice",key,nid,token,"v1")
        self.store.finish(token)
        self.assertTrue(self.store.claim("alice",key,nid,uid(),"v1")[1])

    def test_token_cannot_cross_boards(self):
        token = uid()
        self.store.claim("alice",self.board["id"],self.value["nodes"][0]["id"],token,"v1")
        other=self.store.create("bob",self.value)
        with self.assertRaises(Conflict):
            self.store.claim("bob",other["id"],self.value["nodes"][0]["id"],token,"v1")

    def test_fingerprint_includes_refs_but_not_coordinates(self):
        self.assertEqual(fingerprint({"prompt":"a","refs":[1,2]}),fingerprint({"refs":[1,2],"prompt":"a"}))
        self.assertNotEqual(fingerprint({"prompt":"a","refs":[1,2]}),fingerprint({"prompt":"a","refs":[2,1]}))


    def test_scene_roundtrip_and_bounds(self):
        stage={'actors':[{'id':uid(),'kind':'person','x':-.9,'z':0,'rotation':20,'height':1.75,'color':'#6b73b7'}],
               'camera':{'position':[4,2.5,6],'target':[0,1,0],'fov':40}}
        value=dict(title='3D导演台',nodes=[{**node('stage3d'),'settings':{'stage3d':stage}}],edges=[])
        stored=self.store.create('alice',value)
        self.assertEqual(stage,stored['document']['nodes'][0]['settings']['stage3d'])
        stage['actors'][0]['height']=float('nan')
        with self.assertRaises(ValueError):validate_stage(stage)
        stage['actors'][0]['height']=1.75;stage['camera']['target']=[4,2.5,6]
        with self.assertRaises(ValueError):validate_stage(stage)

    def test_reverse_prompt_storage_is_bounded(self):
        value=dict(title='反推',nodes=[{**node('reverse'),'settings':{'reverse_prompts':{'zh':'中文提示词','en':'a cup'},'reverse_language':'zh'}}],edges=[])
        self.store.create('alice',value)
        value['nodes'][0]['settings']['reverse_prompts']['zh']='x'*50001
        with self.assertRaises(ValueError):document(value)


if __name__ == "__main__":
    unittest.main()
