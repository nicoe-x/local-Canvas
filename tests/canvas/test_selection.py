import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"open_studio/_canvas"))
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import test_routes
from canvas_store import document,Store


class GroupSchemaTests(unittest.TestCase):
    def test_round_trip_and_invalid_memberships(self):
        a,b=test_routes.uid(),test_routes.uid();g=test_routes.uid()
        value={'title':'group','nodes':[{'id':a,'kind':'note','x':0,'y':0},{'id':b,'kind':'note','x':10,'y':10}],'edges':[]}
        self.assertNotIn('groups',document(value))
        value['groups']=[{'id':g,'title':'参考图','node_ids':[a,b]}]
        with tempfile.TemporaryDirectory() as root:
            store=Store(Path(root)/'canvas.sqlite3');saved=store.create('alice',value)
            self.assertEqual(saved['document']['groups'],value['groups'])
            saved=store.save('alice',saved['id'],saved['revision'],saved['document'])
            self.assertEqual(saved['document']['groups'],value['groups'])
        for groups in [[{'id':g,'title':'x','node_ids':[a,a]}],[{'id':g,'title':'x','node_ids':[test_routes.uid()]}],
                       [{'id':g,'title':'x','node_ids':[a]},{'id':test_routes.uid(),'title':'y','node_ids':[a]}],
                       [{'id':g,'title':'x','node_ids':[a],'owner':'bob'}]]:
            with self.subTest(groups=groups),self.assertRaises(ValueError):document({**value,'groups':groups})


class SelectionDownloadTests(test_routes.RouteTests):
    def test_selection_archive_owner_paths_and_cleanup(self):
        image,video,note=[test_routes.uid() for _ in range(3)];image_job,video_job=test_routes.uid(),test_routes.uid()
        for job,kind,content in [(image_job,'image',b'PNGfixture'),(video_job,'video',b'MP4fixture')]:
            self.jobs[job]={'id':job,'owner':'alice','state':'COMPLETED_UNREVIEWED','payload':json.dumps({'kind':kind})}
            folder=self.root/job;folder.mkdir();(folder/('final.png' if kind=='image' else 'final.mp4')).write_bytes(content)
        doc=self.board['document'];doc['nodes'] += [dict(id=image,kind='image',x=10,y=10,title='../unsafe/name',job_id=image_job),dict(id=video,kind='video',x=20,y=20,title='视频',job_id=video_job),dict(id=note,kind='note',x=30,y=30,title='提示词',text='我的文本')]
        response=self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':doc});self.assertEqual(response.status_code,200,response.text)
        endpoint='/api/canvases/'+self.board['id']+'/download-selection';body={'node_ids':[image,video,note,self.node['id']]}
        self.assertEqual(403,self.client.post(endpoint,headers={'authorization':'alice'},json=body).status_code)
        self.assertEqual(404,self.client.post(endpoint,headers={'authorization':'bob','x-csrf-token':'csrf'},json=body).status_code)
        response=self.client.post(endpoint,headers=self.headers,json=body);self.assertEqual(response.status_code,200,response.text)
        result=response.json();self.assertEqual((result['files'],result['skipped']),(3,1))
        self.assertEqual(404,self.client.get(result['url'],headers={'authorization':'bob'}).status_code)
        download=self.client.get(result['url'],headers=self.headers);self.assertEqual(download.status_code,200)
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            names=archive.namelist();self.assertEqual(len(names),4)
            self.assertFalse(any('/' in name or '\\' in name for name in names))
            self.assertEqual(archive.read(next(n for n in names if n.endswith('.txt'))).decode(),'我的文本')
        self.assertEqual(404,self.client.get(result['url'],headers=self.headers).status_code)
        self.assertEqual([],list((self.root/'data/canvas-downloads').iterdir()))
        self.assertEqual(422,self.client.post(endpoint,headers=self.headers,json={'node_ids':[image,image]}).status_code)
        self.assertEqual(422,self.client.post(endpoint,headers=self.headers,json={**body,'output_path':'/public'}).status_code)
        self.assertEqual(0,len(self.created))


if __name__=='__main__':unittest.main()
