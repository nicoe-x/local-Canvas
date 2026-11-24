"""Owner-scoped canvas documents; generation runs are separate, immutable records."""
import hashlib
import json
import math
import re
import sqlite3
import time
import threading
import uuid
from contextlib import contextmanager

ID = re.compile(r"^[a-f0-9]{32}$")
KINDS = {"note", "image", "video", "asset", "reverse", "stage3d", "h3prompt"}


def checked_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("编号无效")
    return value


def document(value):
    if not isinstance(value, dict) or set(value) - {"title", "nodes", "edges", "viewport", "groups"}:
        raise ValueError("画布格式无效")
    title = value.get("title", "未命名画布")
    nodes, edges = value.get("nodes", []), value.get("edges", [])
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80:
        raise ValueError("画布名称须为1–80字")
    if not isinstance(nodes, list) or len(nodes) > 200 or not isinstance(edges, list) or len(edges) > 400:
        raise ValueError("单画布最多200张卡片和400条连线")
    seen = set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) - {"id", "kind", "x", "y", "title", "text", "settings", "job_id", "media_id"}:
            raise ValueError("卡片格式无效")
        checked_id(node.get("id"))
        if node["id"] in seen or node.get("kind") not in KINDS:
            raise ValueError("卡片编号重复或类型无效")
        seen.add(node["id"])
        for axis in ("x", "y"):
            number = node.get(axis)
            if isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number) or abs(number) > 100000:
                raise ValueError("卡片位置无效")
        if not isinstance(node.get("title", ""), str) or len(node.get("title", "")) > 80:
            raise ValueError("卡片名称过长")
        if not isinstance(node.get("text", ""), str) or len(node.get("text", "")) > 50000:
            raise ValueError("提示词过长")
        for key in ("job_id", "media_id"):
            if node.get(key):
                checked_id(node[key])
        settings = node.get("settings", {})
        if not isinstance(settings, dict) or set(settings) - {"variant", "ratio", "style", "seconds", "steps", "cfg", "seed", "image_task", "stage3d", "reverse_prompts", "reverse_language", "reference_mentions", "h3_prompt", "h3_result", "face_repair", "face_reference", "video_resample"}:
            raise ValueError("生成参数无效")
        if 'video_resample' in settings:
            from canvas_video_resample import validate_settings
            if node['kind'] != 'video':
                raise ValueError('二采设置仅用于视频节点')
            validate_settings(settings['video_resample'])
        if 'face_repair' in settings and (type(settings['face_repair']) is not bool or node['kind'] != 'video'):
            raise ValueError('小脸修复仅接受视频节点的布尔开关')
        if settings.get('face_reference') is not None:
            if node['kind'] != 'video':raise ValueError('人物参考仅用于视频修复')
            checked_id(settings['face_reference'])
        if 'h3_result' in settings:
            result=settings['h3_result']
            if not isinstance(result,dict) or set(result)!={'segments','selected','model','references','input_source'}:
                raise ValueError('H3 转换结果格式无效')
            if not isinstance(result['input_source'],str) or len(result['input_source'])>30000:
                raise ValueError('H3 原文快照过长')
            parts=result['segments']
            if not isinstance(parts,list) or not 1<=len(parts)<=6 or type(result['selected']) is not int or not 0<=result['selected']<len(parts):
                raise ValueError('H3 输出片段无效')
            for part in parts:
                if not isinstance(part,dict) or set(part)!={'seconds','prompt'} or type(part['seconds']) is not int or not 4<=part['seconds']<=15 or not isinstance(part['prompt'],str) or not 1<=len(part['prompt'])<=30000:
                    raise ValueError('H3 输出片段格式无效')
            if sum(part['seconds'] for part in parts)>90 or not isinstance(result['model'],str) or len(result['model'])>200:
                raise ValueError('H3 转换结果过长')
            if not isinstance(result['references'],list) or len(result['references'])>9:
                raise ValueError('H3 参考图对应关系无效')
            for item in result['references']:checked_id(item)
            if len(set(result['references']))!=len(result['references']):raise ValueError('H3 参考图编号重复')
        if 'h3_prompt' in settings:
            data=settings['h3_prompt']
            if not isinstance(data,dict) or set(data)!={'source','seconds','style'}:
                raise ValueError('H3 提示词输入格式无效')
            if not isinstance(data['source'],str) or len(data['source'])>30000 or not isinstance(data['style'],str) or not 1<=len(data['style'])<=200:
                raise ValueError('H3 提示词输入过长或风格无效')
            if type(data['seconds']) is not int or not 4<=data['seconds']<=90:
                raise ValueError('H3 总时长为4–90秒')
        if "reference_mentions" in settings:
            mentions = settings["reference_mentions"]
            if not isinstance(mentions, dict) or len(mentions)>200:
                raise ValueError("参考图引用格式无效")
            for alias, source in mentions.items():
                if not isinstance(alias,str) or not re.fullmatch(r"参考图[1-9]\d{0,2}",alias):
                    raise ValueError("参考图引用名称无效")
                checked_id(source)
        if "stage3d" in settings:
            validate_stage(settings["stage3d"])
        if "reverse_language" in settings and settings["reverse_language"] not in {"zh", "en"}:
            raise ValueError("反推语言无效")
        if "reverse_prompts" in settings:
            prompts = settings["reverse_prompts"]
            if not isinstance(prompts, dict) or set(prompts) - {"zh", "en", "negative", "model"}:
                raise ValueError("反推结果格式无效")
            if any(not isinstance(text,str) or len(text)>50000 for text in prompts.values()):
                raise ValueError("反推结果过长")
    adj = {key: [] for key in seen}
    unique = set()
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {"source", "target"}:
            raise ValueError("连线格式无效")
        pair = (checked_id(edge["source"]), checked_id(edge["target"]))
        if pair[0] not in seen or pair[1] not in seen or pair[0] == pair[1] or pair in unique:
            raise ValueError("连线重复或指向不存在的卡片")
        unique.add(pair)
        adj[pair[0]].append(pair[1])
    active, done = set(), set()
    def visit(key):
        if key in active:
            raise ValueError("连线不能形成循环")
        if key in done:
            return
        active.add(key)
        for other in adj[key]:
            visit(other)
        active.remove(key)
        done.add(key)
    for key in seen:
        visit(key)
    viewport = value.get("viewport", {"x": 80, "y": 80, "zoom": 1})
    if not isinstance(viewport, dict) or set(viewport) != {"x", "y", "zoom"}:
        raise ValueError("视口无效")
    for key, number in viewport.items():
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or abs(number) > 1000000:
            raise ValueError("视口参数无效")
    if not .15 <= viewport["zoom"] <= 8:
        raise ValueError("缩放范围为15%–800%")
    result = {"title": title.strip(), "nodes": nodes, "edges": edges, "viewport": viewport}
    if 'groups' in value:
        groups=value['groups'];group_ids=set();members=set()
        if not isinstance(groups,list) or len(groups)>100:raise ValueError('最多100个分组')
        for group in groups:
            if not isinstance(group,dict) or set(group)!={'id','title','node_ids'}:raise ValueError('分组格式无效')
            key=checked_id(group['id']);items=group['node_ids']
            if key in group_ids or not isinstance(group['title'],str) or not group['title'].strip() or len(group['title'])>80:raise ValueError('分组名称或编号无效')
            if not isinstance(items,list) or not 1<=len(items)<=200:raise ValueError('分组成员无效')
            for item in items:checked_id(item)
            if len(set(items))!=len(items) or set(items)-seen or members.intersection(items):raise ValueError('分组成员重复或不存在')
            group_ids.add(key);members.update(items)
        result['groups']=groups
    return result


