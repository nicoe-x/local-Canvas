"""Persistent owner-scoped node trash. Never accept filesystem paths from clients."""
import copy
import json
import time
from contextvars import ContextVar
from contextlib import nullcontext
from fastapi import HTTPException, Request
from canvas_store import checked_id, document, Conflict


def register(ns, store, snapshot):
    app = ns['app']
    ignored = ContextVar('canvas_purge_entries', default=frozenset())
    with store.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS canvas_trash (id TEXT PRIMARY KEY,owner TEXT NOT NULL,canvas_id TEXT NOT NULL,created REAL NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,error TEXT)')

    def owner(request, write=False):
        return ns['authenticate'](request, sensitive=True, write=write)['id']

    def entries(user):
        with store.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM canvas_trash WHERE owner=? AND state IN ('TRASHED','PURGING') ORDER BY created DESC", (user,))]

    def sources(user, key, nodes):
        # All attempts belong to the removed node, not just its displayed result.
        ids = {n['id'] for n in nodes}
        jobs = {n['job_id'] for n in nodes if n.get('job_id')}
        with store.db() as db:
            for row in db.execute('SELECT node_id,job_id,state FROM canvas_runs WHERE canvas_id=?', (key,)):
                if row['node_id'] in ids:
                    if row['state'] == 'PENDING':
                        raise HTTPException(409, '节点提交结果待核对，请稍后再移入回收站')
                    if row['job_id']: jobs.add(row['job_id'])
        return {'jobs': sorted(jobs), 'media': sorted({n['media_id'] for n in nodes if n.get('media_id')})}

    def references(user, job=None, media=None, canvas=None):
        for item in store.list(user):
            graph = store.get(user, item['id'])['document']
            if job:
                if any(n.get('job_id') == job for n in graph['nodes']): return True
                with store.db() as db:
                    active = {n['id'] for n in graph['nodes']}
                    if any(r['node_id'] in active for r in db.execute('SELECT node_id FROM canvas_runs WHERE canvas_id=? AND job_id=?', (item['id'], job))): return True
            if media and item['id'] == canvas and any(n.get('media_id') == media for n in graph['nodes']): return True
        for row in entries(user):
            if row['id'] in ignored.get(): continue
            value = json.loads(row['payload'])
            if job and job in value['sources']['jobs']: return True
            if media and row['canvas_id'] == canvas and media in value['sources']['media']: return True
        return False

    original_purge = ns.get('purge_owned_job')
    if original_purge:
        def guarded_purge(job, user):
            with ns.get('LOCK',nullcontext()), store.lock:
                # Authorize before exposing reference information.
                with ns['database']() as db:
                    row = db.execute('SELECT owner FROM jobs WHERE id=? AND owner=?', (job, user)).fetchone()
                if not row: raise HTTPException(404, '任务不存在')
                if references(user, job=job): raise HTTPException(409, '该作品仍被其他画布节点或回收站项目引用，请先移除引用')
                return original_purge(job, user)
        ns['purge_owned_job'] = guarded_purge

    @app.get('/api/canvas-trash')
    def listing(request: Request):
        user = owner(request)
        return [{**{k:r[k] for k in ('id','canvas_id','created','state','error')}, 'title':json.loads(r['payload'])['title'], 'nodes':[{k:n.get(k) for k in ('id','title','kind')} for n in json.loads(r['payload'])['nodes']]} for r in entries(user)]

    @app.post('/api/canvases/{key}/trash')
    async def trash(key: str, request: Request):
        user = owner(request, True)
        data = await request.json()
        try:
            if not isinstance(data, dict) or set(data) != {'revision','node_ids','request_id'}: raise ValueError('移除参数无效')
            token = checked_id(data['request_id']); ids = data['node_ids']
            if not isinstance(ids,list) or not ids or len(ids)>200 or len(set(ids))!=len(ids): raise ValueError('请选择有效节点')
            for id in ids: checked_id(id)
            with store.lock:
                current = store.get(user,key)
                with store.db() as db:
                    old = db.execute('SELECT * FROM canvas_trash WHERE id=?',(token,)).fetchone()
                    if old:
                        if old['owner']!=user or old['canvas_id']!=key or set(json.loads(old['payload']).get('node_ids',[]))!=set(ids): raise Conflict('移除编号已使用')
                        return {'board':current,'trash_id':token}
                    if current['revision']!=data['revision']: raise Conflict('画布已更新，请刷新后再删除')
                    graph=copy.deepcopy(current['document']); chosen=[n for n in graph['nodes'] if n['id'] in ids]
                    if len(chosen)!=len(ids): raise ValueError('节点不存在')
                    src=sources(user,key,chosen)
                    saved={'title':graph['title'],'nodes':chosen,'node_ids':ids,'sources':src,'edges':[e for e in graph['edges'] if e['source'] in ids or e['target'] in ids], 'groups':[g for g in graph.get('groups',[]) if set(g['node_ids']) & set(ids)]}
                    graph['nodes']=[n for n in graph['nodes'] if n['id'] not in ids]
                    graph['edges']=[e for e in graph['edges'] if e not in saved['edges']]
                    if 'groups' in graph: graph['groups']=[dict(g,node_ids=[i for i in g['node_ids'] if i not in ids]) for g in graph['groups'] if set(g['node_ids'])-set(ids)]
                    db.execute('UPDATE canvases SET document=?,revision=revision+1,updated=? WHERE id=? AND owner=?',(json.dumps(document(graph),ensure_ascii=False),time.time(),key,user))
                    db.execute('INSERT INTO canvas_trash VALUES (?,?,?,?,?,?,NULL)',(token,user,key,time.time(),'TRASHED',json.dumps(saved,ensure_ascii=False)))
                result=store.get(user,key);snapshot(user,result)
                return {'board':result,'trash_id':token}
        except KeyError: raise HTTPException(404,'画布不存在') from None
        except Conflict as e: raise HTTPException(409,str(e)) from None
        except (ValueError,TypeError) as e: raise HTTPException(422,str(e)) from None

    @app.post('/api/canvas-trash/{token}/restore')
    def restore(token: str, request: Request):
        user=owner(request,True)
        with store.lock:
            with store.db() as db:
                row=db.execute("SELECT * FROM canvas_trash WHERE id=? AND owner=? AND state='TRASHED'",(token,user)).fetchone()
                if not row: raise HTTPException(409,'回收记录不存在或已开始彻底删除')
                saved=json.loads(row['payload']);current=store.get(user,row['canvas_id']);graph=copy.deepcopy(current['document'])
                if set(saved['node_ids']) & {n['id'] for n in graph['nodes']}: raise HTTPException(409,'原节点编号已存在，无法覆盖恢复')
                graph['nodes']+=saved['nodes'];ids={n['id'] for n in graph['nodes']}
                graph['edges'] += [e for e in saved['edges'] if e['source'] in ids and e['target'] in ids and e not in graph['edges']]
                groups=graph.setdefault('groups',[])
                for g in saved['groups']:
                    target=next((v for v in groups if v['id']==g['id']),None)
                    restored=[i for i in g['node_ids'] if i in saved['node_ids']]
                    if target: target['node_ids']+=restored
                    else: groups.append(dict(g,node_ids=restored))
                try: graph=document(graph)
                except ValueError as e: raise HTTPException(409,str(e)) from None
                db.execute('UPDATE canvases SET document=?,revision=revision+1,updated=? WHERE id=? AND owner=?',(json.dumps(graph,ensure_ascii=False),time.time(),row['canvas_id'],user))
                db.execute("UPDATE canvas_trash SET state='RESTORED',payload='{}',error=NULL WHERE id=?",(token,))
            result=store.get(user,row['canvas_id']);snapshot(user,result);return result

    @app.post('/api/canvas-trash/purge')
    async def purge(request: Request):
        user=owner(request,True); data=await request.json()
        if not isinstance(data,dict) or set(data)!={'ids'} or not isinstance(data['ids'],list) or not 1<=len(data['ids'])<=200: raise HTTPException(422,'请选择回收记录')
        try:
            ids=set(checked_id(v) for v in data['ids'])
        except (ValueError,TypeError): raise HTTPException(422,'回收编号无效') from None
        with ns.get('LOCK',nullcontext()), store.lock:
            rows=[r for r in entries(user) if r['id'] in ids]
            if len(rows)!=len(ids): raise HTTPException(404,'回收记录不存在')
            context=ignored.set(frozenset(ids))
            try:
                # Validate the full batch before deleting anything.
                for row in rows:
                    value=json.loads(row['payload'])
                    for job in value['sources']['jobs']:
                        if references(user,job=job): raise HTTPException(409,'作品仍有其他节点或回收记录引用，请一并选择相关记录')
                        with ns['database']() as db: task=db.execute('SELECT * FROM jobs WHERE id=? AND owner=?',(job,user)).fetchone()
                        if not task: raise HTTPException(404,'原任务不存在')
                        if not task['purged_at'] and task['state'] not in ns['PURGEABLE']: raise HTTPException(409,'原任务仍在处理，请稍后删除')
                    for media in value['sources']['media']:
                        if references(user,media=media,canvas=row['canvas_id']): raise HTTPException(409,'图片仍被其他节点或回收记录引用')
                deleted=[];failed=[]
                for row in rows:
                    with store.db() as db: db.execute("UPDATE canvas_trash SET state='PURGING',error=NULL WHERE id=?",(row['id'],))
                    try:
                        value=json.loads(row['payload'])
                        # Retry/upscale children must be erased before their parents.
                        tasks={}
                        with ns['database']() as db:
                            for job in value['sources']['jobs']:
                                task=db.execute('SELECT * FROM jobs WHERE id=? AND owner=?',(job,user)).fetchone()
                                if not task['purged_at']: tasks[job]=json.loads(task['payload']) if 'payload' in task.keys() else {}
                        ordered=[]
                        while tasks:
                            parents={p.get(k) for p in tasks.values() for k in ('retry_of','asset_reuse_of','upscale_of')}
                            leaves=[j for j in tasks if j not in parents]
                            if not leaves: raise HTTPException(409,'原任务存在循环依赖，需要管理员核对')
                            for j in leaves: ordered.append(j);tasks.pop(j)
                        for job in ordered:
                            with ns['database']() as db:
                                task=db.execute('SELECT * FROM jobs WHERE id=? AND owner=?',(job,user)).fetchone()
                                if task['purged_at']: continue
                                db.execute('UPDATE jobs SET deleted_at=COALESCE(deleted_at,?) WHERE id=? AND owner=?',(time.time(),job,user))
                            ns['purge_owned_job'](job,user)
                        for media in value['sources']['media']:
                            eraser=ns.get('erase_canvas_media')
                            if eraser is None:
                                from canvas_file_delete import erase_media as eraser
                            eraser(ns['MATERIAL'],ns['user_folder'](user),row['canvas_id'],media)
                        with store.db() as db:
                            for node in value['node_ids']: db.execute('DELETE FROM canvas_runs WHERE canvas_id=? AND node_id=?',(row['canvas_id'],node))
                            db.execute("UPDATE canvas_trash SET state='PURGED',payload='{}',error=NULL WHERE id=?",(row['id'],))
                        deleted.append(row['id'])
                    except Exception as e:
                        detail=e.detail if isinstance(e,HTTPException) else '磁盘或归档删除未完成，请重试彻底删除'
                        with store.db() as db: db.execute('UPDATE canvas_trash SET error=? WHERE id=?',(str(detail),row['id']))
                        failed.append({'id':row['id'],'error':str(detail)})
                return {'deleted':deleted,'failed':failed}
            finally: ignored.reset(context)
