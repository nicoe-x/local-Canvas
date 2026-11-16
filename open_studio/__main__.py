import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description='Open Comfy Studio — standalone creative workspace')
    parser.add_argument('command',nargs='?',choices=['serve','assets'],default='serve')
    parser.add_argument('--data',default=os.environ.get('OPEN_STUDIO_DATA','./studio-data'))
    parser.add_argument('--host',default=os.environ.get('OPEN_STUDIO_HOST','127.0.0.1'))
    parser.add_argument('--port',type=int,default=int(os.environ.get('OPEN_STUDIO_PORT','8848')))
    args=parser.parse_args()
    from .app import create_app,resources
    if args.command=='assets':
        sys.path.insert(0,str(resources()))
        from prepare_three import prepare
        expected=json.loads((resources()/'three-manifest.json').read_text())
        actual=prepare(Path(args.data)/'assets/three')
        if actual!=expected['files']:raise SystemExit('Three.js file integrity mismatch')
        print('Verified Three.js assets installed.');return
    app=create_app(args.data)
    token=Path(args.data)/'setup-token'
    print(f'Open Comfy Studio: http://{args.host}:{args.port}')
    if token.exists():print('初始化令牌（仅首次使用）：'+token.read_text())
    import uvicorn
    uvicorn.run(app,host=args.host,port=args.port,proxy_headers=False)


if __name__=='__main__':main()
