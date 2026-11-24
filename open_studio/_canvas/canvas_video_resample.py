"""Explicit video-to-video runs; sources and job ownership stay server-resolved."""
import asyncio
import json

from fastapi import HTTPException
from canvas_store import Conflict, checked_id, fingerprint


def validate_settings(value):
    import math
    if not isinstance(value, dict) or set(value) != {'source', 'steps', 'denoise'}:
        raise ValueError('二采参数格式无效')
    checked_id(value['source'])
    if type(value['steps']) is not int or not 1 <= value['steps'] <= 32:
        raise ValueError('二采步数须为1–32')
    strength = value['denoise']
    if type(strength) not in (int, float) or not math.isfinite(strength) or not .05 <= strength <= 1:
        raise ValueError('二采降噪强度须为0.05–1')
    return value


async def generate(ns, store, owner, key, node_id, body, request):
    """Called under the normal canvas submission lock, before image-reference routing."""
    try:
        board = store.get(owner, key)
        node = next(n for n in board['document']['nodes'] if n['id'] == node_id)
        settings = validate_settings(node['settings']['video_resample'])
        if node['kind'] != 'video' or node.get('job_id'):
            raise ValueError('请选择独立的二采视频节点')
        token = checked_id(body.get('token'))
        prior = next((r for r in store.runs(owner, key) if r['token'] == token), None)
        if prior:
            if prior['node_id'] != node_id:
                raise Conflict('提交编号已用于其他节点')
            return prior
        if body.get('revision') != board['revision']:
            raise Conflict('请先保存最新画布再生成')
        inputs = [e['source'] for e in board['document']['edges'] if e['target'] == node_id]
        if inputs != [settings['source']]:
            raise ValueError('二采节点须且只能连接选定的一个视频源，请恢复连线')
        source = next(n for n in board['document']['nodes'] if n['id'] == settings['source'])
        if source['kind'] != 'video':
            raise ValueError('二采来源必须为视频节点')
        source_runs = [r for r in store.runs(owner, key) if r['node_id'] == source['id']]
        job = source.get('job_id') or (source_runs[-1].get('job_id') if source_runs else None)
        if not job:
            raise ValueError('源视频尚未生成完成')
        row = ns['owned_job'](job, owner)
        if row['state'] != 'COMPLETED_UNREVIEWED' or json.loads(row['payload']).get('kind') != 'video':
            raise ValueError('请选择已完成的视频结果')
        text = node.get('text', '').strip()
        if len(text) > 30000:
            raise ValueError('二采修改要求不能超过30000字')
        seed = node.get('settings', {}).get('seed')
        if seed is not None and (type(seed) is not int or not 0 <= seed <= 2**53-1):
            raise ValueError('随机种子无效')
        create = getattr(ns['app'].state, 'h3_video_resample', None)
        if create is None:
            raise HTTPException(501, '当前生成服务尚未安装视频二采适配器，未提交任务')
        history = [r for r in store.runs(owner, key) if r['node_id'] == node_id]
        if history and history[-1].get('job_id'):
            previous = ns['owned_job'](history[-1]['job_id'], owner)
            if previous['state'] not in ns['TERMINAL']:
                raise Conflict('当前二采仍在处理，请等待完成')
        options = {'text': text, 'steps': settings['steps'], 'denoise': settings['denoise'], 'seed': seed}
        run, claimed = store.claim(owner, key, node_id, token, fingerprint({'source': job, **options}))
        if not claimed:
            return run
        try:
            if text:
                prepare = getattr(ns['app'].state, 'h3_prompt_prepare', None)
                request_type = getattr(ns['app'].state, 'h3_prompt_request_type', None)
                if prepare is None or request_type is None:
                    raise HTTPException(501, '尚未配置本地 H3 提示词转换服务')
                saved = json.loads(row['payload'])
                seconds = max(4, min(15, int(saved.get('seconds', 5))))
                converted = await prepare(request, request_type(
                    source='保留源视频原有的人物身份、服装、构图、动作顺序和运镜，只按以下要求修正画面细节：'+text,
                    seconds=seconds, style=saved.get('style', '写实'), references=['源视频首帧']))
                if len(converted.get('segments', [])) != 1:
                    raise ValueError('视频二采只接受一个片段的修改要求')
                from canvas_h3 import compile_prompt
                options['text'] = compile_prompt(converted['segments'][0]['prompt'], [source['id']], seconds, saved.get('style', '写实'))
            result = await asyncio.to_thread(create, owner, job, options)
        except (HTTPException, ValueError) as exc:
            store.finish(token)
            if isinstance(exc, ValueError):
                raise HTTPException(422, str(exc)) from None
            raise
        # Unknown failures retain PENDING and must be reconciled, never resubmitted.
        store.finish(token, result['id'])
        return {'state': 'SUBMITTED', 'job_id': result['id'], 'token': token}
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except (ValueError, KeyError, StopIteration) as exc:
        raise HTTPException(422, str(exc)) from None
