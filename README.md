# Hop Geo Distribution

One platform-independent Apache Hop **2.19.0** client distribution, base version **0.2.1-SNAPSHOT**,
with eleven plugin projects installed:

- Geometry Type (shared Geometry/JTS runtime)
- Raster Type
- Geometry Inspector
- Geometry Calculator
- JSON Object Builder
- Geoprocessing
- Vector Raster (GeoTools; no GDAL)
- INTERLIS
- ili2db (action and transform)
- ilivalidator (action and transform)
- Python/GraalPy

## Build

```sh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/build_hop_distribution.py --output-dir dist
```

`distribution.json` is the single source for distribution/Hop versions, the
trusted Hop SHA-512, Maven snapshot base versions and installation roots.
Each build resolves the latest unclassified ZIP in Maven snapshot metadata:
Geometry Type `0.2.0-SNAPSHOT`, other plugins `0.1.0-SNAPSHOT`. Timestamped
snapshot coordinates are recorded in the manifest, never pinned in the workflow.
A new snapshot base version requires an explicit configuration update. CI adds
`build.<github-run-id>.<run-attempt>` to Snapshot distributions so each published
pre-release is unique and immutable. Local builds without that variable keep the
base version in the filename.

The builder verifies Hop's SHA-512, rejects overlapping plugin files, and preserves
launcher permissions. It produces:

- `apache-hop-client-2.19.0-geo-0.2.1-SNAPSHOT.zip` (local build)
- `apache-hop-client-2.19.0-geo-0.2.1-SNAPSHOT.build.123456789.1.zip` (CI build)
- its `.sha256` checksum
- `release-metadata.json`, including resolved input URLs, versions and hashes

## Shared Geometry runtime

Install Geometry Type once under `plugins/misc/hop-geometry-type`; it owns the shared
Geometry/JTS, GeoTools, Imagen, ImageIO-Ext and UOM runtime. Install Raster Type under
`plugins/misc/hop-raster-type`; it owns the native raster model. Vector Raster contains
only its GeoTools raster backend and declares `../../misc/hop-raster-type` plus
`../../misc/hop-raster-type/lib` in `dependencies.xml`. The shared classloader group is
`sogeo-geometry`.

Old Vector Raster ZIPs are rejected, not rewritten. GDAL and Form Definition are
not included. Upgrade by extracting the distribution into a clean directory;
do not overlay it on an installation containing obsolete plugin JARs.

## End-to-end verification

With Java 21 or 25 selected through `JAVA_HOME`:

```sh
python3 scripts/run_e2e.py \
  --archive dist/apache-hop-client-2.19.0-geo-0.2.1-SNAPSHOT.zip \
  --work-dir .ci/local-e2e
```

Use a fresh work directory. Logs, generated fixtures and results remain under its
`reports` directory. Tests exercise the actual installed Hop launchers and plugin
classloaders. They cover runtime identity under both load orders, plugin loading
and Inspector initialization, geometry serialization/preview (SRID, Z/M, curves),
raster clip/reprojection/statistics, vector export, calculator/geoprocessing,
INTERLIS curve roundtrip, ili2db action/transform, positive and negative validator
action/transform scenarios, JSON Object Builder and JSON Array Builder example pipelines, and
GraalPy including Geometry fields.

Fixture preparation uses a separate JVM with the required data libraries; that
classpath is never used to run pipelines or runtime identity tests. Adapted test
fixtures are attributed in `e2e/provenance.json`.

### Validator behavior

Static validation without incoming rows applies `failPipelineOnInvalid` just like
row-driven validation. Technical validation errors always fail the transform; an
invalid result either stops the pipeline or is emitted according to that option.

## CI and releases

PRs, pushes to `main` and manual runs build one archive on Ubuntu. Only E2E jobs
use the Java 21/25 × Linux/macOS/Windows matrix, all consuming that same archive.
Release publication depends on the complete successful matrix and is disabled
for PRs. Main builds with the `0.2.1-SNAPSHOT` base create immutable GitHub
pre-releases with their build suffix; existing tags and assets are left unchanged.
For the final stable release, change `distribution_version` to `0.2.1` and publish
without a suffix. Stable releases are immutable as well.
