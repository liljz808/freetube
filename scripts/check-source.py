#!/usr/bin/env python3
"""Fail CI if the removed private-UIKit dependency chain returns."""
import json
import plistlib
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
project = root / 'FreeTube/FreeTube.xcodeproj'
source = root / 'FreeTube/FreeTube'
pbx = (project / 'project.pbxproj').read_text()
lock = json.loads((project / 'project.xcworkspace/xcshareddata/swiftpm/Package.resolved').read_text())
for text in [pbx, json.dumps(lock)] + [p.read_text() for p in source.rglob('*.swift')]:
    # Strip source comments, which may document historical problems.
    text = re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)
    assert not re.search(r'LNPopup|lnpopup|LNSwiftUIUtils|lnswiftuiutils', text), 'Popup dependency returned'
    assert not re.search(r'_frameForHostedAccessoryView|_hostedElementLayoutResolver', text)
with (source / 'Info.plist').open('rb') as f:
    info = plistlib.load(f)
assert {'audio', 'processing'} <= set(info['UIBackgroundModes'])
assert 'com.leshko.freetube.resume-downloads' in info['BGTaskSchedulerPermittedIdentifiers']
assert info['UIFileSharingEnabled']
print('SOURCE CHECK PASSED: popup chain removed; background declarations present')
