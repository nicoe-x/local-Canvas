"""Bounded, verified ComfyUI discovery and HTTP adapter. Never submits while scanning."""
import asyncio
import ipaddress
import json
from pathlib import PurePosixPath
import socket
import httpx
from .config import endpoint,private_address


class Comfy:
    def __init__(self,config,transport=None):self.config=config;self.transport=transport

    def connection(self):
        value=self.config.read().get('comfy')
        if not value:raise ValueError('尚未连接 ComfyUI，请在连接设置中选择实例')
        endpoint(value['url'])
        return value

    async def request(self,method,path,**kwargs):
        config=self.connection()
        async with httpx.AsyncClient(base_url=config['url'],headers=config.get('headers',{}),verify=config.get('verify_tls',True),timeout=20,trust_env=False,follow_redirects=False,transport=self.transport) as client:
            response=await client.request(method,path,**kwargs);response.raise_for_status();return response.json()

    async def inspect(self,url,headers=None,verify=True):
        url=endpoint(url)
        async with httpx.AsyncClient(base_url=url,headers=headers or {},verify=verify,timeout=3,trust_env=False,follow_redirects=False,transport=self.transport) as client:
            response=await client.get('/system_stats')
            if response.status_code in (401,403):return {'url':url,'auth_required':True,'healthy':False}
            response.raise_for_status();stats=response.json()
            if not isinstance(stats,dict) or not isinstance(stats.get('devices'),list) or not isinstance(stats.get('system'),dict):raise ValueError('该地址不是可验证的 ComfyUI 服务')
            async with client.stream('GET','/object_info') as reply:
                reply.raise_for_status();raw=bytearray()
                async for chunk in reply.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw)>32*1024**2:raise ValueError('节点元数据超过32MB，请手动检查服务')
            info=json.loads(raw)
            if not isinstance(info,dict) or not any(isinstance(v,dict) and 'input' in v for v in info.values()):raise ValueError('缺少 ComfyUI 节点元数据')
        models={}
        for node,fields in {'CheckpointLoaderSimple':['ckpt_name'],'UNETLoader':['unet_name'],'CLIPLoader':['clip_name'],'DualCLIPLoader':['clip_name1','clip_name2'],'VAELoader':['vae_name'],'LoraLoader':['lora_name']}.items():
            for field in fields:
                choices=info.get(node,{}).get('input',{}).get('required',{}).get(field,[])
                if choices and isinstance(choices[0],list):models[node+'.'+field]=[str(v) for v in choices[0]]
        return {'url':url,'healthy':True,'auth_required':False,'devices':[str(d.get('name','')) for d in stats['devices']], 'nodes':sorted(info),'models':models,'version':str(stats['system'].get('comfyui_version','unknown'))}

    async def scan(self,cidr=None,ports=None):
        ports=ports or [8188,8189,8190,8191]
        if not isinstance(ports,list) or not 1<=len(ports)<=8 or any(type(p)!=int or not 1<=p<=65535 for p in ports):raise ValueError('请选择最多8个有效端口')
        if cidr:
            network=ipaddress.ip_network(cidr,strict=False)
            if network.version!=4 or network.num_addresses>256 or not all(private_address(ip) for ip in [network.network_address,network.broadcast_address]):raise ValueError('仅扫描用户指定的本机或私有网段，范围最多/24')
            hosts=[str(ip) for ip in network.hosts()]
        else:
            hosts=['127.0.0.1']
            try:
                if all(private_address(v[4][0]) for v in socket.getaddrinfo('host.docker.internal',8188,type=socket.SOCK_STREAM)):hosts.append('host.docker.internal')
            except OSError:pass
        semaphore=asyncio.Semaphore(24)
        async def probe(host,port):
            async with semaphore:
                try:return await self.inspect(f'http://{host}:{port}')
                except (httpx.HTTPError,ValueError,OSError,json.JSONDecodeError):return None
        result=await asyncio.gather(*(probe(h,p) for h in hosts for p in ports))
        return [r for r in result if r]

    async def upload(self,raw,name):
        value=await self.request('POST','/upload/image',files={'image':(name,raw,'image/jpeg')},data={'type':'input','overwrite':'false'})
        filename=value.get('name','');subfolder=value.get('subfolder','')
        if not filename or '/' in filename or '\\' in filename or '..' in PurePosixPath(subfolder).parts:raise ValueError('ComfyUI 返回的上传路径无效')
        return (subfolder.rstrip('/')+'/' if subfolder else '')+filename

    async def download(self,descriptor,target):
        name=descriptor.get('filename','');folder=descriptor.get('subfolder','')
        if not name or '/' in name or '\\' in name or '..' in PurePosixPath(folder).parts or descriptor.get('type','output')!='output':raise ValueError('生成结果路径无效')
        config=self.connection();total=0
        async with httpx.AsyncClient(base_url=config['url'],headers=config.get('headers',{}),verify=config.get('verify_tls',True),timeout=90,trust_env=False,follow_redirects=False,transport=self.transport) as client:
            async with client.stream('GET','/view',params={'filename':name,'subfolder':folder,'type':'output'}) as response:
                response.raise_for_status()
                with target.open('wb') as stream:
                    async for chunk in response.aiter_bytes():
                        total+=len(chunk)
                        if total>512*1024**2:raise ValueError('单个生成文件超过512MB')
                        stream.write(chunk)
        if not total:raise ValueError('ComfyUI 返回了空文件')
