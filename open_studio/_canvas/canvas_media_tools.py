"""Owner-scoped CPU derivatives; no browser paths, shell commands or GPU submissions."""
import asyncio
import json
import math
from pathlib import Path
import subprocess
import uuid
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from canvas_store import checked_id


def number(value,low,high):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError('参数超出允许范围')
    return value


def probe(path):
    result=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=15,check=True)
    data=json.loads(result.stdout);video=next(s for s in data['streams'] if s['codec_type']=='video')
    parts=video.get('avg_frame_rate','24/1').split('/');fps=float(parts[0])/max(float(parts[-1]),1)
    if not math.isfinite(fps) or fps<=0 or fps>480:raise ValueError('无法读取有效的视频帧率')
    return {'width':int(video['width']),'height':int(video['height']),'fps':fps,'duration':float(data['format']['duration']),'has_audio':any(s['codec_type']=='audio' for s in data['streams'])}


def process(source,folder,action,options):
    info=probe(source)
    if action=='info':return info,[]
    if info['width']*info['height']>16_000_000:raise ValueError('视频分辨率超过处理范围')
    arguments=['ffmpeg','-v','error','-nostdin','-y','-threads','2','-filter_threads','1']
    if action=='frame':
        if set(options)-{'time'}:raise ValueError('截图参数无效')
        time=number(options.get('time',0),0,max(0,info['duration']-.001))
        filename='frame.png';arguments+=['-ss',str(time),'-i',str(source),'-frames:v','1','-update','1']
    else:
        if info['duration']>90:raise ValueError('本地视频处理目前支持90秒以内的片段')
        arguments+=['-i',str(source)]
        if action=='audio':
            if options:raise ValueError('音频导出参数无效')
            if not info['has_audio']:raise ValueError('此视频没有音轨')
            filename='audio.wav';arguments+=['-vn','-acodec','pcm_s16le']
        elif action=='mute':
            if options:raise ValueError('视频分离参数无效')
            filename='silent-video.mp4';arguments+=['-map','0:v:0','-c:v','copy','-an','-movflags','+faststart']
        elif action=='crop_subtitles':
            if set(options)-{'bottom'}:raise ValueError('字幕区域参数无效')
            bottom=number(options.get('bottom',.15),.02,.35)
            height=max(2,int(info['height']*(1-bottom))//2*2)
            filename='cropped-video.mp4';arguments+=['-vf',f'crop=iw:{height}:0:0','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-movflags','+faststart']
        elif action=='interpolate':
            if set(options)-{'fps'}:raise ValueError('补帧参数无效')
            fps=options.get('fps',30)
            if isinstance(fps,bool) or fps not in [30,60]:raise ValueError('补帧仅支持30或60fps')
            if info['duration']>15:raise ValueError('本地光流补帧支持15秒以内片段')
            filename='interpolated-video.mp4';arguments+=['-vf',f"scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir",'-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-movflags','+faststart']
        else:raise ValueError('未知的视频处理功能')
    folder.mkdir(parents=True,mode=0o700);output=folder/filename
    temporary=output.with_name(output.stem+'.partial'+output.suffix)
    try:
        subprocess.run(arguments+[str(temporary)],stdin=subprocess.DEVNULL,capture_output=True,timeout=150,check=True)
        if not temporary.is_file() or not 0<temporary.stat().st_size<=512*1024**2:raise ValueError('结果文件无效或超过512MB')
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return info,[filename]


def register(ns,store):
    app=ns['app'];slots=asyncio.Semaphore(2)
    def owner(request,write=False):return ns['authenticate'](request,sensitive=True,write=write)['id']
    def folder(actor,key):
        store.get(actor,key)
        return ns['MATERIAL']/'canvas'/ns['user_folder'](actor)/checked_id(key)/'tools'

    @app.get('/api/canvases/{key}/result-capabilities')
    def capabilities(key:str,request:Request):
        try:folder(owner(request),key)
        except (KeyError,ValueError):raise HTTPException(404,'画布不存在') from None
        return {'local':['frame','audio','mute','crop_subtitles','interpolate'],
                'external':{'layer_separation':False,'panorama':False,'motion_capture':False},
                'external_status':'等待配置外部服务账号与接口'}

    @app.post('/api/canvases/{key}/video-tools')
    async def video_tool(key:str,request:Request):
        actor=owner(request,True)
        try:
            base=folder(actor,key);board=store.get(actor,key);body=await request.json()
            if not isinstance(body,dict) or set(body)-{'node_id','action','options'}:raise ValueError('处理请求无效')
            if body.get('action') not in ['info','frame','audio','mute','crop_subtitles','interpolate']:raise ValueError('此功能尚未接入')
            if not isinstance(body.get('options',{}),dict):raise ValueError('处理参数无效')
            node=next(n for n in board['document']['nodes'] if n['id']==checked_id(body['node_id']))
            job=node.get('job_id') or next((r['job_id'] for r in reversed(store.runs(actor,key)) if r['node_id']==node['id'] and r.get('job_id')),None)
            if not job:raise ValueError('节点还没有视频结果')
            row=ns['owned_job'](job,actor)
            if row['state']!='COMPLETED_UNREVIEWED' or json.loads(row['payload']).get('kind')!='video':raise ValueError('请选择已完成的视频结果')
            source=ns['output_folder'](row)/'final.mp4'
            if not source.is_file() or source.is_symlink() or source.stat().st_size>1024**3:raise ValueError('视频文件不存在或超过1GB')
            operation=uuid.uuid4().hex;target=base/operation
            async with slots:
                info,files=await asyncio.to_thread(process,source,target,body['action'],body.get('options',{}))
            return {'state':'COMPLETED_UNREVIEWED','info':info,'files':[{'name':name,'url':f'/api/canvases/{key}/tool-files/{operation}/{name}'} for name in files]}
        except (KeyError,StopIteration):raise HTTPException(404,'画布或素材不存在') from None
        except (ValueError,TypeError) as exc:raise HTTPException(422,str(exc)) from None
        except subprocess.TimeoutExpired:raise HTTPException(504,'本地处理超时，请缩短片段后重试') from None
        except subprocess.CalledProcessError:raise HTTPException(422,'视频文件无法完成此处理，请检查音轨或编码') from None

    @app.get('/api/canvases/{key}/tool-files/{operation}/{name}')
    def result_file(key:str,operation:str,name:str,request:Request):
        try:
            base=folder(owner(request),key);parent=base/checked_id(operation);path=parent/name
            if name not in ['frame.png','audio.wav','silent-video.mp4','cropped-video.mp4','interpolated-video.mp4'] or parent.is_symlink() or path.is_symlink() or not path.is_file():raise ValueError()
        except (ValueError,KeyError):raise HTTPException(404,'文件不存在') from None
        return FileResponse(path,filename=name,headers={'Cache-Control':'private, no-store'})
