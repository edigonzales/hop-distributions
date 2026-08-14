# hop-distributions

Builds Apache Hop 2.18.1 client distributions with the `hop-gdal-plugin` gdal suite, the `hop-geotools-plugin` vector transforms, the shared `hop-geometry-type-plugin` runtime, the `hop-geometry-inspector-plugin`, the `hop-geoprocessing-plugin`, the `hop-geometry-calculator-plugin`, the `hop-ili2db-plugin`, and the `hop-ilivalidator-plugin` merged in.

## What it does

- Runs on every `push` to `main`
- Runs on pull requests against `main` and builds the Windows target for validation
- Can also be started manually with `workflow_dispatch`
- Downloads `apache-hop-client-2.18.1.zip` from Apache and verifies its SHA-512 checksum
- Resolves the latest public `edigonzales/hop-gdal-plugin` release
- Resolves the latest public `edigonzales/hop-geotools-plugin` release
- Resolves the latest public `edigonzales/hop-geometry-type-plugin` release
- Resolves the latest public `edigonzales/hop-geometry-inspector-plugin` release
- Resolves the latest public `edigonzales/hop-geoprocessing-plugin` release
- Resolves the latest public `edigonzales/hop-geometry-calculator-plugin` release
- Resolves the latest public `edigonzales/hop-ili2db-plugin` release
- Resolves the latest public `edigonzales/hop-ilivalidator-plugin` release
- Merges the matching `hop-gdal-suite-<version>-<target>.zip` into Hop for:
  - `linux-x86_64`
  - `linux-aarch64`
  - `osx-x86_64`
  - `osx-aarch64`
  - `windows-x86_64`
- Merges the platform-independent `hop-geotools-plugin-<version>.zip` into every generated distribution
- Merges `hop-geometry-type-plugin-<version>.zip` exactly once as the shared Geometry/JTS runtime
- Merges `hop-geometry-inspector-plugin-<version>.zip` into all generated distributions
- Merges `hop-geoprocessing-plugin-<version>.zip` into all generated distributions
- Merges `hop-geometry-calculator-plugin-<version>.zip` into all generated distributions
- Merges `hop-action-ili2db-<version>.zip` and `hop-transform-ili2db-<version>.zip` into all generated distributions
- Merges `hop-action-ilivalidator-<version>.zip` and `hop-transform-ilivalidator-<version>.zip` into all generated distributions
- Validates the shared geometry/JTS runtime layout in the packaged ZIP, including that GeoTools does not carry another `jts-core` or Geometry Type runtime
- Runs a Windows end-to-end pipeline `OGR Input -> Geometry Calculator -> Dummy` twice before a release can be published
- Runs a Windows SQL/MM `CURVEPOLYGON` preview-string regression smoke against the packaged distribution
- Publishes the resulting archives as a GitHub release

## Plugin artifact model

`hop-distributions` consumes **installable plugin ZIPs from GitHub Releases**. Maven repositories are used by plugin projects for compile/build dependencies, but are not used here to assemble the Hop runtime.

The Geometry Type runtime is intentionally present only once:

```text
hop/
├── plugins/misc/hop-geometry-type/
│   ├── hop-geometry-type-....jar
│   └── lib/jts-core-....jar
├── plugins/transforms/gdal-suite/
├── plugins/transforms/geotools-vector/
├── plugins/transforms/hop-geoprocessing/
├── plugins/transforms/hop-geometry-calculator/
└── plugins/misc/hop-geometry-inspector/
```

The geospatial consumer plugins use that shared runtime instead of packaging their own JTS copy.

## Release and output names

Published names deliberately contain only the Apache Hop version and the seven-character `hop-distributions` commit SHA. Plugin release identifiers are kept out of filenames and release titles so names stay short and stable as more plugins are added.

For a distribution commit such as `595728817ee158f06f54d52675a5600c4ac680e1`, the distribution id is `5957288`.

The GitHub release tag is:

```text
hop-2.18.1-geo-5957288
```

The GitHub release title is:

```text
Apache Hop 2.18.1 + Geo Plugins (5957288)
```

Generated archives use this pattern:

```text
apache-hop-client-2.18.1-geo-5957288-linux-x86_64.zip
apache-hop-client-2.18.1-geo-5957288-linux-aarch64.zip
apache-hop-client-2.18.1-geo-5957288-osx-x86_64.zip
apache-hop-client-2.18.1-geo-5957288-osx-aarch64.zip
apache-hop-client-2.18.1-geo-5957288-windows-x86_64.zip
```

The exact full release tag of every bundled plugin remains recorded in `release-metadata.json` and in the GitHub release body. The short distribution id therefore identifies the assembled distribution, while the metadata preserves full reproducibility and provenance.

## Local usage

```bash
python3 scripts/build_hop_distribution.py \
  --hop-version 2.18.1 \
  --plugin-release latest \
  --geotools-release latest \
  --geometry-inspector-release latest \
  --geoprocessing-release latest \
  --geometry-calculator-release latest \
  --ili2db-release latest \
  --ilivalidator-release latest \
  --output-dir dist
```

Use `--target` one or more times to build only specific classifiers. Each plugin release option also accepts an explicit GitHub release tag instead of `latest`, which makes a distribution build reproducible against a fixed set of plugin releases.

The raw builder output is finalized by `scripts/finalize_release_names.py` after the shared Geometry Type runtime has been added. This final step records the Geometry Type release and normalizes all published names to the short distribution-id scheme above.

## Requirements

The workflow expects public, non-draft, non-prerelease GitHub releases in:

- `edigonzales/hop-gdal-plugin`, containing all five `hop-gdal-suite-...zip` assets
- `edigonzales/hop-geotools-plugin`, containing exactly one `hop-geotools-plugin-...zip` asset with `plugins/transforms/geotools-vector/`
- `edigonzales/hop-geometry-type-plugin`, containing exactly one `hop-geometry-type-plugin-...zip` asset
- `edigonzales/hop-geometry-inspector-plugin`, containing exactly one `hop-geometry-inspector-plugin-...zip` asset
- `edigonzales/hop-geoprocessing-plugin`, containing exactly one `hop-geoprocessing-plugin-...zip` asset
- `edigonzales/hop-geometry-calculator-plugin`, containing exactly one `hop-geometry-calculator-plugin-...zip` asset
- `edigonzales/hop-ili2db-plugin`, containing exactly one `hop-action-ili2db-...zip` asset and one `hop-transform-ili2db-...zip` asset
- `edigonzales/hop-ilivalidator-plugin`, containing exactly one `hop-action-ilivalidator-...zip` asset and one `hop-transform-ilivalidator-...zip` asset

The GeoTools plugin itself is Java 17 compatible, but the complete bundled Hop distribution currently has the stricter runtime requirement from Apache Hop/GDAL. The Windows runtime smoke uses Java 23 because the GDAL plugin artifacts are compiled for Java 23. Apache Hop 2.18 itself requires Java 21 or newer.
