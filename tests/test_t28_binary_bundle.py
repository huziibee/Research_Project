from __future__ import annotations
import json, tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from ambiguity_manager.model.t28_bundle import T28BundleError, binary_stats, build_manifest, canonical_json, first_difference, safe_extract, sha256_file, verify_archive, write_deterministic_tar_gz

class T28BinaryBundleTests(unittest.TestCase):
    def make_bundle(self, root: Path):
        (root/'a.bin').write_bytes(b'one\n\xc3\xa9\x00')
        (root/'b.jsonl').write_bytes(b'{"x":1}\n')
        m=build_manifest(root,[('a.bin','canonical_corpus','1'),('b.jsonl','train_manifest','1')]); mb=canonical_json(m); archive=root/'bundle.tar.gz'; write_deterministic_tar_gz(archive,root,mb,'bundle_manifest.json',m['members']); return m,archive
    def test_source_hash_and_binary_stats(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'x'; p.write_bytes(b'a\r\nb\rX\xc3\xa9\0')
            s=binary_stats(p); self.assertEqual(s['sha256'],sha256_file(p)); self.assertEqual(s['crlf_count'],1); self.assertEqual(s['standalone_cr_count'],1); self.assertFalse(s['ends_in_lf']); self.assertTrue(s['utf8_valid'])
    def test_archive_members_equal_source_bytes(self):
        with TemporaryDirectory() as d:
            root=Path(d); m,a=self.make_bundle(root); self.assertEqual(verify_archive(a,sha256_file(a),m)['status'],'VERIFY_PASSED')
    def test_archive_is_deterministic(self):
        with TemporaryDirectory() as d:
            root=Path(d); m,a=self.make_bundle(root); b=root/'second.tar.gz'; write_deterministic_tar_gz(b,root,canonical_json(m),'bundle_manifest.json',m['members']); self.assertEqual(a.read_bytes(),b.read_bytes())
    def test_extraction_preserves_bytes_and_is_immutable(self):
        with TemporaryDirectory() as d:
            root=Path(d); m,a=self.make_bundle(root); dest=root/'out'; result=safe_extract(a,dest,m,sha256_file(a)); self.assertEqual(result['status'],'VERIFY_PASSED'); self.assertEqual((dest/'a.bin').read_bytes(),(root/'a.bin').read_bytes()); self.assertTrue((dest/'VERIFY_PASSED.json').exists());
            with self.assertRaises(T28BundleError): safe_extract(a,dest,m,sha256_file(a))
    def test_wrong_archive_hash_and_stale_archive_rejected(self):
        with TemporaryDirectory() as d:
            root=Path(d); m,a=self.make_bundle(root)
            with self.assertRaises(T28BundleError): verify_archive(a,'0'*64,m)
            with self.assertRaises(T28BundleError): verify_archive(a,sha256_file(a),{**m,'members':[]})
    def test_mutation_types_detected(self):
        source=b'one\nlast'; self.assertEqual(first_difference(source,b'one\r\nlast')['offset'],3); self.assertEqual(first_difference(source,b'\xef\xbb\xbf'+source)['offset'],0); self.assertEqual(first_difference(source,source+b'\n')['offset'],len(source))
    def test_unexpected_and_missing_members_rejected(self):
        with TemporaryDirectory() as d:
            root=Path(d); m,a=self.make_bundle(root); bad=dict(m); bad['members']=m['members']+[{'path':'holdout.jsonl','role':'protected','byte_size':0,'sha256':'0'*64}]
            with self.assertRaises(T28BundleError): verify_archive(a,sha256_file(a),bad)
    def test_fixture_is_read_as_exact_binary(self):
        fixture=Path(__file__).parent/'fixtures'/'t28_binary_transport.hex'; b=bytes.fromhex(fixture.read_text(encoding='ascii').strip()); self.assertIn(b'\r\n',b); self.assertIn(b'\rX',b); self.assertIn(b'\0',b); self.assertIn('é'.encode(),b); self.assertTrue(b.endswith(b'\n'))

if __name__=='__main__': unittest.main()
