import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import psutil

ROOT=Path(__file__).resolve().parents[1]


class ProcessDeadline(unittest.TestCase):
    def test_permission_error_is_ignored_only_after_group_members_have_exited(self):
        (ROOT/'.tmp').mkdir(exist_ok=True)
        for keep_alive,expected in [(False,124),(True,1)]:
            with self.subTest(live=keep_alive),tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
                pidfile=Path(folder)/'owned.json'
                program=('import os,subprocess,sys,time,json;from pathlib import Path;os.close(1);os.close(2);'
                         'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]);'
                         "pending=Path(sys.argv[1]+'.tmp');pending.write_text(json.dumps([os.getpid(),p.pid]));"
                         'os.replace(pending,sys.argv[1]);time.sleep(60)')
                # This case tests cleanup permissions. Start its short deadline
                # only once the controlled process group reports readiness.
                shim=("import os,runpy,signal,subprocess,sys,time\nfrom pathlib import Path\n"
                      "real=os.killpg\nstart=subprocess.Popen\nmarker=Path(sys.argv[3])\n"
                      "def ready(*args,**kwargs):\n"
                      " child=start(*args,**kwargs)\n"
                      " if kwargs.get('start_new_session'):\n"
                      "  deadline=time.monotonic()+10\n"
                      "  while not marker.exists() and child.poll() is None:\n"
                      "   if time.monotonic()>=deadline:\n"
                      "    try: real(child.pid,signal.SIGKILL)\n"
                      "    except ProcessLookupError: pass\n"
                      "    child.wait(timeout=3)\n"
                      "    raise RuntimeError('Controlled group did not become ready')\n"
                      "   time.sleep(.01)\n"
                      " return child\nsubprocess.Popen=ready\n"
                      "def injected(group,number):\n"
                      " if number==signal.SIGKILL: raise PermissionError('synthetic group permission denial')\n"
                      f" if number==signal.SIGTERM and {keep_alive!r}: return\n"
                      " return real(group,number)\nos.killpg=injected\n"
                      "script=sys.argv[1];sys.argv=[script,'0.5',sys.executable,'-c',sys.argv[2],sys.argv[3]]\n"
                      "runpy.run_path(script,run_name='__main__')")
                started=time.time()
                try:
                    result=subprocess.run([sys.executable,'-c',shim,str(ROOT/'scripts/bounded.py'),
                                           program,str(pidfile)],capture_output=True,timeout=20)
                    self.assertTrue(pidfile.exists(),'Controlled child never started')
                    self.assertEqual(result.returncode,expected,result.stderr.decode())
                    if keep_alive:
                        self.assertIn('PermissionError',result.stderr.decode())
                finally:
                    if pidfile.exists():
                        for pid in json.loads(pidfile.read_text()):
                            try:
                                process=psutil.Process(pid)
                                if process.status()!=psutil.STATUS_ZOMBIE:
                                    self.assertGreaterEqual(process.create_time(),started-1)
                                    process.kill()
                                    try:process.wait(timeout=1)
                                    except psutil.TimeoutExpired:pass
                            except psutil.NoSuchProcess:
                                pass

    def test_descendants_exit_on_timeout_and_normal_leader_exit(self):
        (ROOT/'.tmp').mkdir(exist_ok=True)
        for wait,expected in [(True,124),(False,0)]:
            with self.subTest(wait=wait),tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
                pidfile=Path(folder)/'grandchild.pid'
                release=Path(folder)/'release'
                program=("import os,subprocess,sys,time;from pathlib import Path;"
                         'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);'
                         "pending=Path(sys.argv[1]+'.tmp');pending.write_text(str(p.pid));"
                         "os.replace(pending,sys.argv[1]);"
                         "\nwhile not Path(sys.argv[2]).exists(): time.sleep(.01)\n"+
                         ('time.sleep(60)' if wait else ''))
                # Start the deadline only after the descendant is published and
                # the test holds its identity; setup is not the timed behavior.
                shim=("import os,runpy,signal,subprocess,sys,time\nfrom pathlib import Path\n"
                      "start=subprocess.Popen;release=Path(sys.argv[4])\n"
                      "def ready(*args,**kwargs):\n"
                      " child=start(*args,**kwargs)\n"
                      " if kwargs.get('start_new_session'):\n"
                      "  deadline=time.monotonic()+10\n"
                      "  while not release.exists() and child.poll() is None:\n"
                      "   if time.monotonic()>=deadline:\n"
                      "    os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=3)\n"
                      "    raise RuntimeError('Descendant identity was not acknowledged')\n"
                      "   time.sleep(.01)\n"
                      " return child\nsubprocess.Popen=ready\n"
                      "script=sys.argv[1];sys.argv=[script,'2',sys.executable,'-c',sys.argv[2],sys.argv[3],sys.argv[4]]\n"
                      "runpy.run_path(script,run_name='__main__')")
                process=None
                with subprocess.Popen([sys.executable,'-c',shim,str(ROOT/'scripts/bounded.py'),
                                       program,str(pidfile),str(release)],
                                      stdout=subprocess.PIPE,stderr=subprocess.PIPE) as command:
                    try:
                        deadline=time.monotonic()+10
                        while time.monotonic()<deadline and command.poll() is None:
                            try:
                                text=pidfile.read_text()
                                if text.isdecimal() and int(text)>0:
                                    process=psutil.Process(int(text))
                                    process.create_time()  # Cache identity before the leader can exit.
                                    break
                            except FileNotFoundError:
                                pass
                            time.sleep(.01)
                        self.assertIsNotNone(process,'Descendant did not publish a complete PID')
                        release.touch()
                        _,stderr=command.communicate(timeout=8)
                        self.assertEqual(command.returncode,expected,stderr.decode())
                        deadline=time.monotonic()+1
                        while time.monotonic()<deadline:
                            try:
                                if not process.is_running() or process.status()==psutil.STATUS_ZOMBIE:
                                    break
                            except psutil.NoSuchProcess:
                                break
                            time.sleep(.01)
                        else:
                            self.fail('Bounded command left a running descendant')
                    finally:
                        release.touch()
                        if command.poll() is None:
                            command.terminate()
                            command.communicate(timeout=8)
                        if process is not None and process.is_running():
                            try:
                                if process.status()!=psutil.STATUS_ZOMBIE:
                                    process.kill()
                                    process.wait(timeout=3)
                            except psutil.NoSuchProcess:
                                pass
