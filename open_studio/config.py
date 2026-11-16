import ipaddress
import json
import os
from pathlib import Path
import socket
from urllib.parse import urlsplit


def private_address(value):
    ip=ipaddress.ip_address(value)
    return ip.is_loopback or (ip.version==4 and any(ip in ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))) or (ip.version==6 and ip in ipaddress.ip_network('fc00::/7'))


def endpoint(value):
    if not isinstance(value,str) or len(value)>500:raise ValueError('ComfyUI 地址无效')
    parsed=urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise ValueError('请填写 http(s)://主机:端口，不要在地址内填写密码、查询参数或路径')
    port=parsed.port or (443 if parsed.scheme=='https' else 80)
    if not 1<=port<=65535:raise ValueError('端口无效')
    addresses={item[4][0] for item in socket.getaddrinfo(parsed.hostname,port,type=socket.SOCK_STREAM)}
    if not addresses or not all(private_address(ip) for ip in addresses):raise ValueError('仅支持本机和局域网地址；不允许公网、链路本地或元数据地址')
    host='['+parsed.hostname+']' if ':' in parsed.hostname else parsed.hostname
    return f'{parsed.scheme}://{host}:{port}'


class Config:
    def __init__(self,root):
        self.root=Path(root).expanduser().resolve();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=self.root/'settings.json'

    def read(self):
        return json.loads(self.path.read_text(encoding="utf8")) if self.path.exists() else {}

    def write(self,value):
        temporary=self.path.with_suffix('.tmp')
        with temporary.open('w',encoding='utf8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
        temporary.chmod(0o600);temporary.replace(self.path)

    def public(self):
        value=self.read();comfy=value.get('comfy',{})
        return {'comfy':{'url':comfy.get('url',''),'verify_tls':comfy.get('verify_tls',True),'has_auth':bool(comfy.get('headers'))},'connected':bool(comfy),'defaults':value.get('defaults',{})}
