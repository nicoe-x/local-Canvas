import asyncio
import contextlib
import json
from pathlib import Path
import subprocess
import time
from urllib.parse import urlsplit
from PIL import Image
import httpx
from .workflows import render
from .comfy import Comfy


class Engine:
    def __init__(self,store,comfy):self.store=store;self.comfy=comfy;self.task=None

    def start(self):
        with self.store.db() as db:
            # A process crash between POST and recording prompt_id is ambiguous.
            db.execute("UPDATE jobs SET state='NEEDS_ATTENTION',stage='提交结果待核对，请勿重复生成' WHERE state='STARTING' AND prompt_id IS NULL")
        self.task=asyncio.create_task(self.loop())

    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):await self.task

    def folder(self,row):return self.store.root/'jobs'/row['owner']/row['id']

    async def loop(self):
        while True:
            try:
                with self.store.db() as db:job=db.execute("SELECT * FROM jobs WHERE state IN ('QUEUED','RUNNING') AND deleted_at IS NULL ORDER BY CASE state WHEN 'RUNNING' THEN 0 ELSE 1 END,created LIMIT 1").fetchone()
                if not job:await asyncio.sleep(1);continue
                await self.run(dict(job))
            except asyncio.CancelledError:raise
            except Exception:
                # Do not put tokens, remote response bodies or prompts into logs.
                await asyncio.sleep(2)

    def client(self,job):
        snapshot=json.loads(job['payload']).get('connection')
        if not snapshot:return self.comfy
        class Frozen:
            def read(self):return {'comfy':snapshot}
        return Comfy(Frozen(),self.comfy.transport)

    async def watch(self,job):
        try:
            from websockets.asyncio.client import connect
            config=self.client(job).connection();parts=urlsplit(config['url']);url=('wss' if parts.scheme=='https' else 'ws')+'://'+parts.netloc+'/ws?clientId='+job['id']
            import ssl
            tls=None
            if parts.scheme=='https':tls=ssl.create_default_context() if config.get('verify_tls',True) else ssl._create_unverified_context()
            async with connect(url,additional_headers=config.get('headers',{}),ssl=tls,open_timeout=5,max_size=2*1024**2,proxy=None) as socket:
                executing=False
                async for raw in socket:
                    if not isinstance(raw,str):continue
                    event=json.loads(raw);data=event.get('data',{})
                    if event.get('type')=='executing':executing=data.get('prompt_id')==job.get('prompt_id')
                    if event.get('type')=='progress' and (data.get('prompt_id')==job.get('prompt_id') or executing):
                        maximum=data.get('max',0);value=data.get('value',0)
                        if isinstance(value,(int,float)) and isinstance(maximum,(int,float)) and maximum>0:
                            self.store.update(job['id'],progress=max(0,min(100,round(100*value/maximum))),stage=f'当前采样阶段 {value}/{maximum}')
        except Exception:
            # HTTP history polling remains authoritative if WebSocket is unavailable.
            return

    async def run(self,job):
        key=job['id'];payload=json.loads(job['payload']);folder=self.folder(job);comfy=self.client(job)
        if job['state']=='QUEUED':
            self.store.update(key,state='STARTING',stage='准备参考素材与工作流',progress=0)
            try:
                references=[]
                for index in range(payload.pop('reference_count',0)):
                    references.append(await comfy.upload((folder/f'ref-{index}.jpg').read_bytes(),f'openstudio-{key}-{index}.jpg'))
                graph=render(payload['workflow'],payload,references)
                for node in graph.values():
                    if 'filename_prefix' in node['inputs']:node['inputs']['filename_prefix']='OpenStudio/'+key+'/result'
            except Exception:
                self.store.update(key,state='FAILED',stage='参考素材或工作流准备失败，请核对连接与参数',detail={'error':{'code':'COMFY_PREPARE_FAILED'}});return
            # Persist STARTING before POST. Never retry POST after uncertain failure.
            try:
                result=await comfy.request('POST','/prompt',json={'prompt':graph,'client_id':key,'extra_data':{'open_studio_job':key}})
                prompt=result.get('prompt_id')
                if not isinstance(prompt,str) or not prompt:raise ValueError('Missing prompt ID')
            except httpx.HTTPStatusError as error:
                if error.response.status_code in (400,422):self.store.update(key,state='FAILED',stage='ComfyUI 拒绝了工作流，请检查节点、模型和参数',detail={'error':{'code':'COMFY_VALIDATION_FAILED'}})
                else:self.store.update(key,state='NEEDS_ATTENTION',stage='提交结果待核对，请勿重复生成',detail={'error':{'code':'COMFY_RESULT_UNCERTAIN'}})
                return
            except Exception:
                self.store.update(key,state='NEEDS_ATTENTION',stage='提交结果待核对，请勿重复生成',detail={'error':{'code':'COMFY_RESULT_UNCERTAIN'}});return
            job['prompt_id']=prompt;self.store.update(key,prompt_id=prompt,state='RUNNING',stage='已进入 ComfyUI 队列')
        watch=asyncio.create_task(self.watch(job))
        misses=0
        try:
            while True:
                try:history=await comfy.request('GET','/history/'+job['prompt_id']);entry=history.get(job['prompt_id'])
                except Exception:
                    misses+=1
                    if misses>=12:self.store.update(key,state='NEEDS_ATTENTION',stage='ComfyUI 暂不可达，恢复连接后请核对结果',detail={'error':{'code':'COMFY_CONNECTION_LOST'}});return
                    await asyncio.sleep(5);continue
                misses=0
                if entry:
                    if entry.get('status',{}).get('status_str')=='error':self.store.update(key,state='FAILED',stage='ComfyUI 执行失败，请在 ComfyUI 查看节点错误',detail={'error':{'code':'COMFY_EXECUTION_FAILED'}});return
                    if entry.get('status',{}).get('completed') or entry.get('outputs'):
                        try:await self.collect(job,entry)
                        except Exception:self.store.update(key,state='FAILED',stage='结果下载或解码失败，可重新核对后台结果',detail={'error':{'code':'COMFY_OUTPUT_FAILED'}})
                        return
                await asyncio.sleep(2)
        finally:
            watch.cancel()
            with contextlib.suppress(asyncio.CancelledError):await watch

    async def collect(self,job,entry):
        folder=self.folder(job);folder.mkdir(parents=True,exist_ok=True,mode=0o700);artifacts=[]
        for output in entry.get('outputs',{}).values():
            for category in ('images','videos','gifs','audio'):
                for descriptor in output.get(category,[]):
                    if not isinstance(descriptor,dict):continue
                    ext=Path(descriptor.get('filename','')).suffix.lower()
                    if ext not in {'.png','.jpg','.jpeg','.webp','.mp4','.webm','.gif','.wav','.mp3'}:continue
                    if len(artifacts)>=32:raise ValueError('Too many outputs')
                    name=f'artifact-{len(artifacts):02d}'+ext;temporary=folder/(name+'.partial')
                    await self.client(job).download(descriptor,temporary);temporary.replace(folder/name);artifacts.append(name)
        payload=json.loads(job['payload']);kind=payload.get('kind','image')
        images=[n for n in artifacts if Path(n).suffix in {'.png','.jpg','.jpeg','.webp'}]
        videos=[n for n in artifacts if Path(n).suffix in {'.mp4','.webm','.gif'}]
        if kind=='image':
            if not images:raise ValueError('No image result')
            with Image.open(folder/images[0]) as image:image.convert('RGB').save(folder/'final.png')
        else:
            if not videos:raise ValueError('No video result')
            source=folder/videos[0]
            if source.suffix=='.mp4':
                import shutil
                shutil.copyfile(source,folder/'final.mp4')
            else:await asyncio.to_thread(subprocess.run,['ffmpeg','-v','error','-nostdin','-y','-i',str(source),'-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(folder/'final.mp4')],capture_output=True,check=True,timeout=300)
            await asyncio.to_thread(subprocess.run,['ffmpeg','-v','error','-nostdin','-y','-i',str(folder/'final.mp4'),'-frames:v','1','-update','1',str(folder/'final.png')],capture_output=True,check=True,timeout=30)
        self.store.update(job['id'],state='COMPLETED_UNREVIEWED',stage='生成完成 · 未审片',progress=100,detail={'artifacts':artifacts,'reviewed':False})

    async def reconcile(self,job):
        if job['prompt_id']:
            self.store.update(job['id'],state='RUNNING',stage='恢复后台结果核对');return True
        comfy=self.client(job);queue=await comfy.request('GET','/queue');history=await comfy.request('GET','/history',params={'max_items':200})
        prompts=[p for key in ['queue_running','queue_pending'] for p in queue.get(key,[])]+[v.get('prompt',[]) for v in history.values()]
        for prompt in prompts:
            if len(prompt)>3 and isinstance(prompt[3],dict) and prompt[3].get('open_studio_job')==job['id']:
                self.store.update(job['id'],prompt_id=prompt[1],state='RUNNING',stage='已找到原提交，继续核对');return True
        return False