def validate_stage(stage):
    if not isinstance(stage, dict) or set(stage) != {"actors", "camera"}:
        raise ValueError("三维场景格式无效")
    def number(value, low, high):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError("三维坐标或尺寸无效")
    actors = stage["actors"]
    if not isinstance(actors,list) or len(actors)>30:
        raise ValueError("三维场景最多30个人物或道具")
    ids=set()
    for actor in actors:
        if not isinstance(actor,dict) or set(actor)!={"id","kind","x","z","rotation","height","color"}:
            raise ValueError("三维物体格式无效")
        checked_id(actor["id"])
        if actor["id"] in ids or actor["kind"] not in {"person","box","chair","table"}:
            raise ValueError("三维物体类型或编号无效")
        ids.add(actor["id"])
        for key in ["x","z"]:number(actor[key],-50,50)
        number(actor["rotation"],-360,360);number(actor["height"],.3,5)
        if not isinstance(actor["color"],str) or not re.fullmatch(r"#[a-fA-F0-9]{6}",actor["color"]):
            raise ValueError("三维颜色无效")
    camera=stage["camera"]
    if not isinstance(camera,dict) or set(camera)!={"position","target","fov"}:
        raise ValueError("摄影机格式无效")
    for key in ["position","target"]:
        values=camera[key]
        if not isinstance(values,list) or len(values)!=3:raise ValueError("摄影机坐标无效")
        for value in values:number(value,-100,100)
    if sum((a-b)**2 for a,b in zip(camera['position'],camera['target']))<.01:
        raise ValueError("摄影机与目标不能重合")
    number(camera['fov'],15,90)


