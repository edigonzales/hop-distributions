from pathlib import Path
import tempfile
import unittest
from run_e2e import runtime_libraries

class RuntimeClasspathTests(unittest.TestCase):
    def test_only_host_swt_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            hop=Path(directory)
            for folder in ['core','spark-client','swt/win64','swt/osx/arm64','swt/osx/x86_64','swt/linux/arm64','swt/linux/x86_64']:
                path=hop/'lib'/folder;path.mkdir(parents=True)
                (path/('swt.jar' if folder.startswith('swt/') else 'hop.jar')).touch()
            for system,machine,expected in [('linux','x86_64','linux/x86_64'),('linux','aarch64','linux/arm64'),('darwin','arm64','osx/arm64'),('darwin','x86_64','osx/x86_64'),('win32','AMD64','win64')]:
                with self.subTest(system=system,machine=machine):
                    jars=runtime_libraries(hop,system,machine)
                    self.assertEqual([p for p in jars if p.name=='swt.jar'],[hop/'lib/swt'/expected/'swt.jar'])
                    self.assertEqual(len(jars),3)
