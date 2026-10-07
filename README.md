# Hop Geo Distribution

One platform-independent Apache Hop **2.19.0** client distribution, base version **0.2.1-SNAPSHOT**,
with fourteen plugin projects installed:

- Geometry Type (shared Geometry/JTS runtime)
- Raster Type
- Geometry Inspector
- Application Launcher (desktop perspective)
- Geometry Calculator
- JSON Object Builder
- SDMX Input
- Geoprocessing
- Vector Raster (GeoTools; no GDAL)
- INTERLIS
- ili2db (action and transform)
- ilivalidator (action and transform)
- INTERLIS Row Validator
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

## Application Launcher

The distribution includes Application Launcher under
`plugins/misc/hop-application-launcher`, with its libraries and license. In Hop GUI,
open **Applications / Anwendungen** in the perspective selector. Configure the Git
repository, branch and a dedicated checkout base directory in **Settings / Einstellungen**.
The default repository is `sogis/datenportal-themenrepo`, branch `main`.
The launcher manages a separate checkout subdirectory for each configured repository.

The launcher provides parameter forms for catalogued pipelines and workflows,
local execution, live logs and revision-linked run reports. See the
[launcher handbook](https://edigonzales.github.io/hop-application-launcher-plugin/)
for catalog and parameter configuration.

## SDMX Input

SDMX Input is installed under `plugins/transforms/hop-sdmx` from
`ch.so.agi:hop-sdmx-plugin:0.1.0-SNAPSHOT`. Find **SDMX Input** in Hop's **Input**
category. Its dialog discovers dataflows, dimensions and code lists, while the
pipeline stores a fixed output schema. Start/end periods and dimension filters
support Hop parameters, including values supplied by Application Launcher.
Labels are separate fields resolved from structure metadata; codes and SDMX
period strings are preserved. BFS is the first verified provider.

See the [SDMX handbook](https://edigonzales.github.io/hop-sdmx-plugin/)
for configuration and the parameterized BFS example. The distribution tests use
[e2e/sdmx/health-financing.hpl](e2e/sdmx/health-financing.hpl) with a local HTTP
fixture server; the pipeline's default endpoint points to BFS for manual use.

## INTERLIS Row Validator

INTERLIS Row Validator is installed under `plugins/transforms/interlis-row-validator`
from `ch.so.agi:hop-interlis-row-validator-plugin:0.1.0-SNAPSHOT`. Find
**Row Stream Validator (INTERLIS)** in Hop's **Validation** category. Map incoming
scalar fields to attributes of one INTERLIS class. The complete finite input stream
forms one validation unit; original fields and values, including unmapped fields,
are preserved. Geometry, structures and association roles are unsupported.

The native Local engine is required. **Full validation**, the default, requires
one transform copy without partitioning and releases rows in reception order only
after successful validation, including the second pass. Validation errors release
no rows. Its original-row cache can spool to disk, optionally with compression.
**Single Pass** emits checked rows immediately and allows independent parallel
copies, but omits second-pass class constraints, including some MANDATORY
CONSTRAINTs. On the first error it stops; previously emitted rows cannot be recalled.

Typed Date/Timestamp mappings require an explicit conversion time zone. Optional
JSONL reports record diagnostics, validation decisions and emitted row counts.
See the [Row Validator handbook](https://edigonzales.github.io/hop-interlis-row-validator-plugin/row-validator/main/index.html#row-validator)
for configuration and limitations.

## End-to-end verification

With Java 21 or 25 selected through `JAVA_HOME` and Git available for disposable
launcher fixtures (Linux additionally needs an X display, such as `xvfb-run -a`):

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
action/transform scenarios, JSON Object Builder and JSON Array Builder example
pipelines, and GraalPy including Geometry fields. SDMX checks cover installed
plugin discovery, parameterized periods, stable output columns, codes and German
labels, numeric and missing observations, multiplier/status preservation,
incompatible schema rejection before data retrieval, rejection of deletion actions,
and cancellation of a streaming pipeline without retrying the data request.
They use a local HTTP server and require no BFS availability. Launcher checks
discover and initialize the installed SWT perspective, clone a disposable local
Git repository, run a pipeline and workflow through its parameter forms, and
verify CSV output, logs and revision-linked reports. A missing input file must
produce a failed run. Launcher settings, checkout and reports are isolated under
`reports/launcher`; these checks do not access the default themes repository.

Row Validator checks cover full validation with compressed one-row-cache spooling,
unchanged original values and ordering, late UNIQUE conflicts and MANDATORY
CONSTRAINT failures with no output, the limited Single Pass scope and early failure,
empty input, parallel Single Pass copies, rejection of parallel Full validation,
and typed temporal conversion with `Europe/Zurich`. They verify JSONL completion,
status, release decisions and row counts, plus spool cleanup. All nine scenarios
use small local fixtures; reports and generated pipelines remain under
`reports/row-validator`.

Fixture preparation uses a separate JVM with the required data libraries; that
classpath is never used to run pipelines or runtime identity tests. Adapted test
fixtures are attributed in `e2e/provenance.json`.

### File validator behavior

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