class Conflict(Exception):
    pass


class Store:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.source_validator = None

    @contextmanager
    def db(self):
        with self.lock:
            with self._db() as db:
                yield db

    @contextmanager
    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.row_factory = sqlite3.Row
            db.executescript("""
            CREATE TABLE IF NOT EXISTS canvases (
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, revision INTEGER NOT NULL,
              document TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS canvas_runs (
              token TEXT PRIMARY KEY, canvas_id TEXT NOT NULL, node_id TEXT NOT NULL,
              fingerprint TEXT NOT NULL, job_id TEXT, state TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS canvas_projects (
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
              created REAL NOT NULL, updated REAL NOT NULL, UNIQUE(owner,name));
            """)
            if 'project_id' not in {row[1] for row in db.execute('PRAGMA table_info(canvases)')}:
                db.execute('ALTER TABLE canvases ADD COLUMN project_id TEXT')
            db.execute('CREATE INDEX IF NOT EXISTS canvases_owner_project ON canvases(owner,project_id)')
            with db:
                yield db
        finally:
            db.close()

    def list(self, owner, project_id="all"):
        with self.db() as db:
            if project_id == 'all':
                rows = db.execute("SELECT * FROM canvases WHERE owner=? ORDER BY updated DESC", (owner,)).fetchall()
            else:
                target=None if project_id=='unclassified' else project_id
                self.check_project(db,owner,target)
                rows=db.execute('SELECT * FROM canvases WHERE owner=? AND project_id IS ? ORDER BY updated DESC',(owner,target)).fetchall()
        return [{"id": row["id"], "title": json.loads(row["document"])["title"], "updated": row["updated"],
                 "project_id":row['project_id'], "node_count":len(json.loads(row['document'])['nodes'])} for row in rows]

    def get(self, owner, key):
        checked_id(key)
        with self.db() as db:
            row = db.execute("SELECT * FROM canvases WHERE id=? AND owner=?", (key, owner)).fetchone()
        if not row:
            raise KeyError(key)
        return {"id": key, "revision": row["revision"], "document": json.loads(row["document"]), "project_id":row['project_id']}

    def create(self, owner, value, project_id=None):
        value = document(value)
        key = uuid.uuid4().hex
        with self.db() as db:
            self.check_project(db,owner,project_id)
            if self.source_validator: self.source_validator(owner, key, value)
            db.execute("INSERT INTO canvases (id,owner,revision,document,updated,project_id) VALUES (?,?,1,?,?,?)", (key, owner, json.dumps(value, ensure_ascii=False), time.time(),project_id))
        return self.get(owner, key)

    @staticmethod
    def check_project(db,owner,key):
        if key is None:return
        checked_id(key)
        if not db.execute('SELECT 1 FROM canvas_projects WHERE id=? AND owner=?',(key,owner)).fetchone():
            raise KeyError('项目不存在')

    @staticmethod
    def project_name(name):
        if not isinstance(name,str) or not 1<=len(name.strip())<=80:
            raise ValueError('项目名称须为1–80字')
        return name.strip()

    def projects(self,owner):
        with self.db() as db:
            rows=db.execute('SELECT p.id,p.name,p.created,p.updated,count(c.id) AS canvas_count FROM canvas_projects p LEFT JOIN canvases c ON c.project_id=p.id AND c.owner=p.owner WHERE p.owner=? GROUP BY p.id ORDER BY p.updated DESC,p.id',(owner,)).fetchall()
            unclassified=db.execute('SELECT count(*) FROM canvases WHERE owner=? AND project_id IS NULL',(owner,)).fetchone()[0]
        return {'items':[dict(row) for row in rows], 'unclassified_count':unclassified}

    def create_project(self,owner,name):
        name=self.project_name(name);key=uuid.uuid4().hex;now=time.time()
        try:
            with self.db() as db:db.execute('INSERT INTO canvas_projects VALUES (?,?,?,?,?)',(key,owner,name,now,now))
        except sqlite3.IntegrityError:raise ValueError('已有同名项目，请使用其他名称') from None
        return {'id':key,'name':name,'canvas_count':0}

    def rename_project(self,owner,key,name):
        name=self.project_name(name)
        try:
            with self.db() as db:
                self.check_project(db,owner,key)
                if key is None:raise ValueError('未分类不能重命名')
                db.execute('UPDATE canvas_projects SET name=?,updated=? WHERE id=? AND owner=?',(name,time.time(),key,owner))
        except sqlite3.IntegrityError:raise ValueError('已有同名项目，请使用其他名称') from None
        return {'id':key,'name':name}

    def move(self,owner,key,project_id,revision):
        checked_id(key)
        if isinstance(revision,bool) or not isinstance(revision,int) or revision<1:raise ValueError('画布版本无效')
        with self.db() as db:
            self.check_project(db,owner,project_id)
            result=db.execute('UPDATE canvases SET project_id=?,revision=revision+1,updated=? WHERE id=? AND owner=? AND revision=?',(project_id,time.time(),key,owner,revision))
            if result.rowcount!=1:raise Conflict('画布已更新，请刷新后再移动分类')
        return self.get(owner,key)

    def save(self, owner, key, revision, value):
        checked_id(key)
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError("画布版本无效")
        value = document(value)
        with self.db() as db:
            if self.source_validator: self.source_validator(owner, key, value)
            cursor = db.execute("UPDATE canvases SET document=?,revision=revision+1,updated=? WHERE id=? AND owner=? AND revision=?",
                                (json.dumps(value, ensure_ascii=False), time.time(), key, owner, revision))
            if cursor.rowcount != 1:
                raise Conflict("其他页面已更新画布，请导出当前内容后重新加载")
        return self.get(owner, key)

    def runs(self, owner, key):
        self.get(owner, key)
        with self.db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM canvas_runs WHERE canvas_id=? ORDER BY created", (key,))]

    def claim(self, owner, key, node_id, token, fingerprint):
        checked_id(token)
        current = self.get(owner, key)
        if node_id not in {n["id"] for n in current["document"]["nodes"]}:
            raise ValueError("卡片不存在")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM canvas_runs WHERE token=?", (token,)).fetchone()
            if existing:
                if existing["canvas_id"] != key or existing["node_id"] != node_id or existing["fingerprint"] != fingerprint:
                    raise Conflict("提交编号已用于其他操作")
                return dict(existing), False
            if db.execute("SELECT 1 FROM canvas_runs WHERE canvas_id=? AND node_id=? AND state='PENDING'", (key, node_id)).fetchone():
                raise Conflict("上次提交结果待核对，请到原工作台检查任务，勿重复生成")
            db.execute("INSERT INTO canvas_runs VALUES (?,?,?,?,NULL,'PENDING',?)", (token, key, node_id, fingerprint, time.time()))
        return {"token": token, "state": "PENDING", "job_id": None}, True

    def finish(self, token, job_id=None):
        with self.db() as db:
            db.execute("UPDATE canvas_runs SET job_id=?,state=? WHERE token=?", (job_id, "SUBMITTED" if job_id else "REJECTED", token))

    def exclude_infrastructure(self, token):
        with self.db() as db:
            db.execute("UPDATE canvas_runs SET state='INFRASTRUCTURE_FAILED' WHERE token=? AND state='SUBMITTED'", (token,))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def resolve_reference_mentions(text, settings, ordered_sources, kind):
    """Stable node-bound aliases become the actual reference upload indices.

    A disconnected/deleted source is an error, never rebound to another image.
    """
    mentions=settings.get("reference_mentions",{})
    def replace(match):
        alias=match.group(1);source=mentions.get(alias)
        if not source or source not in ordered_sources:
            raise ValueError(f"@{alias} 已失效，请重新选择参考图或删除该引用")
        index=ordered_sources.index(source)+1
        return f"<Picture {index}>" if kind=='video' else f"参考图{index}"
    return re.sub(r"@(参考图[1-9]\d{0,2})(?!\d)",replace,text)
