#!/usr/bin/env python3
"""Bound one command and its whole process group, including abnormal parent exits."""
import os
import signal
import subprocess
import sys


def signal_group(group,number):
    try:
        os.killpg(group,number)
    except ProcessLookupError:
        return
    except PermissionError:
        # macOS may retain an unsignalable zombie-only group after TERM/reaping.
        # A denial for any live member remains an error; never retry another signal.
        listing=subprocess.run(['ps','-axo','pgid=,stat='],capture_output=True,text=True,check=True)
        states=[parts[1] for line in listing.stdout.splitlines()
                if (parts:=line.split()) and int(parts[0])==group]
        if any(not state.startswith('Z') for state in states):
            raise


def main():
    seconds=float(sys.argv[1])
    if seconds<=0 or len(sys.argv)<3:
        raise ValueError('usage: bounded.py seconds command [args...]')
    child=None
    def interrupted(number,frame):
        raise SystemExit(128+number)
    for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP,signal.SIGALRM):
        signal.signal(number,interrupted)
    try:
        child=subprocess.Popen(sys.argv[2:],start_new_session=True)
        try:
            code=child.wait(timeout=seconds)
            return code if code>=0 else 128-code
        except subprocess.TimeoutExpired:
            print('Command exceeded its process-group deadline',file=sys.stderr)
            return 124
    finally:
        if child is not None:
            signal_group(child.pid,signal.SIGTERM)
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            signal_group(child.pid,signal.SIGKILL)
            child.wait(timeout=3)


if __name__=='__main__':
    sys.exit(main())
