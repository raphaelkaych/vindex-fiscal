import sqlite3,tempfile
from contextlib import closing
from pathlib import Path
from cryptography.fernet import Fernet,InvalidToken
from django.test import SimpleTestCase,override_settings
from portal.services import sqlite_backup


class SQLiteSnapshotTests(SimpleTestCase):
    def test_online_wal_roundtrip_and_refusal_to_replace(self):
        with tempfile.TemporaryDirectory() as folder,override_settings(CERTIFICATE_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            folder=Path(folder);source=folder/'source.sqlite3';archive=folder/'copy.vdb';dest=folder/'dest.sqlite3'
            with closing(sqlite3.connect(source)) as db:
                db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE sample(value TEXT)');db.execute("INSERT INTO sample VALUES ('FICTICIO-SOMENTE-TESTE')");db.commit()
                sqlite_backup.create(source,archive);sqlite_backup.verify(archive)
                self.assertNotIn(b'FICTICIO-SOMENTE-TESTE',archive.read_bytes())
                sqlite_backup.restore(archive,dest)
                with closing(sqlite3.connect(dest)) as copy:self.assertEqual(copy.execute('SELECT value FROM sample').fetchone()[0],'FICTICIO-SOMENTE-TESTE')
                with self.assertRaises(ValueError):sqlite_backup.restore(archive,source)
                with self.assertRaises(ValueError):sqlite_backup.create(source,archive)
    def test_tamper_missing_source_and_wrong_key_leave_target_absent(self):
        with tempfile.TemporaryDirectory() as folder,override_settings(CERTIFICATE_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            folder=Path(folder);source=folder/'source.sqlite3';archive=folder/'copy.vdb';dest=folder/'dest.sqlite3'
            with self.assertRaises(ValueError):sqlite_backup.create(source,archive)
            with closing(sqlite3.connect(source)) as db:db.execute('CREATE TABLE sample(value TEXT)');db.commit()
            sqlite_backup.create(source,archive)
            raw=archive.read_bytes();archive.write_bytes(raw[:-8])
            with self.assertRaises((ValueError,InvalidToken)):sqlite_backup.restore(archive,dest)
            self.assertFalse(dest.exists())
