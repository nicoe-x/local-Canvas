import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid


TERMINAL={'COMPLETED_UNREVIEWED','FAILED','CANCELLED','NEEDS_ATTENTION'}
PURGEABLE={'COMPLETED_UNREVIEWED','FAILED','CANCELLED'}


def password_hash(password,salt=None):
    salt=salt or secrets.token_bytes(16)
    return base64.b64encode(salt).decode()+':'+base64.b64encode(hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1)).decode()


def check_password(password,value):
    salt=base64.b64decode(value.split(':')[0]);return hmac.compare_digest(password_hash(password,salt),value)


class Store:
    def __init__(self,root):
        self.root=Path(root);self.lock=threading.RLock();self.path=self.root/'studio.sqlite3'
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,owner TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,owner TEXT NOT NULL,title TEXT NOT NULL,state TEXT NOT NULL,stage TEXT NOT NULL,progress INTEGER NOT NULL DEFAULT 0,payload TEXT NOT NULL,detail TEXT NOT NULL DEFAULT '{}',created REAL NOT NULL,prompt_id TEXT,deleted_at REAL,purged_at REAL,purge_started_at REAL);
            CREATE TABLE IF NOT EXISTS workflows(id TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT NOT NULL,document TEXT NOT NULL,created REAL NOT NULL);
            ''')
        token=self.root/'setup-token'
        if not self.has_user() and not token.exists():token.write_text(secrets.token_urlsafe(24));token.chmod(0o600)

    @contextmanager
    def db(self):
        with self.lock:
            db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
            try:
                with db:yield db
            finally:db.close()

    def has_user(self):
        with self.db() as db:return bool(db.execute('SELECT 1 FROM users LIMIT 1').fetchone())

    def setup(self,username,password,token):
        with self.lock:
            if self.has_user():raise ValueError('初始化已经完成')
            expected=(self.root/'setup-token').read_text()
            if not isinstance(token,str) or not hmac.compare_digest(expected,token):raise ValueError('初始化令牌不正确')
            if not isinstance(username,str) or not 1<=len(username.strip())<=60 or not isinstance(password,str) or not 8<=len(password)<=128:raise ValueError('用户名须1–60字，密码须8–128字')
            key=uuid.uuid4().hex
            with self.db() as db:db.execute('INSERT INTO users VALUES (?,?,?)',(key,username.strip(),password_hash(password)))
            (self.root/'setup-token').unlink();return key

    def login(self,username,password):
        with self.db() as db:row=db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        if not row or not check_password(password,row['password_hash']):raise ValueError('账号或密码不正确')
        session=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)',(hashlib.sha256(session.encode()).hexdigest(),row['id'],csrf,time.time()+7*86400))
        return session,csrf

    def session(self,cookie):
        with self.db() as db:return db.execute('SELECT s.*,u.username FROM sessions s JOIN users u ON u.id=s.owner WHERE s.id=? AND expires>?',(hashlib.sha256((cookie or '').encode()).hexdigest(),time.time())).fetchone()

    def job(self,key,owner):
        with self.db() as db:return db.execute('SELECT * FROM jobs WHERE id=? AND owner=?',(key,owner)).fetchone()

    def update(self,key,**values):
        allowed={'state','stage','progress','detail','prompt_id','deleted_at','purged_at','purge_started_at','payload'}
        if not values or set(values)-allowed:raise ValueError('Invalid job mutation')
        with self.db() as db:db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*[json.dumps(v,ensure_ascii=False) if k in {'detail','payload'} else v for k,v in values.items()],key))

    def new_job(self,owner,payload,workflow):
        key=uuid.uuid4().hex
        # Freeze the workflow at submission; later editing does not change queued work.
        payload={**payload,'workflow':workflow}
        with self.db() as db:db.execute("INSERT INTO jobs(id,owner,title,state,stage,payload,created) VALUES (?,?,?,'QUEUED','等待 ComfyUI 调度',?,?)",(key,owner,payload.get('title','未命名作品'),json.dumps(payload,ensure_ascii=False),time.time()))
        return key

    def workflows(self):
        with self.db() as db:return [json.loads(r['document']) for r in db.execute('SELECT * FROM workflows ORDER BY created')]

    def workflow(self,key):return next((w for w in self.workflows() if w['id']==key),None)

    def save_workflow(self,value):
        with self.db() as db:db.execute('INSERT INTO workflows VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,kind=excluded.kind,document=excluded.document',(value['id'],value['name'],value['kind'],json.dumps(value,ensure_ascii=False),time.time()))
        return value
