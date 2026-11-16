"""Build a standalone deployment ZIP from explicit source and asset allowlists."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

REPO=Path(__file__).resolve().parents[1]
FILES=['pyproject.toml','setup.py','README.md','LICENSE','NOTICE','Dockerfile','compose.yaml','start.ps1','start.sh','.dockerignore','MANIFEST.in','requirements-tested.txt','VALIDATION.md']
MODULES=['__init__.py','__main__.py','app.py','comfy.py','config.py','engine.py','store.py','workflows.py']
CANVAS=['canvas_store.py','canvas_routes.py','canvas_trash.py','canvas_selection_download.py','canvas_media_tools.py','prepare_three.py','three-manifest.json']


def build(output,with_three=True,three_cache=None):
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)/'open-comfy-studio';root.mkdir()
        def copy(source,relative):
            target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        for name in FILES:copy(REPO/name,name)
        for name in MODULES:copy(REPO/'open_studio'/name,'open_studio/'+name)
        for name in CANVAS:copy(REPO/'open_studio/_canvas'/name,'open_studio/_canvas/'+name)
        for directory in ['open_studio/static','open_studio/_canvas/static']:
            for path in (REPO/directory).iterdir():
                if path.is_file() and path.suffix in {'.js','.css','.html','.svg'}:copy(path,directory+'/'+path.name)
        if with_three:
            source=Path(three_cache) if three_cache else REPO/'open_studio/_canvas/static/vendor/three'
            manifest=json.loads((REPO/'open_studio/_canvas/three-manifest.json').read_text(encoding='utf8'))['files']
            for name,digest in manifest.items():
                path=source/name
                if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Three.js integrity mismatch: '+name)
                copy(path,'open_studio/_canvas/static/vendor/three/'+name)
        manifest={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
        (root/'MANIFEST.sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob('*')):
                if path.is_file():archive.write(path,'open-comfy-studio/'+path.relative_to(root).as_posix())
    return {'path':str(output),'files':len(manifest)+1,'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--without-three',action='store_true');args=parser.parse_args()
    print(json.dumps(build(args.output,not args.without_three),indent=2))
