import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY_TYPES = {
    'SOGIS_RASTER_CLIP',
    'SOGIS_RASTER_REPROJECT',
    'SOGIS_RASTER_ZONAL_STATS',
}


class RasterE2EFixtureTests(unittest.TestCase):
    def transforms(self, fixture):
        root = ET.parse(ROOT / 'e2e' / 'raster' / fixture).getroot()
        return root.findall('transform')

    def assert_value_chain(self, fixture, operation_type, raster_field, requires_writer):
        transforms = self.transforms(fixture)
        types = [transform.findtext('type') for transform in transforms]
        self.assertTrue(LEGACY_TYPES.isdisjoint(types), types)
        self.assertIn('SOGIS_RASTER_READER', types)
        self.assertIn(operation_type, types)
        if requires_writer:
            self.assertIn('SOGIS_RASTER_WRITER', types)

        raster_transforms = [
            transform for transform in transforms
            if transform.findtext('rasterField') is not None
        ]
        self.assertTrue(raster_transforms)
        for transform in raster_transforms:
            self.assertEqual(transform.findtext('version'), '1')
            self.assertEqual(transform.findtext('rasterField'), raster_field)

        removed_fields = {
            name.text
            for transform in transforms
            if transform.findtext('type') == 'SelectValues'
            for name in transform.findall('./fields/remove/name')
        }
        self.assertIn(raster_field, removed_fields)

    def test_clip_fixture_uses_raster_value_chain(self):
        self.assert_value_chain(
            'clip.hpl', 'SOGIS_RASTER_VALUE_CLIP', '__raster_value_2', True
        )

    def test_reproject_fixture_uses_raster_value_chain(self):
        self.assert_value_chain(
            'reproject.hpl', 'SOGIS_RASTER_VALUE_REPROJECT', '__raster_value_2', True
        )

    def test_zonal_fixture_uses_raster_value_chain(self):
        self.assert_value_chain(
            'zonal.hpl', 'SOGIS_RASTER_VALUE_ZONAL_STATS', '__raster_value_4', False
        )


if __name__ == '__main__':
    unittest.main()
