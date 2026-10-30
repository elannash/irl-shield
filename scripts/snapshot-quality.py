#!/usr/bin/env python3
"""Freeze a private source copy while the main mirror continues performance work."""
from pathlib import Path
import re
import shutil
import sys

root=Path(__file__).resolve().parents[1]
name=sys.argv[1]
if not re.fullmatch(r'[a-zA-Z0-9_-]+',name):
    raise ValueError('Snapshot name must be a simple identifier')
target=root/'.tmp'/name
target.mkdir(parents=True,exist_ok=False)
ignore=shutil.ignore_patterns('cache','.venv*','__pycache__')
for directory in ['bench','shield','fixtures','models','Sources','scripts']:
    shutil.copytree(root/directory,target/directory,ignore=ignore)
for path in root.glob('requirements*.txt'):
    shutil.copy2(path,target/path.name)
for directory in ['models','fixtures']:
    (target/directory/'cache').symlink_to(root/directory/'cache',target_is_directory=True)
(target/'.venv').symlink_to(root/'.venv',target_is_directory=True)
(target/'out').symlink_to(root/'out',target_is_directory=True)
(target/'.build').mkdir()
shutil.copy2(root/'.build/vision-bridge',target/'.build/vision-bridge')
print(target)
