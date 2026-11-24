"""Produce a reviewed private-server overlay from an exact source snapshot.

Does not write to a running service. Paths here are source/output directories only.
"""
from pathlib import Path
import shutil
import sys


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Private adapter version mismatch: '+before[:100])
    return text.replace(before, after, 1)


def patch(name, text):
    if name == 'gateway/runner.py':
        anchor='        if payload.get("upscale_of"):'
        return once(text,anchor,
            '        if payload.get("resample_of"):\n'
            '            from video_resample import run as run_resample\n'
            '            status("RUNNING", "等待视频二采资源", 3)\n'
            '            with gpu_session(ROOT / "gpu.lock"):\n'
            '                run_resample(folder, payload, job_id, status)\n'
            '            return\n'+anchor)
    if name == 'gateway/bridge.py':
        return once(text,'and not payload.get("upscale_of"):',
                    'and not payload.get("upscale_of") and not payload.get("resample_of"):')
    if name == 'studio/app.py':
        text=once(text,"OR json_extract(payload,'$.upscale_of')=?) LIMIT 1",
                        "OR json_extract(payload,'$.upscale_of')=? OR json_extract(payload,'$.resample_of')=?) LIMIT 1")
        text=once(text,'(job_id, job_id, job_id, job_id),','(job_id, job_id, job_id, job_id, job_id),')
        before='"retry_of", "asset_reuse_of", "upscale_of"'
        if text.count(before) != 2:
            raise ValueError('Private deletion dependency policy changed')
        return text.replace(before,before+', "resample_of"')
    if name == 'studio/app_private.py':
        return text+'\nfrom video_resample_routes import register as register_video_resample\nregister_video_resample(vars(legacy))\n'
    if name == 'studio/canvas_routes.py':
        text=once(text,'"face_repair": bool(getattr(app.state, \'h3_face_repair\', False))}',
                       '"face_repair": bool(getattr(app.state, \'h3_face_repair\', False)),\n'
                       '                "video_resample": callable(getattr(app.state, \'h3_video_resample\', None))}')
        anchor='            previous_token=next('
        if text.count(anchor)!=1:raise ValueError('Canvas submission hook changed')
        return text.replace(anchor,
            "            if node.get('settings', {}).get('video_resample') is not None:\n"
            '                from canvas_video_resample import generate as resample\n'
            '                return await resample(ns, store, owner, key, node_id, body, request)\n'+anchor,1)
    if name == 'studio/canvas_store.py':
        lines=text.splitlines(keepends=True)
        matches=[i for i,line in enumerate(lines) if 'set(settings) - {' in line]
        if len(matches)!=1:raise ValueError('Canvas settings whitelist changed')
        i=matches[0];lines[i]=once(lines[i],'}:',', "video_resample"}:')
        lines.insert(i+2,"        if 'video_resample' in settings:\n"
                     '            from canvas_video_resample import validate_settings\n'
                     "            if node['kind'] != 'video':\n"
                     "                raise ValueError('二采设置仅用于视频节点')\n"
                     "            validate_settings(settings['video_resample'])\n")
        return ''.join(lines)
    if name == 'studio/static/canvas-result-tools.js':
        return once(text,"  const videoActions=[", "  const videoActions=[['reshoot','二次采样',s=>window.openVideoResample(nodeBy(s.node.id))],")
    if name == 'studio/static/canvas.html':
        import re
        text=re.sub(r'(canvas-result-tools\.(?:css|js))\?[^"\s]+',r'\1?v=20261124-resample2',text)
        return once(text,'</head>','<script src="/canvas-video-resample.js?v=20261124-02" defer></script></head>')
    raise ValueError('Unexpected overlay path '+name)


PATCHES=['gateway/runner.py','gateway/bridge.py','studio/app.py','studio/app_private.py',
         'studio/canvas_routes.py','studio/canvas_store.py','studio/static/canvas-result-tools.js','studio/static/canvas.html']


def build(source, output):
    source,output=Path(source).resolve(),Path(output).resolve()
    if source==output or source in output.parents:
        raise ValueError('Use a separate output directory')
    here=Path(__file__).resolve().parent
    root=here.parents[1]
    changes={name:patch(name,(source/name).read_text(encoding='utf8')) for name in PATCHES}
    for name,text in changes.items():
        if name.endswith('.py'):compile(text,name,'exec')
    for name,text in changes.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf8')
    for folder,names in [('gateway',['video_resample.py']),('studio',['video_resample.py','video_resample_routes.py'])]:
        for name in names:shutil.copyfile(here/name,output/folder/name)
    shutil.copyfile(root/'open_studio/_canvas/canvas_video_resample.py',output/'studio/canvas_video_resample.py')
    shutil.copyfile(root/'open_studio/_canvas/static/canvas-video-resample.js',output/'studio/static/canvas-video-resample.js')
    css=(root/'open_studio/_canvas/static/canvas-result-tools.css').read_text(encoding='utf8').split('.resample-fields',1)[1]
    (output/'studio/static/canvas-result-tools.css').write_text(
        (source/'studio/static/canvas-result-tools.css').read_text(encoding='utf8')+'\n.resample-fields'+css,encoding='utf8')


if __name__=='__main__':
    build(*sys.argv[1:])
