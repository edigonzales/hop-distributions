# hop-distributions

Builds Apache Hop 2.17.0 client distributions with the `hop-gdal-plugin` vector suite, the `hop-geometry-inspector-plugin`, the `hop-geoprocessing-plugin`, the `hop-ili2db-plugin`, and the `hop-ilivalidator-plugin` merged in.

## What it does

- Runs on every `push` to `main`
- Can also be started manually with `workflow_dispatch`
- Does not run on pull requests
- Downloads `apache-hop-client-2.17.0.zip` from Apache
- Resolves the latest public `edigonzales/hop-gdal-plugin` release
- Resolves the latest public `edigonzales/hop-geometry-inspector-plugin` release
- Resolves the latest public `edigonzales/hop-geoprocessing-plugin` release
- Resolves the latest public `edigonzales/hop-ili2db-plugin` release
- Resolves the latest public `edigonzales/hop-ilivalidator-plugin` release
- Merges the matching `hop-vector-suite-<version>-<target>.zip` into Hop for:
  - `linux-x86_64`
  - `linux-aarch64`
  - `osx-x86_64`
  - `osx-aarch64`
  - `windows-x86_64`
- Merges `hop-geometry-inspector-plugin-<version>.zip` into all generated distributions
- Merges `hop-geoprocessing-plugin-<version>.zip` into all generated distributions
- Merges `hop-action-ili2db-<version>.zip` and `hop-transform-ili2db-<version>.zip` into all generated distributions
- Merges `hop-action-ilivalidator-<version>.zip` and `hop-transform-ilivalidator-<version>.zip` into all generated distributions
- Publishes the resulting archives as a GitHub release

## Output names

Generated archives use this pattern:

```text
apache-hop-client-2.17.0-hop-plugins-<gdal_tag_id>-<geometry_inspector_tag_id>-<ili2db_tag_id>-<ilivalidator_tag_id>-<geoprocessing_tag_id>-<target>.zip
```

The `*_tag_id` parts are compact, filename-safe identifiers derived from the full plugin release tags.

The release tag uses this pattern:

```text
hop-2.17.0-<gdal_tag_id>-<geometry_inspector_tag_id>-<ili2db_tag_id>-<ilivalidator_tag_id>-<geoprocessing_tag_id>-<sha7>
```

## Local usage

```bash
python3 scripts/build_hop_distribution.py \
  --hop-version 2.17.0 \
  --plugin-release latest \
  --geometry-inspector-release latest \
  --geoprocessing-release latest \
  --ili2db-release latest \
  --ilivalidator-release latest \
  --output-dir dist
```

Use `--target` one or more times to build only specific classifiers.

## Requirement

The workflow expects public, non-draft GitHub releases in:

- `edigonzales/hop-gdal-plugin`, containing all five `hop-vector-suite-...zip` assets
- `edigonzales/hop-geometry-inspector-plugin`, containing exactly one `hop-geometry-inspector-plugin-...zip` asset
- `edigonzales/hop-geoprocessing-plugin`, containing exactly one `hop-geoprocessing-plugin-...zip` asset
- `edigonzales/hop-ili2db-plugin`, containing exactly one `hop-action-ili2db-...zip` asset and one `hop-transform-ili2db-...zip` asset
- `edigonzales/hop-ilivalidator-plugin`, containing exactly one `hop-action-ilivalidator-...zip` asset and one `hop-transform-ilivalidator-...zip` asset
