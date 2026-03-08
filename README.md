# hop-distributions

Builds Apache Hop 2.17.0 client distributions with the `hop-gdal-plugin` vector suite and the `hop-geometry-inspector-plugin` merged in.

## What it does

- Runs on every `push` to `main`
- Can also be started manually with `workflow_dispatch`
- Does not run on pull requests
- Downloads `apache-hop-client-2.17.0.zip` from Apache
- Resolves the latest public `edigonzales/hop-gdal-plugin` release
- Resolves the latest public `edigonzales/hop-geometry-inspector-plugin` release
- Merges the matching `hop-vector-suite-<version>-<target>.zip` into Hop for:
  - `linux-x86_64`
  - `linux-aarch64`
  - `osx-x86_64`
  - `osx-aarch64`
  - `windows-x86_64`
- Merges `hop-geometry-inspector-plugin-<version>.zip` into all generated distributions
- Publishes the resulting archives as a GitHub release

## Output names

Generated archives use this pattern:

```text
apache-hop-client-2.17.0-hop-gdal-plugin-<plugin_tag_safe>-<target>.zip
```

The release tag uses this pattern:

```text
hop-2.17.0-<plugin_tag_safe>-<geometry_inspector_tag_safe>-<sha7>
```

## Local usage

```bash
python3 scripts/build_hop_distribution.py \
  --hop-version 2.17.0 \
  --plugin-release latest \
  --geometry-inspector-release latest \
  --output-dir dist
```

Use `--target` one or more times to build only specific classifiers.

## Requirement

The workflow expects public, non-draft GitHub releases in:

- `edigonzales/hop-gdal-plugin`, containing all five `hop-vector-suite-...zip` assets
- `edigonzales/hop-geometry-inspector-plugin`, containing exactly one `hop-geometry-inspector-plugin-...zip` asset
