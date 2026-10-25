import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name("probe_mount.py")
if MODULE_PATH.exists():
    SPEC = importlib.util.spec_from_file_location("workspace_mount_probe", MODULE_PATH)
    PROBE = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(PROBE)
else:
    PROBE = None


class MountProbeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(PROBE, "The native filesystem deployment probe is missing.")

    def test_probe_checks_lock_conflicts_and_atomic_replacement_then_removes_only_its_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preserved = root / "existing.md"
            preserved.write_text("Existing user data")
            result = PROBE.run_probe(root, require_nfs=False)
            self.assertTrue(result["ok"])
            self.assertTrue(result["lockConflict"])
            self.assertTrue(result["lockRelease"])
            self.assertTrue(result["atomicReplacement"])
            self.assertTrue(result["exactUtf8"])
            self.assertFalse(result["retained"])
            self.assertEqual(list(root.iterdir()), [preserved])
            self.assertEqual(preserved.read_text(), "Existing user data")

    def test_retained_fixture_uses_the_runtime_project_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = PROBE.run_probe(root, require_nfs=False, keep=True)
            self.assertTrue(result["retained"])
            self.assertRegex(result["ownerKey"], r"^[a-f0-9]{64}$")
            self.assertRegex(result["workspaceId"], r"^[a-f0-9-]{36}$")
            fixture = root / result["ownerKey"] / result["workspaceId"] / "files" / result["path"]
            self.assertEqual(fixture.read_bytes(), result["content"].encode("utf-8"))
            self.assertEqual(fixture.stat().st_mode & 0o777, 0o600)

    def test_default_probe_rejects_a_local_directory_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "NFS"):
                PROBE.run_probe(Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
