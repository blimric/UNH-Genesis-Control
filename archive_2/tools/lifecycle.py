"""Per-subsystem ownership; does not manage hardware."""
import fcntl
import json
import os
from pathlib import Path
import subprocess


def identity(pid):
    result=subprocess.run(['ps','-p',str(pid),'-o','lstart=','-o','command='],capture_output=True,text=True)
    return result.stdout.strip() if result.returncode==0 else ''


def active(output):
    try:
        state=json.loads((Path(output)/'.runtime/recorder.json').read_text())
        return state if state['identity']==identity(state['pid']) else None
    except (OSError,ValueError,KeyError):return None


class Lease:
    def __init__(self,output):
        root=Path(output)/'.runtime';root.mkdir(parents=True,exist_ok=True)
        self.state=root/'recorder.json';self.handle=(root/'recorder.lock').open('a+')
        try:fcntl.flock(self.handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close();raise RuntimeError('Recorder already owns this subsystem output') from None

    def ready(self):
        temporary=self.state.with_suffix('.tmp')
        temporary.write_text(json.dumps({'pid':os.getpid(),'identity':identity(os.getpid())}))
        temporary.replace(self.state)

    def close(self):
        try:self.state.unlink(missing_ok=True)
        finally:self.handle.close()
