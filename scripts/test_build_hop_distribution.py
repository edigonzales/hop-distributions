import json
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build_hop_distribution as builder


class DistributionTests(unittest.TestCase):
    def test_distribution_config_includes_raster_type(self):
        config_path = Path(__file__).resolve().parents[1] / 'distribution.json'
        config = json.loads(config_path.read_text())
        plugins = config['plugins']
        geometry_index = next(
            index for index, plugin in enumerate(plugins)
            if plugin['artifact'] == 'hop-geometry-type-plugin'
        )
        self.assertEqual(
            plugins[geometry_index + 1],
            {
                'artifact': 'hop-raster-type-plugin',
                'root': 'plugins/misc/hop-raster-type',
                'version': '0.1.0-SNAPSHOT',
            },
        )

    def test_snapshot_selects_latest_unclassified_zip(self):
        metadata = b'''<metadata><versioning><snapshotVersions>
          <snapshotVersion><extension>zip</extension><value>0.1.0-20260910.100000-1</value><updated>20260910100000</updated></snapshotVersion>
          <snapshotVersion><extension>zip</extension><value>0.1.0-20260911.100000-2</value><updated>20260911100000</updated></snapshotVersion>
          <snapshotVersion><extension>zip</extension><classifier>sources</classifier><value>wrong</value><updated>20260912100000</updated></snapshotVersion>
        </snapshotVersions></versioning></metadata>'''
        self.assertEqual(builder.resolve_snapshot(metadata, 'plugin'), '0.1.0-20260911.100000-2')

    def test_missing_zip_fails(self):
        with self.assertRaises(builder.BuildError):
            builder.resolve_snapshot(b'<metadata/>', 'plugin')

    def test_unsafe_archive_paths(self):
        for name in ('../evil', '/etc/file', 'C:/file', '..\\file'):
            with self.subTest(name=name), self.assertRaises(builder.BuildError):
                builder.normalize_zip_entry_name(name)

    def make_archive(self, path, entries):
        with zipfile.ZipFile(path, 'w') as archive:
            for name, value in entries.items():
                archive.writestr(name, value)

    def runtime_entries(self):
        return {
            'hop/plugins/misc/hop-geometry-type/hop-geometry-type-0.2.jar': b'geometry',
            'hop/plugins/misc/hop-geometry-type/lib/jts-core-1.20.jar': b'jts',
            'hop/plugins/misc/hop-geometry-type/lib/gt-main-35.1.jar': b'geotools',
            'hop/plugins/misc/hop-geometry-type/lib/imagen-core-0.9.2.jar': b'imagen',
            'hop/plugins/misc/hop-raster-type/hop-raster-type-0.1.jar': b'raster-type',
            'hop/plugins/misc/hop-raster-type/lib/hop-raster-core-0.1.jar': b'raster-core',
            'hop/plugins/transforms/vector-raster/dependencies.xml': b'<dependencies><folder>../../misc/hop-raster-type</folder><folder>../../misc/hop-raster-type/lib</folder></dependencies>',
        }

    def test_runtime_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp)/'runtime.zip'
            entries = self.runtime_entries()
            self.make_archive(archive, entries)
            builder.validate_runtime(archive)
            entries['hop/plugins/transforms/vector-raster/lib/jts-core-1.20.jar'] = b'copy'
            self.make_archive(archive, entries)
            with self.assertRaisesRegex(builder.BuildError, 'outside central Geometry Type'):
                builder.validate_runtime(archive)

    def test_missing_raster_type_lib_reference_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp)/'runtime.zip'
            entries = self.runtime_entries()
            entries['hop/plugins/transforms/vector-raster/dependencies.xml'] = b'<dependencies><folder>../../misc/hop-raster-type</folder></dependencies>'
            self.make_archive(archive, entries)
            with self.assertRaisesRegex(builder.BuildError, 'exactly the central Raster Type'):
                builder.validate_runtime(archive)

    def test_direct_geometry_dependency_reference_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp)/'runtime.zip'
            entries = self.runtime_entries()
            entries['hop/plugins/transforms/vector-raster/dependencies.xml'] = b'<dependencies><folder>../../misc/hop-raster-type</folder><folder>../../misc/hop-raster-type/lib</folder><folder>../../misc/hop-geometry-type</folder></dependencies>'
            self.make_archive(archive, entries)
            with self.assertRaisesRegex(builder.BuildError, 'exactly the central Raster Type'):
                builder.validate_runtime(archive)

    def test_shared_runtime_outside_its_owner_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp)/'runtime.zip'
            entries = self.runtime_entries()
            entries['hop/plugins/transforms/vector-raster/lib/gt-main-35.1.jar'] = b'copy'
            self.make_archive(archive, entries)
            with self.assertRaisesRegex(builder.BuildError, 'outside central Geometry Type'):
                builder.validate_runtime(archive)

            entries = self.runtime_entries()
            entries['hop/plugins/transforms/vector-raster/lib/hop-raster-core-0.1.jar'] = b'copy'
            self.make_archive(archive, entries)
            with self.assertRaisesRegex(builder.BuildError, 'outside central Raster Type'):
                builder.validate_runtime(archive)

    def test_imagen_registry_outside_geometry_type_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp)/'runtime.zip'
            entries = self.runtime_entries()
            nested = io.BytesIO()
            with zipfile.ZipFile(nested, 'w') as jar:
                jar.writestr('META-INF/registryFile.imagen', 'descriptor fixture')
            entries['hop/plugins/transforms/vector-raster/lib/affine-0.9.2.jar'] = nested.getvalue()
            self.make_archive(archive, entries)
            with self.assertRaisesRegex(builder.BuildError, 'Imagen registry outside'):
                builder.validate_runtime(archive)

    def test_merge_preserves_launchers_and_rejects_overlapping_plugins(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            hop, plugin, output = root/'hop.zip', root/'plugin.zip', root/'out.zip'
            self.make_archive(hop, {'hop/lib/core.jar': b'core'})
            with zipfile.ZipFile(hop, 'a') as archive:
                info = zipfile.ZipInfo('hop/hop-run.sh')
                info.external_attr = 0o100755 << 16
                archive.writestr(info, b'#!/bin/sh\n')
            self.make_archive(plugin, {'plugins/transforms/example/plugin.jar': b'plugin'})
            item = builder.PluginArchive(plugin, 'plugins/transforms/example/')
            builder.build_distribution_archive(hop_zip_path=hop, plugin_archives=[item], output_path=output)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.getinfo('hop/hop-run.sh').external_attr >> 16, 0o100755)
                self.assertEqual(archive.read('hop/plugins/transforms/example/plugin.jar'), b'plugin')
            with self.assertRaisesRegex(builder.BuildError, 'overlap'):
                builder.merge_zip_archives(hop_zip_path=hop, plugin_archives=[item,item], output_path=output)

    def test_build_records_resolved_inputs_and_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            hop=root/'hop.zip'
            self.make_archive(hop, {'hop/lib/core.jar':b'core'})
            entries=self.runtime_entries()
            config={'distribution_version':'0.2.0','hop_version':'2.19.0','hop_sha512':builder.digest(hop,'sha512'),
                    'snapshot_repository':'https://example.test','plugins':[
                        {'artifact':'geometry','version':'0.2.0-SNAPSHOT','root':'plugins/misc/hop-geometry-type'},
                        {'artifact':'raster','version':'0.1.0-SNAPSHOT','root':'plugins/misc/hop-raster-type'},
                        {'artifact':'vector','version':'0.1.0-SNAPSHOT','root':'plugins/transforms/vector-raster'}]}
            def download(url,path):
                if url.endswith('maven-metadata.xml'):
                    Path(path).write_text('<metadata><versioning><snapshotVersions><snapshotVersion><extension>zip</extension><value>0.2.0-20260911.100000-1</value></snapshotVersion></snapshotVersions></versioning></metadata>')
                elif 'apache-hop-client' in url:
                    Path(path).write_bytes(hop.read_bytes())
                else:
                    plugin_root=next(
                        plugin['root'] for plugin in config['plugins']
                        if f"/{plugin['artifact']}/" in url
                    )
                    self.make_archive(path,{k.removeprefix('hop/'):v for k,v in entries.items() if k.startswith('hop/'+plugin_root)})
            with patch.object(builder,'download',download):
                metadata=builder.build(config,root/'dist')
            artifact=root/'dist'/metadata['artifacts'][0]['file']
            self.assertEqual(metadata['schema_version'], 2)
            self.assertEqual(metadata['distribution_version'], '0.2.0')
            self.assertEqual(metadata['publication_version'], '0.2.0')
            self.assertFalse(metadata['prerelease'])
            self.assertEqual(metadata['release_tag'],'v0.2.0')
            self.assertEqual(metadata['artifacts'][0]['sha256'],builder.digest(artifact))
            self.assertEqual(len(metadata['plugins']),3)
            self.assertIn('20260911',metadata['plugins'][0]['resolved_version'])
            self.assertEqual(len(list((root/'dist').glob('*.zip'))),1)

            snapshot_config = dict(config, distribution_version='0.2.1-SNAPSHOT')
            with patch.dict(os.environ, {'DISTRIBUTION_BUILD_SUFFIX': 'build.123.1'}):
                with patch.object(builder,'download',download):
                    snapshot = builder.build(snapshot_config,root/'snapshot')
            snapshot_artifact = root/'snapshot'/snapshot['artifacts'][0]['file']
            self.assertEqual(snapshot['distribution_version'], '0.2.1-SNAPSHOT')
            self.assertEqual(snapshot['publication_version'], '0.2.1-SNAPSHOT.build.123.1')
            self.assertTrue(snapshot['prerelease'])
            self.assertEqual(snapshot['release_tag'], 'v0.2.1-SNAPSHOT.build.123.1')
            self.assertEqual(snapshot_artifact.name, 'apache-hop-client-2.19.0-geo-0.2.1-SNAPSHOT.build.123.1.zip')

            with patch.dict(os.environ, {'DISTRIBUTION_BUILD_SUFFIX': 'build.124.1'}):
                with patch.object(builder,'download',download):
                    second_snapshot = builder.build(snapshot_config,root/'snapshot-two')
            self.assertNotEqual(snapshot['publication_version'], second_snapshot['publication_version'])

            with patch.dict(os.environ, {'DISTRIBUTION_BUILD_SUFFIX': 'build/unsafe'}):
                with self.assertRaisesRegex(builder.BuildError, 'build suffix'):
                    builder.build(snapshot_config,root/'bad-suffix')

            with patch.dict(os.environ, {'DISTRIBUTION_BUILD_SUFFIX': 'build.999.1'}):
                with self.assertRaisesRegex(builder.BuildError, 'only valid for SNAPSHOT'):
                    builder.build(config,root/'stable-with-suffix')

            config['hop_sha512']='0'*128
            with patch.object(builder,'download',download), self.assertRaisesRegex(builder.BuildError,'SHA-512'):
                builder.build(config,root/'bad')

if __name__ == '__main__':
    unittest.main()
