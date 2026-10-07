"""Configuration boundaries for the fixed, private Db2 environment file."""
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch

from workbench import db2_env
from workbench.domain import ValidationError

# Public test-only certificate; never installed as a connection certificate.
CERTIFICATE = """-----BEGIN CERTIFICATE-----
MIIDKzCCAhOgAwIBAgIUQj2/wM0DbFsIn7t5bL6I3McCsf4wDQYJKoZIhvcNAQEL
BQAwJTEjMCEGA1UEAwwaZmljdGlvbmFsLWRiMi10ZXN0LmludmFsaWQwHhcNMjYx
MDA2MDQwODQ0WhcNMzYxMDAzMDQwODQ0WjAlMSMwIQYDVQQDDBpmaWN0aW9uYWwt
ZGIyLXRlc3QuaW52YWxpZDCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEB
AKhN0FyhjPeh7JcnlioWzC9Jz9Mz8pKcntNUlP7+dvyLm5o99M+VORSsB36zEm55
hGKRhLNgZrIL/L1VVc790jppGjzdLTN5kyI1U7l5A3pLWl3t6ETJsx24EJ8McyGj
mpsyok+9Miin4jyLX7/51KOUEYyYRxIvC5qdIqB1Ge0vcucsCByYVEU0tk7YTc7J
FlBX0/DPKVnNQp3sUvFubHlD6L0bJKA3KkUuS6S7gOnHe58XGoNcV8AU6C7ri7k1
scApoPIog1VyQqOb3iTghpdx4RHjedOFHv9LGmt7s5xc5z/3LdBReW8x6losIWxi
BTSURaihtfU5WUqGsJRPEOMCAwEAAaNTMFEwHQYDVR0OBBYEFDolnM5hRw5nkvY+
VGASVa/yt/RzMB8GA1UdIwQYMBaAFDolnM5hRw5nkvY+VGASVa/yt/RzMA8GA1Ud
EwEB/wQFMAMBAf8wDQYJKoZIhvcNAQELBQADggEBAHQ0I0vR4QK+aCDSm+xOLQ0r
C3i4RBSwUZJrDGEfKJEZ6rbeb6YibkEavfheZctPYguT8CPhrpIiCttT7wrbN23O
KUjaR8EFxFlgzWKZDnOUhSwoYbAr1+hferz5u/XlHROCMFg83eZZeND3ef9Bvnsk
R+SRkbYQZjIeZ6atyCL8ckn2fZEV7mUJnjPNvKKrtIv6wL6AFiFAUDOIGXbdt458
0y3/561Z8PdDmrcDWdcvPvz1SmgySIA4JS/V51XgrJJrbBERViPGjZtZKIvc00Aj
ql8Z+LkReXFeBFnm6m4T8Vqma9nHK7Nyi9cwKFNFJYo/TTEflb4+zR3aQbc23zo=
-----END CERTIFICATE-----
"""
BASE = """DB2_LOCATION_NAME=TESTLOC
DB2_HOSTNAME=db2.example.invalid
DB2_PORT=5116
DB2_DATABASE=TESTDB
# DB2_USERNAME=commented-user
DB2_PASSWORD=
DB2_SSL_CONNECTION=true
DB2_SSL_CERT_LOCATION=certs/test.cer
DB2_QUERY_ROW_LIMIT=
"""


