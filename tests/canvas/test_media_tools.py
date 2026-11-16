import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"open_studio/_canvas"))
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import test_routes
from canvas_media_tools import process,number,probe


class MediaRoutesTests(test_routes.RouteTests):
    def test_media_ownership_csrf_and_files(self):
        job=test_routes.uid();self.jobs[job]={'id':job,'owner':'alice','state':'COMPLETED_UNREVIEWED','payload':json.dumps({'kind':'video'})}
        source=self.root/job;source.mkdir();(source/'final.mp4').write_bytes(b'fixture')
        value=self.board['document'];value['nodes'][0].update(kind='video',job_id=job)
        response=self.client.put('/api/canvases/'+self.board['id'],headers=self.headers,json={'revision':1,'document':value});self.assertEqual(response.status_code,200,response.text)
        endpoint='/api/canvases/'+self.board['id']+'/video-tools';body={'node_id':self.node['id'],'action':'audio','options':{}}
        self.assertEqual(403,self.client.post(endpoint,headers={'authorization':'alice'},json=body).status_code)
        self.assertEqual(404,self.client.post(endpoint,headers={'authorization':'bob','x-csrf-token':'csrf'},json=body).status_code)
        def fake(_source,folder,action,options):
            self.assertEqual(_source,source/'final.mp4');folder.mkdir(parents=True);(folder/'audio.wav').write_bytes(b'RIFFfixture');return {'has_audio':True},['audio.wav']
        with patch('canvas_media_tools.process',side_effect=fake):
            result=self.client.post(endpoint,headers=self.headers,json=body)
            self.assertEqual(result.status_code,200,result.text)
        url=result.json()['files'][0]['url'];self.assertEqual(b'RIFFfixture',self.client.get(url,headers=self.headers).content)
        self.assertEqual(404,self.client.get(url,headers={'authorization':'bob'}).status_code)
        self.assertEqual(404,self.client.get(url.replace('audio.wav','credentials.json'),headers=self.headers).status_code)
        self.assertEqual(422,self.client.post(endpoint,headers=self.headers,json={**body,'action':'shell','options':{'command':'echo unsafe'}}).status_code)
        self.assertEqual(0,len(self.created))


class MediaCPUIntegrationTests(unittest.TestCase):
    def test_bounds(self):
        for value in [True,float('nan'),float('inf'),-1,500,'1']:
            with self.assertRaises(ValueError):number(value,0,100)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg is required for CPU integration')
    def test_real_cpu_derivatives(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i','color=c=blue:s=64x64:r=12:d=1','-f','lavfi','-i','sine=duration=1','-c:v','libx264','-pix_fmt','yuv420p','-shortest',str(source)],capture_output=True,check=True,timeout=20)
            for action,options,name in [('frame',{'time':.25},'frame.png'),('audio',{},'audio.wav'),('mute',{},'silent-video.mp4'),('crop_subtitles',{'bottom':.15},'cropped-video.mp4'),('interpolate',{'fps':30},'interpolated-video.mp4')]:
                target=root/action;info,files=process(source,target,action,options)
                self.assertEqual(files,[name]);self.assertTrue((target/name).stat().st_size>50)
                self.assertTrue(info['has_audio'])
            self.assertFalse(probe(root/'mute/silent-video.mp4')['has_audio'])
            self.assertLess(probe(root/'crop_subtitles/cropped-video.mp4')['height'],64)
            self.assertEqual(probe(root/'interpolate/interpolated-video.mp4')['fps'],30)
            with self.assertRaises(ValueError):process(source,root/'bad','frame',{'time':999})


if __name__=='__main__':unittest.main()
