#!/usr/bin/env python3
"""Validate a device IPA's layout, arm64 images, platform and embedded dependencies.

This is package inspection, never a substitute for launching on a real device.
Uses only the Python standard library, including when running on Linux.
"""
import argparse
import json
import plistlib
import posixpath
import struct
import zipfile
from pathlib import Path

ARM64 = 0x0100000C
MAGICS = (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf')


def macho_arm64(data):
    """Read device load commands from an arm64 Mach-O (thin or big-endian fat)."""
    if data[:4] in MAGICS[1:]:
        count = struct.unpack_from('>I', data, 4)[0]
        wide = data[:4] == MAGICS[2]
        size = 32 if wide else 20
        for i in range(count):
            at = 8 + i * size
            cpu = struct.unpack_from('>I', data, at)[0]
            offset, length = struct.unpack_from('>QQ' if wide else '>II', data, at + 8)
            if cpu == ARM64:
                return macho_arm64(data[offset:offset + length])
        raise ValueError('Mach-O has no arm64 slice')
    if data[:4] != MAGICS[0] or len(data) < 32:
        raise ValueError('Not a supported 64-bit Mach-O')
    _, cpu, _, kind, count, commands_size, _, _ = struct.unpack_from('<8I', data)
    if cpu != ARM64:
        raise ValueError('Mach-O is not arm64')
    if 32 + commands_size > len(data):
        raise ValueError('Truncated Mach-O load commands')
    dependencies, rpaths = [], []
    platform = None
    at = 32
    for _ in range(count):
        cmd, size = struct.unpack_from('<II', data, at)
        if size < 8 or at + size > 32 + commands_size:
            raise ValueError('Invalid Mach-O load command')
        if cmd in (0xC, 0x80000018, 0x8000001F, 0x80000023, 0x8000001C):
            offset = struct.unpack_from('<I', data, at + 8)[0]
            if not 12 <= offset < size:
                raise ValueError('Invalid Mach-O string offset')
            value = data[at + offset:at + size].split(b'\0', 1)[0].decode()
            if cmd == 0x8000001C:
                rpaths.append(value)
            else:
                dependencies.append(value)
        elif cmd == 0x32:  # LC_BUILD_VERSION; PLATFORM_IOS == 2, SIMULATOR == 7
            platform = struct.unpack_from('<I', data, at + 8)[0]
        elif cmd == 0x25 and platform is None:  # LC_VERSION_MIN_IPHONEOS
            platform = 2
        at += size
    if platform != 2:
        raise ValueError(f'Mach-O platform is {platform}, expected iOS device (2)')
    return {'filetype': kind, 'dependencies': dependencies, 'rpaths': rpaths}


def verify_ipa(path):
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = {i.filename for i in infos}
        if len(names) != len(infos):
            raise ValueError('Duplicate archive entries')
        for name in names:
            if name.startswith('/') or '..' in name.split('/'):
                raise ValueError('Unsafe archive path')
            if 'LNPopup' in name or 'LNSwiftUIUtils' in name:
                raise ValueError('Removed popup framework is still packaged')
        apps = {name.split('/')[1] for name in names
                if name.startswith('Payload/') and len(name.split('/')) >= 3
                and name.split('/')[1].endswith('.app')}
        if len(apps) != 1:
            raise ValueError('Expected one .app inside Payload/')
        app = 'Payload/' + apps.pop()
        info = plistlib.loads(archive.read(app + '/Info.plist'))
        for key in ('CFBundleIdentifier', 'CFBundleExecutable', 'CFBundleVersion',
                    'CFBundleShortVersionString', 'MinimumOSVersion'):
            if not info.get(key):
                raise ValueError(f'Missing Info.plist key: {key}')
        if info.get('CFBundlePackageType') != 'APPL':
            raise ValueError('Bundle is not an application')
        if info.get('CFBundleSupportedPlatforms') != ['iPhoneOS']:
            raise ValueError('Not an iPhoneOS build')
        if not {'audio', 'processing'} <= set(info.get('UIBackgroundModes', [])):
            raise ValueError('Background audio / processing declaration missing')
        if not info.get('UIFileSharingEnabled'):
            raise ValueError('Download file sharing missing')
        executable = app + '/' + info['CFBundleExecutable']
        if executable not in names:
            raise ValueError('App executable missing')
        if not (archive.getinfo(executable).external_attr >> 16) & 0o111:
            raise ValueError('App executable has no execute permission')
        images = {}
        for name in sorted(names):
            if name.endswith('/'):
                continue
            with archive.open(name) as f:
                magic = f.read(4)
            if magic not in MAGICS:
                continue
            data = archive.read(name)
            if any(token in data for token in
                   (b'LNPopup', b'_frameForHostedAccessoryView', b'_hostedElementLayoutResolver')):
                raise ValueError(f'Restricted popup implementation found in {name}')
            images[name] = macho_arm64(data)
        if executable not in images or images[executable]['filetype'] != 2:
            raise ValueError('App executable is not an arm64 MH_EXECUTE image')

        def expand(value, loader):
            return value.replace('@executable_path', app).replace('@loader_path', loader)

        for name, image in images.items():
            loader = posixpath.dirname(name)
            paths = [expand(r, loader) for r in image['rpaths']]
            paths += [app + '/Frameworks']  # Standard inherited app runpath.
            for dep in image['dependencies']:
                if dep.startswith(('/System/Library/', '/usr/lib/')):
                    continue
                # Swift's standard runtime ships with iOS 17+, the minimum target.
                if dep.startswith('@rpath/libswift') and dep.endswith('.dylib'):
                    continue
                if dep.startswith('@rpath/'):
                    candidates = [posixpath.normpath(p + '/' + dep[7:]) for p in paths]
                else:
                    candidates = [posixpath.normpath(expand(dep, loader))]
                if not any(candidate in images for candidate in candidates):
                    raise ValueError(f'Missing embedded dependency for {name}: {dep}')
        return {
            'package_verification': 'passed', 'device_launch': 'NOT_TESTED',
            'app': app, 'bundle_id': info['CFBundleIdentifier'],
            'minimum_os': info['MinimumOSVersion'], 'architecture': 'arm64',
            'background_modes': info['UIBackgroundModes'],
            'macho_images': images,
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify_ipa(args.ipa)
    report = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(report)
    print(report)
