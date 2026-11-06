"""Regression tests for package validation using synthetic headers, not app builds."""
import importlib.util
import plistlib
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('verify_ipa', Path(__file__).resolve().parents[1] / 'scripts/verify-ipa.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def image(platform=2, cpu=verifier.ARM64, dependencies=(), kind=2):
    commands = [struct.pack('<6I', 0x32, 24, platform, 0, 0, 0)]
    for dep in dependencies:
        value = dep.encode() + b'\0'
        size = (24 + len(value) + 7) // 8 * 8
        commands.append(struct.pack('<6I', 0xC, size, 24, 0, 0, 0) + value.ljust(size - 24, b'\0'))
    payload = b''.join(commands)
    return struct.pack('<8I', 0xFEEDFACF, cpu, 0, kind, len(commands), len(payload), 0, 0) + payload


class PackageValidationTests(unittest.TestCase):
    def package(self, binary=None, extra=None, info_changes=None, executable_mode=0o100755):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'synthetic-test-only.zip'
        info = {
            'CFBundleIdentifier': 'test.freetube', 'CFBundleExecutable': 'FreeTube',
            'CFBundleVersion': '1', 'CFBundleShortVersionString': '1.0',
            'MinimumOSVersion': '17.0', 'CFBundlePackageType': 'APPL',
            'CFBundleSupportedPlatforms': ['iPhoneOS'],
            'UIBackgroundModes': ['audio', 'processing'], 'UIFileSharingEnabled': True,
        }
        info.update(info_changes or {})
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('Payload/FreeTube.app/Info.plist', plistlib.dumps(info))
            entry = zipfile.ZipInfo('Payload/FreeTube.app/FreeTube')
            entry.external_attr = executable_mode << 16
            archive.writestr(entry, image() if binary is None else binary)
            for name, data in (extra or {}).items():
                archive.writestr(name, data)
        return path

    def test_device_package_passes_without_claiming_device_test(self):
        result = verifier.verify_ipa(self.package())
        self.assertEqual(result['package_verification'], 'passed')
        self.assertEqual(result['device_launch'], 'NOT_TESTED')

    def test_rejects_simulator_arm64(self):
        with self.assertRaisesRegex(ValueError, 'platform'):
            verifier.verify_ipa(self.package(image(platform=7)))

    def test_rejects_wrong_architecture(self):
        with self.assertRaisesRegex(ValueError, 'arm64'):
            verifier.verify_ipa(self.package(image(cpu=0x01000007)))

    def test_rejects_missing_framework(self):
        with self.assertRaisesRegex(ValueError, 'Missing embedded dependency'):
            verifier.verify_ipa(self.package(image(dependencies=['@rpath/Python.framework/Python'])))

    def test_accepts_embedded_dependency(self):
        verifier.verify_ipa(self.package(image(dependencies=['@rpath/Python.framework/Python']), {
            'Payload/FreeTube.app/Frameworks/Python.framework/Python': image(kind=6),
        }))

    def test_rejects_simulator_embedded_framework(self):
        with self.assertRaisesRegex(ValueError, 'platform'):
            verifier.verify_ipa(self.package(image(), {
                'Payload/FreeTube.app/Frameworks/Python.framework/Python': image(kind=6, platform=7),
            }))

    def test_rejects_removed_popup_implementation(self):
        with self.assertRaisesRegex(ValueError, 'Restricted popup'):
            verifier.verify_ipa(self.package(image() + b'_frameForHostedAccessoryView\0'))

    def test_rejects_missing_background_audio(self):
        with self.assertRaisesRegex(ValueError, 'Background audio'):
            verifier.verify_ipa(self.package(info_changes={'UIBackgroundModes': ['processing']}))

    def test_rejects_non_executable_binary(self):
        with self.assertRaisesRegex(ValueError, 'execute permission'):
            verifier.verify_ipa(self.package(executable_mode=0o100644))

    def test_rejects_unsafe_archive(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe archive'):
            verifier.verify_ipa(self.package(extra={'../outside': b'x'}))

    def test_rejects_truncated_load_commands(self):
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            verifier.macho_arm64(image()[:-1])

    def test_accepts_arm64_fat_device(self):
        thin = image()
        fat = struct.pack('>7I', 0xCAFEBABE, 1, verifier.ARM64, 0, 28, len(thin), 0) + thin
        self.assertEqual(verifier.macho_arm64(fat)['filetype'], 2)


if __name__ == '__main__':
    unittest.main()
