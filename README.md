# hop-distributions

Builds Apache Hop 2.17.0 client distributions with the `hop-gdal-plugin` vector suite merged in.

## What it does

- Runs on every `push` to `main`
- Can also be started manually with `workflow_dispatch`
- Does not run on pull requests
- Downloads `apache-hop-client-2.17.0.zip` from Apache
- Resolves the latest public `edigonzales/hop-gdal-plugin` release
- Merges the matching `hop-vector-suite-<version>-<target>.zip` into Hop for:
  - `linux-x86_64`
  - `linux-aarch64`
  - `osx-x86_64`
  - `osx-aarch64`
  - `windows-x86_64`
- Publishes the resulting archives as a GitHub draft release

## Output names

Generated archives use this pattern:

```text
apache-hop-client-2.17.0-hop-gdal-plugin-<plugin_tag_safe>-<target>.zip
```

The draft release tag uses this pattern:

```text
hop-2.17.0-<plugin_tag_safe>-<sha7>
```

## Local usage

```bash
python3 scripts/build_hop_distribution.py \
  --hop-version 2.17.0 \
  --plugin-release latest \
  --output-dir dist
```

Use `--target` one or more times to build only specific classifiers.

## Requirement

The workflow expects a public, non-draft GitHub release in `edigonzales/hop-gdal-plugin` that contains all five `hop-vector-suite-...zip` assets.
