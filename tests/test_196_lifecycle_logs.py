"""Reconfigurar logs no deja archivos de la configuración anterior abiertos."""
from __future__ import annotations

import subprocess
import sys
import unittest


class TestLogs(unittest.TestCase):
    def test_reconfiguracion_cierra_solo_handlers_propios(self):
        script = '''
import io, logging, tempfile
from app.lifecycle import setup_logging
stream = io.StringIO()
ajeno = logging.StreamHandler(stream)
logging.getLogger().addHandler(ajeno)
with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
    setup_logging(a, console=False)
    viejos = list(logging.getLogger().handlers)
    assert not stream.closed
    assert all(h.stream is not None for h in viejos)
    setup_logging(b, console=False)
    assert all(h.stream is None for h in viejos)
    assert not stream.closed
    logging.getLogger().info('log nuevo')
'''
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
