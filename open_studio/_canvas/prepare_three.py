"""Install minimal pinned MIT Three.js runtime; no CDN at browser runtime."""
import base64
import hashlib
import io
from pathlib import Path
import tarfile
import urllib.request

VERSION = "0.187.0"
INTEGRITY = "Qiu7R+Cmh8CstZsY1uJOSWnVlfo7ZtNLV7mF8Jltk3LB3AtDu9cRZlcnRKkAk8Y4z6KKw35z7Y7Urd7jWY8etA=="
URL = f"https://registry.npmjs.org/three/-/three-{VERSION}.tgz"


def prepare(destination):
    with urllib.request.urlopen(URL, timeout=60) as response:
        raw = response.read(15*1024*1024+1)
    if base64.b64encode(hashlib.sha512(raw).digest()).decode() != INTEGRITY:
        raise RuntimeError("Three.js npm archive integrity mismatch")
    destination = Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    files = {"three.module.js":"package/build/three.module.js",
             "three.core.js":"package/build/three.core.js",
             "OrbitControls.js":"package/examples/jsm/controls/OrbitControls.js", "LICENSE":"package/LICENSE"}
    result={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as archive:
        for name, member in files.items():
            data=archive.extractfile(member).read()
            if name == "OrbitControls.js":
                data=data.replace(b"from 'three'",b"from './three.module.js'")
            (destination/name).write_bytes(data)
            result[name] = hashlib.sha256(data).hexdigest()
    return result


if __name__ == '__main__':
    import sys,json
    print(json.dumps({"version":VERSION,"files":prepare(sys.argv[1])},indent=2))
