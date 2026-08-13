# hop-distributions

Builds Apache Hop 2.18.1 client distributions with the `hop-gdal-plugin` gdal suite, the shared `hop-geometry-type-plugin` runtime, the `hop-geometry-inspector-plugin`, the `hop-geoprocessing-plugin`, the `hop-geometry-calculator-plugin`, the `hop-ili2db-plugin`, and the `hop-ilivalidator-plugin` merged in.

## What it does

- Runs on every `push` to `main`
- Runs on pull requests against `main` and builds the Windows target for validation
- Can also be started manually with `workflow_dispatch`
- Downloads `apache-hop-client-2.18.1.zip` from Apache and verifies its SHA-512 checksum
- Resolves the latest public `edigonzales/hop-gdal-plugin` release
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
- Merges `hop-geometry-type-plugin-<version>.zip` as the shared geometry runtime into all generated distributions
- Merges `hop-geometry-inspector-plugin-<version>.zip` into all generated distributions
- Merges `hop-geoprocessing-plugin-<version>.zip` into all generated distributions
- Merges `hop-geometry-calculator-plugin-<version>.zip` into all generated distributions
- Merges `hop-action-ili2db-<version>.zip` and `hop-transform-ili2db-<version>.zip` into all generated distributions
- Merges `hop-action-ilivalidator-<version>.zip` and `hop-transform-ilivalidator-<version>.zip` into all generated distributions
- Validates the shared geometry/JTS runtime layout in the packaged ZIP
- Runs a Windows end-to-end pipeline `OGR Input -> Geometry Calculator -> Dummy` twice before a release can be published
- Publishes the resulting archives as a GitHub release

## Output names

Generated archives use this pattern:

```text
apache-hop-client-2.18.1-hop-plugins-<gdal_tag_id>-<geometry_inspector_tag_id>-<ili2db_tag_id>-<ilivalidator_tag_id>-<geoprocessing_tag_id>-<geometry_calculator_tag_id>-<geometry_type_tag_id>-<target>.zip
```

The `*_tag_id` parts are compact, filename-safe identifiers derived from the full plugin release tags.

The release tag uses this pattern:

```text
hop-2.18.1-<gdal_tag_id>-<geometry_inspector_tag_id>-<ili2db_tag_id>-<ilivalidator_tag_id>-<geoprocessing_tag_id>-<geometry_calculator_tag_id>-<geometry_type_tag_id>-<sha7>
```

## Local usage

```bash
python3 scripts/build_hop_distribution.py \
  --hop-version 2.18.1 \
  --plugin-release latest \
  --geometry-inspector-release latest \
  --geoprocessing-release latest \
  --geometry-calculator-release latest \
  --ili2db-release latest \
  --ilivalidator-release latest \
  --output-dir dist
```

Use `--target` one or more times to build only specific classifiers.

## Requirements

The workflow expects public, non-draft GitHub releases in:

- `edigonzales/hop-gdal-plugin`, containing all five `hop-gdal-suite-...zip` assets
- `edigonzales/hop-geometry-type-plugin`, containing exactly one `hop-geometry-type-plugin-...zip` asset
- `edigonzales/hop-geometry-inspector-plugin`, containing exactly one `hop-geometry-inspector-plugin-...zip` asset
- `edigonzales/hop-geoprocessing-plugin`, containing exactly one `hop-geoprocessing-plugin-...zip` asset
- `edigonzales/hop-geometry-calculator-plugin`, containing exactly one `hop-geometry-calculator-plugin-...zip` asset
- `edigonzales/hop-ili2db-plugin`, containing exactly one `hop-action-ili2db-...zip` asset and one `hop-transform-ili2db-...zip` asset
- `edigonzales/hop-ilivalidator-plugin`, containing exactly one `hop-action-ilivalidator-...zip` asset and one `hop-transform-ilivalidator-...zip` asset

The Windows runtime smoke currently uses Java 23 because the GDAL plugin artifacts are compiled for Java 23. Apache Hop 2.18 itself requires Java 21 or newer.
