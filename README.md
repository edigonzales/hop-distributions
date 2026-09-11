# Hop Geo Distribution

One platform-independent Apache Hop **2.19.0** client distribution, version **0.2.0**,
with nine plugin projects installed:

- Geometry Type (shared Geometry/JTS runtime)
- Geometry Inspector
- Geometry Calculator
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
A new snapshot base version requires an explicit configuration update.

The builder verifies Hop's SHA-512, rejects overlapping plugin files, and preserves
launcher permissions. It produces:

- `apache-hop-client-2.19.0-geo-0.2.0.zip`
- its `.sha256` checksum
- `release-metadata.json`, including resolved input URLs, versions and hashes

## Shared Geometry runtime

Install Geometry Type once under `plugins/misc/hop-geometry-type`, with JTS in its
`lib` folder. Vector Raster must contain no Geometry/JTS copies and must declare
both `../../misc/hop-geometry-type` and `../../misc/hop-geometry-type/lib` in
`dependencies.xml`. Hop deliberately skips nested `lib` folders when searching a
dependency directory. The shared classloader group is `sogeo-geometry`.

Old Vector Raster ZIPs are rejected, not rewritten. GDAL and Form Definition are
not included. Upgrade by extracting the distribution into a clean directory;
do not overlay it on an installation containing obsolete plugin JARs.

## End-to-end verification

With Java 21 or 25 selected through `JAVA_HOME`:

```sh
python3 scripts/run_e2e.py \
  --archive dist/apache-hop-client-2.19.0-geo-0.2.0.zip \
  --work-dir .ci/local-e2e
```

Use a fresh work directory. Logs, generated fixtures and results remain under its
`reports` directory. Tests exercise the actual installed Hop launchers and plugin
classloaders. They cover runtime identity under both load orders, plugin loading
and Inspector initialization, geometry serialization/preview (SRID, Z/M, curves),
raster clip/reprojection/statistics, vector export, calculator/geoprocessing,
INTERLIS curve roundtrip, ili2db action/transform, positive and negative validator
action/transform scenarios, and GraalPy including Geometry fields.

Fixture preparation uses a separate JVM with the required data libraries; that
classpath is never used to run pipelines or runtime identity tests. Adapted test
fixtures are attributed in `e2e/provenance.json`.

### Known validator behavior

In the current ilivalidator snapshot, static validation without incoming rows emits
an invalid result row but bypasses the `failPipelineOnInvalid` check. Use incoming
file rows when a validation error must fail the pipeline. The negative E2E test
exercises that row-driven mode. This distribution does not modify plugin behavior.

## CI and releases

PRs, pushes to `main` and manual runs build one archive on Ubuntu. Only E2E jobs
use the Java 21/25 × Linux/macOS/Windows matrix, all consuming that same archive.
Release publication depends on the complete successful matrix and is disabled
for PRs. GitHub release `v0.2.0` includes the ZIP, checksum and provenance manifest.
Existing releases are left unchanged. Increment `distribution_version` for the
next publication; rebuilding an existing version does not replace its release.
