#!/usr/bin/env python3
"""Create a minimal GeoPackage containing one SQL/MM CURVEPOLYGON feature."""

from __future__ import annotations

import sqlite3
import struct
import sys
from pathlib import Path


def wkb_circular_string(points: list[tuple[float, float]]) -> bytes:
    payload = bytearray()
    payload += struct.pack("<BI", 1, 8)  # little endian, CircularString
    payload += struct.pack("<I", len(points))
    for x, y in points:
        payload += struct.pack("<dd", x, y)
    return bytes(payload)


def wkb_curve_polygon() -> bytes:
    ring = wkb_circular_string(
        [
            (0.0, 0.0),
            (4.0, 0.0),
            (4.0, 4.0),
            (0.0, 4.0),
            (0.0, 0.0),
        ]
    )
    return struct.pack("<BII", 1, 10, 1) + ring  # CurvePolygon with one ring


def gpkg_geometry_blob(srs_id: int = 2056) -> bytes:
    # GeoPackage binary header: magic, version, flags (little endian/no envelope), SRS ID.
    return b"GP" + bytes((0, 1)) + struct.pack("<i", srs_id) + wkb_curve_polygon()


def create(path: Path) -> None:
    if path.exists():
        path.unlink()

    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA application_id = 1196444487")  # GPKG
        connection.execute("PRAGMA user_version = 10300")

        connection.executescript(
            """
            CREATE TABLE gpkg_spatial_ref_sys (
              srs_name TEXT NOT NULL,
              srs_id INTEGER NOT NULL PRIMARY KEY,
              organization TEXT NOT NULL,
              organization_coordsys_id INTEGER NOT NULL,
              definition TEXT NOT NULL,
              description TEXT
            );

            INSERT INTO gpkg_spatial_ref_sys VALUES
              ('Undefined Cartesian', -1, 'NONE', -1, 'undefined', 'undefined Cartesian coordinate reference system'),
              ('Undefined geographic', 0, 'NONE', 0, 'undefined', 'undefined geographic coordinate reference system'),
              ('CH1903+ / LV95', 2056, 'EPSG', 2056, 'undefined', 'Swiss projected coordinate reference system');

            CREATE TABLE gpkg_contents (
              table_name TEXT NOT NULL PRIMARY KEY,
              data_type TEXT NOT NULL,
              identifier TEXT UNIQUE,
              description TEXT DEFAULT '',
              last_change DATETIME NOT NULL,
              min_x DOUBLE,
              min_y DOUBLE,
              max_x DOUBLE,
              max_y DOUBLE,
              srs_id INTEGER,
              CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
            );

            CREATE TABLE gpkg_geometry_columns (
              table_name TEXT NOT NULL,
              column_name TEXT NOT NULL,
              geometry_type_name TEXT NOT NULL,
              srs_id INTEGER NOT NULL,
              z TINYINT NOT NULL,
              m TINYINT NOT NULL,
              CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
              CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
              CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
            );

            CREATE TABLE gpkg_extensions (
              table_name TEXT,
              column_name TEXT,
              extension_name TEXT NOT NULL,
              definition TEXT NOT NULL,
              scope TEXT NOT NULL,
              CONSTRAINT ge_tce UNIQUE (table_name, column_name, extension_name)
            );

            CREATE TABLE curve_feature (
              id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
              geometry BLOB NOT NULL
            );

            INSERT INTO gpkg_contents
              (table_name, data_type, identifier, description, last_change, min_x, min_y, max_x, max_y, srs_id)
            VALUES
              ('curve_feature', 'features', 'curve_feature', 'CurvePolygon smoke fixture',
               '2026-08-14T00:00:00.000Z', 0, 0, 4, 4, 2056);

            INSERT INTO gpkg_geometry_columns
              (table_name, column_name, geometry_type_name, srs_id, z, m)
            VALUES
              ('curve_feature', 'geometry', 'CURVEPOLYGON', 2056, 0, 0);

            INSERT INTO gpkg_extensions
              (table_name, column_name, extension_name, definition, scope)
            VALUES
              ('curve_feature', 'geometry', 'gpkg_geom_CURVEPOLYGON',
               'http://www.geopackage.org/spec/#extension_geometry_types', 'read-write');
            """
        )
        connection.execute(
            "INSERT INTO curve_feature (geometry) VALUES (?)",
            (sqlite3.Binary(gpkg_geometry_blob()),),
        )
        connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: create_curve_gpkg.py <output.gpkg>")
    create(Path(sys.argv[1]))
