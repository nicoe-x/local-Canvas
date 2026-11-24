"""Private Studio queue adapter. The browser supplies no owner, paths or priority."""
import json
import secrets
import time
import uuid

from fastapi import HTTPException


def register(ns):
    def create(owner, source_id, options):
        from video_resample import inspect_source
        with ns['LOCK'], ns['database']() as db:
            source = ns['owned_job'](source_id, owner)
            saved = json.loads(source['payload'])
            if source['state'] != 'COMPLETED_UNREVIEWED' or saved.get('kind') != 'video':
                raise HTTPException(409, '请选择已完成的视频')
            info = inspect_source(ns['output_folder'](source) / 'final.mp4')
            active = "('QUEUED','STARTING','RUNNING','CANCELLING','PAUSING','PAUSED','RESUMING')"
            own = db.execute('SELECT count(*) FROM jobs WHERE owner=? AND state IN '+active, (owner,)).fetchone()[0]
            total = db.execute('SELECT count(*) FROM jobs WHERE state IN '+active).fetchone()[0]
            if own >= 3 or total >= 20:
                raise HTTPException(429, '任务队列已满，请等待已有任务完成')
            key = uuid.uuid4().hex
            derived = {'kind': 'video', 'mode': 'creative', 'title': source['title'][:65]+' · 二次采样',
                       'text': options['text'], 'style': saved.get('style', '写实'),
                       'seconds': info['frames']/24, 'ratio': saved.get('ratio', '16:9'),
                       'labels': [], 'video_resolution': 'native', 'resample_of': source_id,
                       'video_resample': {'steps': options['steps'], 'denoise': options['denoise'],
                                          'seed': options['seed'] if options['seed'] is not None else secrets.randbelow(2**53)},
                       'expedite': False}
            folder = ns['material_folder'](owner, key)
            folder.mkdir(parents=True, mode=0o700)
            (folder/'request.json').write_text(json.dumps(derived, ensure_ascii=False), encoding='utf8')
            db.execute("INSERT INTO jobs(id,owner,title,state,stage,payload,created,attempt,root_id) VALUES(?,?,?,'QUEUED','等待视频二采',?,?,1,?)",
                       (key, owner, derived['title'], json.dumps(derived, ensure_ascii=False), time.time(), key))
        return {'id': key}
    ns['app'].state.h3_video_resample = create
