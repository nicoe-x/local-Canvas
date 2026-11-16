"""Owner-scoped selection ZIPs, streamed once and removed after download."""
import asyncio
import json
from pathlib import Path
import re
import time
import uuid
import zipfile
from fastapi import HTTPException,Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from canvas_store import checked_id


def safe_title(value):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',value or '素材').strip(' .')[:70] or '素材'


def remove(folder,root):
    if folder.is_symlink() or folder.resolve().parent!=root.resolve():return
    for name in ['archive.zip','meta.json']:
        path=folder/name
        if path.is_file() and not path.is_symlink():path.unlink()
    try:folder.rmdir()
    except OSError:pass


def register(ns,store):
    app=ns['app'];root=ns['DATA']/'canvas-downloads';slots=asyncio.Semaphore(2)
    def owner(request,write=False):return ns['authenticate'](request,sensitive=True,write=write)['id']
    def build(actor,key,ids):
        board=store.get(actor,key);nodes={n['id']:n for n in board['document']['nodes']}
        if not isinstance(ids,list) or not 1<=len(ids)<=200 or len(set(checked_id(i) for i in ids))!=len(ids):raise ValueError('请选择1–200个不同节点')
        if set(ids)-nodes.keys():raise KeyError('选中的节点不存在')
        latest={r['node_id']:r for r in store.runs(actor,key) if r.get('job_id')}
        sources=[];skipped=[];total=0
        for index,ident in enumerate(ids):
            node=nodes[ident];path=None;raw=None;ext=None
            if node.get('media_id'):
                path=ns['MATERIAL']/'canvas'/ns['user_folder'](actor)/key/(checked_id(node['media_id'])+'.jpg');ext='jpg'
            elif node['kind'] in ['note','reverse'] and node.get('text','').strip():raw=node['text'].encode();ext='txt'
            else:
                job=node.get('job_id') or latest.get(ident,{}).get('job_id')
                if job:
                    row=ns['owned_job'](job,actor);kind=json.loads(row['payload']).get('kind')
                    if row['state']=='COMPLETED_UNREVIEWED' and kind in ['image','video']:
                        ext='png' if kind=='image' else 'mp4';path=ns['output_folder'](row)/('final.'+ext)
            if not ext or (path is not None and (not path.is_file() or path.is_symlink())):
                skipped.append({'id':ident,'title':node.get('title',''),'reason':'没有可下载的已完成结果'});continue
            size=path.stat().st_size if path is not None else len(raw)
            if size>512*1024**2:raise ValueError('单个文件超过512MB，请单独下载')
            total+=size
            if total>2*1024**3:raise ValueError('所选文件超过2GB，请分批下载')
            sources.append((f'{index+1:03d}_{safe_title(node.get("title"))}.{ext}',path,raw))
        if not sources:raise ValueError('选中的节点没有已完成结果或文本')
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        for folder in root.iterdir():
            if folder.is_symlink() or not folder.is_dir() or not re.fullmatch('[a-f0-9]{32}',folder.name):continue
            try:
                if json.loads((folder/'meta.json').read_text())['expires']<time.time():remove(folder,root)
            except (OSError,ValueError,KeyError):continue
        token=uuid.uuid4().hex;folder=root/token;folder.mkdir(mode=0o700)
        try:
            with zipfile.ZipFile(folder/'archive.zip','w',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
                for name,path,raw in sources:
                    if path is not None:archive.write(path,name)
                    else:archive.writestr(name,raw)
                archive.writestr('selection.json',json.dumps({'title':board['document']['title'],'nodes':[nodes[i] for i in ids],
                    'edges':[e for e in board['document']['edges'] if e['source'] in ids and e['target'] in ids],
                    'groups':[g for g in board['document'].get('groups',[]) if set(g['node_ids'])<=set(ids)],'skipped':skipped},ensure_ascii=False,indent=2))
            (folder/'meta.json').write_text(json.dumps({'owner':actor,'canvas':key,'expires':time.time()+1800,'name':safe_title(board['document']['title'])+'-选中素材.zip'}))
        except Exception:
            remove(folder,root);raise
        return {'url':f'/api/canvases/{key}/selection-download/{token}','files':len(sources),'skipped':len(skipped)}

    @app.post('/api/canvases/{key}/download-selection')
    async def prepare_download(key:str,request:Request):
        actor=owner(request,True)
        try:
            body=await request.json()
            if not isinstance(body,dict) or set(body)!={'node_ids'}:raise ValueError('下载参数无效')
            async with slots:return await asyncio.to_thread(build,actor,key,body['node_ids'])
        except KeyError:raise HTTPException(404,'画布或选中节点不存在') from None
        except (TypeError,ValueError) as exc:raise HTTPException(422,str(exc)) from None
        except OSError:raise HTTPException(507,'打包失败，请检查源文件或可用存储空间') from None

    @app.get('/api/canvases/{key}/selection-download/{token}')
    def download(key:str,token:str,request:Request):
        actor=owner(request)
        try:
            store.get(actor,key);folder=root/checked_id(token)
            if folder.is_symlink():raise ValueError()
            meta=json.loads((folder/'meta.json').read_text())
            if meta['owner']!=actor or meta['canvas']!=key:raise ValueError()
            if meta['expires']<time.time():remove(folder,root);raise ValueError()
            path=folder/'archive.zip'
            if not path.is_file() or path.is_symlink():raise ValueError()
        except (OSError,ValueError,KeyError):raise HTTPException(404,'下载已过期或不存在，请重新打包') from None
        return FileResponse(path,media_type='application/zip',filename=meta['name'],headers={'Cache-Control':'private, no-store'},background=BackgroundTask(remove,folder,root))
