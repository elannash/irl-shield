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
                         'Path(sys.argv[1]).write_text(json.dumps([os.getpid(),p.pid]));time.sleep(60)')
                shim=("import os,runpy,signal,sys\nreal=os.killpg\n"
                      "def injected(group,number):\n"
                      " if number==signal.SIGKILL: raise PermissionError('synthetic group permission denial')\n"
                      f" if number==signal.SIGTERM and {keep_alive!r}: return\n"
                      " return real(group,number)\nos.killpg=injected\n"
                      "script=sys.argv[1];sys.argv=[script,'0.5',sys.executable,'-c',sys.argv[2],sys.argv[3]]\n"
                      "runpy.run_path(script,run_name='__main__')")
                started=time.time()
                try:
                    result=subprocess.run([sys.executable,'-c',shim,str(ROOT/'scripts/bounded.py'),
                                           program,str(pidfile)],capture_output=True,timeout=10)
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
                program=('import subprocess,sys,time;from pathlib import Path;'
                         'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]);'
                         'Path(sys.argv[1]).write_text(str(p.pid));'+('time.sleep(60)' if wait else ''))
                result=subprocess.run([sys.executable,str(ROOT/'scripts/bounded.py'),'2',
                                       sys.executable,'-c',program,str(pidfile)],capture_output=True,timeout=8)
                self.assertEqual(result.returncode,expected,result.stderr.decode())
                pid=int(pidfile.read_text())
                deadline=time.monotonic()+1
                while time.monotonic()<deadline:
                    try:
                        process=psutil.Process(pid)
                        if process.status()==psutil.STATUS_ZOMBIE:
                            break
                    except psutil.NoSuchProcess:
                        break
                    time.sleep(.01)
                else:
                    os.kill(pid,9)
                    self.fail('Bounded command left a running descendant')
