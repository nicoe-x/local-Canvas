"""Bundle the shared canvas through a strict source allowlist when building wheels."""
from pathlib import Path
import shutil
from setuptools import setup
from setuptools.command.build_py import build_py

BACKEND=['canvas_store.py','canvas_routes.py','canvas_trash.py','canvas_selection_download.py','canvas_media_tools.py','prepare_three.py','three-manifest.json']


class BuildCanvas(build_py):
    def run(self):
        super().run()
        base=Path(__file__).resolve().parent;source=base/'open_studio/_canvas'
        destination=Path(self.build_lib)/'open_studio/_canvas';destination.mkdir(parents=True,exist_ok=True)
        for name in BACKEND:shutil.copyfile(source/name,destination/name)
        static=source/'static' if (source/'static').is_dir() else source
        for path in static.iterdir():
            if path.is_file() and path.suffix in {'.js','.css','.html','.svg'}:
                (destination/'static').mkdir(exist_ok=True);shutil.copyfile(path,destination/'static'/path.name)
        vendor=static/'vendor/three'
        if vendor.is_dir():shutil.copytree(vendor,destination/'static/vendor/three',dirs_exist_ok=True)


setup(cmdclass={'build_py':BuildCanvas})