class Db2EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.file = self.root / '.env'
        self.file.write_text(BASE)
        self.cert = self.root / 'certs/test.cer'
        self.cert.parent.mkdir()
        self.cert.write_text(CERTIFICATE)
        self.credentials = {'DB2_USERNAME': 'fictional-user', 'DB2_PASSWORD': 'fictional-secret'}

    def settings(self, env=None):
        return db2_env.settings({} if env is None else env, self.file)

    def connection(self, env=None):
        return db2_env.connection_string(self.credentials if env is None else env, self.file)

    def test_fields_comments_default_limit_and_private_representation(self):
        config = self.settings()
        self.assertEqual((config.location, config.database, config.host, config.port),
                         ('TESTLOC', 'TESTDB', 'db2.example.invalid', 5116))
        self.assertEqual(config.row_limit, 500000)
        self.assertTrue(config.ssl)
        self.assertEqual(config.certificate, self.cert)
        self.assertEqual(config.username, '')
        self.assertEqual(config.password, '')
        config = self.settings(self.credentials)
        self.assertNotIn('fictional-user', repr(config))
        self.assertNotIn('fictional-secret', repr(config))

    def test_default_path_is_module_relative_not_a_directory_search(self):
        expected = Path(db2_env.__file__).resolve().parents[1] / 'tools/dq3g_mcp/.env'
        self.assertEqual(db2_env.DEFAULT_ENV_FILE, expected)
        with patch('workbench.db2_env.DEFAULT_ENV_FILE', self.file), patch('os.getcwd', return_value='/unrelated'):
            self.assertEqual(db2_env.settings({}).database, 'TESTDB')

    def test_shell_overrides_including_empty_are_not_fallbacks(self):
        self.file.write_text(BASE.replace('DB2_PASSWORD=', 'DB2_PASSWORD=file-secret'))
        self.assertEqual(self.settings({'DB2_PASSWORD': ''}).password, '')
        with self.assertRaises(ValidationError):
            self.connection({'DB2_USERNAME': 'fictional', 'DB2_PASSWORD': ''})
        self.assertEqual(self.settings({'DB2_PORT': '5117'}).port, 5117)
        with self.assertRaises(ValidationError):
            self.settings({'DB2_PORT': ''})

    def test_quoted_hash_and_shell_metacharacters_remain_literal(self):
        value = 'a#b;$(touch should-not-exist)${HOME}`echo x`'
        self.file.write_text(BASE.replace('DB2_PASSWORD=', 'DB2_PASSWORD="' + value + '" # comment'))
        self.assertEqual(self.settings().password, value)
        self.assertFalse((self.root / 'should-not-exist').exists())

    def test_unquoted_inline_comments_and_crlf(self):
        self.file.write_bytes(BASE.replace('DB2_PORT=5116', 'DB2_PORT=5116 # comment')
                              .replace('DB2_PASSWORD=', 'DB2_PASSWORD=literal#hash')
                              .replace('\n', '\r\n').encode())
        self.assertEqual(self.settings().port, 5116)
        self.assertEqual(self.settings().password, 'literal#hash')

    def test_bad_syntax_unknown_duplicate_and_unclosed_quotes_rejected(self):
        for suffix in ('DB2_PORT=5116\n', 'UNKNOWN=private-value\n', 'export DB2_PORT=5116\n',
                       'DB2_USERNAME="unfinished\n', 'DB2_USERNAME="x" trailing\n'):
            with self.subTest(suffix=suffix):
                self.file.write_text(BASE + suffix)
                with self.assertRaises(ValidationError) as failure:
                    self.settings()
                self.assertNotIn('private-value', str(failure.exception))

    def test_invalid_encoding_controls_and_file_size_rejected(self):
        for content in (BASE.encode() + b'\xff', BASE.encode() + b'\x00', b'#' * (65536 + 1)):
            self.file.write_bytes(content)
            with self.assertRaises(ValidationError):
                self.settings()

    def test_row_cap_boundaries_and_blank(self):
        for raw, expected in (('', 500000), ('1', 1), ('500000', 500000)):
            self.assertEqual(self.settings({'DB2_QUERY_ROW_LIMIT': raw}).row_limit, expected)
        for raw in ('0', '-1', '500001', '1.0', '1e3', 'True'):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                self.settings({'DB2_QUERY_ROW_LIMIT': raw})

    def test_ssl_off_and_bad_nonsecret_values_fail_closed(self):
        for key, value in (('DB2_SSL_CONNECTION', 'false'), ('DB2_SSL_CONNECTION', ''),
                           ('DB2_SSL_CONNECTION', None), ('DB2_PASSWORD', None),
                           ('DB2_HOSTNAME', 'secret@bad'), ('DB2_PORT', '65536'),
                           ('DB2_PORT', '0'), ('DB2_DATABASE', ''), ('DB2_LOCATION_NAME', '')):
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError) as failure:
                self.settings({key: value})
            self.assertNotIn('secret@bad', str(failure.exception))

    def test_missing_file_can_be_fully_configured_by_shell(self):
        self.file.unlink()
        values = dict(line.split('=', 1) for line in BASE.splitlines() if line and not line.startswith('#'))
        self.assertEqual(self.settings(values).row_limit, 500000)
        with self.assertRaises(ValidationError):
            self.settings()

    def test_symlink_environment_file_and_parent_rejected(self):
        link = self.root / 'linked.env'
        link.symlink_to(self.file)
        with self.assertRaises(ValidationError):
            db2_env.settings({}, link)
        directory = self.root / 'linked-dir'
        directory.symlink_to(self.cert.parent, target_is_directory=True)
        (self.cert.parent / '.env').write_text(BASE)
        with self.assertRaises(ValidationError):
            db2_env.settings({}, directory / '.env')

    def test_certificate_traversal_absolute_and_symlink_rejected(self):
        for raw in ('../outside.cer', '/absolute.cer', 'C:\\outside.cer', 'certs/../test.cer'):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                self.settings({'DB2_SSL_CERT_LOCATION': raw})
        self.cert.unlink()
        self.cert.symlink_to(self.file)
        with self.assertRaises(ValidationError):
            self.settings()

    def test_missing_certificate_or_credentials_have_redacted_errors(self):
        with self.assertRaisesRegex(ValidationError, 'credentials'):
            self.connection({})
        self.cert.unlink()
        self.assertEqual(self.settings().certificate, self.cert)
        with self.assertRaises(ValidationError) as failure:
            self.connection()
        self.assertNotIn(str(self.cert), str(failure.exception))

    def test_actual_pem_der_validation_without_rewriting(self):
        pem = self.cert.read_bytes()
        connection = self.connection()
        self.assertIn('SECURITY={SSL}', connection)
        self.assertIn('SSLClientHostnameValidation={Basic}', connection)
        self.assertEqual(self.cert.read_bytes(), pem)
        der = ssl.PEM_cert_to_DER_cert(CERTIFICATE)
        self.cert.write_bytes(der)
        self.assertIn('SSLServerCertificate={' + str(self.cert) + '}', self.connection())
        self.assertEqual(self.cert.read_bytes(), der)

    def test_invalid_certificate_and_der_trailing_data_rejected(self):
        for content in (b'PLACEHOLDER', b'-----BEGIN CERTIFICATE-----\ninvalid\n-----END CERTIFICATE-----',
                        ssl.PEM_cert_to_DER_cert(CERTIFICATE) + b'garbage',
                        CERTIFICATE.encode() + b'private trailing data'):
            with self.subTest(content=content[:20]):
                self.cert.write_bytes(content)
                with self.assertRaises(ValidationError) as failure:
                    self.connection()
                self.assertNotIn('private trailing data', str(failure.exception))

    def test_odbc_escaping_no_location_parameter_and_credential_bounds(self):
        connection = self.connection({'DB2_USERNAME': 'user;X=}', 'DB2_PASSWORD': 'secret;PWD=bad}'})
        self.assertIn('UID={user;X=}}}', connection)
        self.assertIn('PWD={secret;PWD=bad}}}', connection)
        self.assertNotIn('LOCATION', connection)
        self.assertIn('DRIVER={IBM DB2 ODBC DRIVER}', connection)
        for value in ('bad\nsecret', 'x' * 8193):
            with self.assertRaises(ValidationError) as failure:
                self.connection({'DB2_USERNAME': 'fictional', 'DB2_PASSWORD': value})
            self.assertNotIn(value, str(failure.exception))


if __name__ == '__main__':
    unittest.main()
