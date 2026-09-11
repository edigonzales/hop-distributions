#!/usr/bin/env python3
"""Verify the actual install ZIP in an isolated Hop home, optionally with Geometry."""
import argparse
import copy
import csv
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


def set_text(parent, tag, text):
    element = parent.find(tag)
    if element is None:
        element = ET.SubElement(parent, tag)
    element.text = str(text)


def output_field(transform, name, kind, replace=False):
    fields = transform.find("outputFields")
    field = ET.SubElement(fields, "outputField")
    for tag, value in dict(name=name, type=kind, length=-1, precision=-1, replaceExisting="Y" if replace else "N").items():
        set_text(field, tag, value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hop-home", type=Path, required=True)
    parser.add_argument("--plugin-zip", type=Path, required=False)
    parser.add_argument("--geometry-plugin-zip", type=Path)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    hop_home = args.hop_home.resolve()
    hop_run = hop_home / ("hop-run.bat" if os.name == "nt" else "hop-run.sh")
    if not hop_run.is_file():
        raise SystemExit(f"Hop launcher not found: {hop_run}")
    template = ET.parse(Path(__file__).resolve().parents[1] / "e2e/graalpy.hpl")
    from contextlib import nullcontext
    args.work_dir.mkdir(parents=True, exist_ok=True)
    with nullcontext(str(args.work_dir.resolve())) as directory:
        root = Path(directory)
        input_dir = root / "input"
        input_dir.mkdir()
        run_metadata = root / "config/metadata/pipeline-run-configuration"
        run_metadata.mkdir(parents=True)
        local = json.loads((hop_home / "config/projects/default/metadata/pipeline-run-configuration/local.json").read_text())
        local["executionInfoLocationName"] = ""
        local["dataProfile"] = ""
        (run_metadata / "local.json").write_text(json.dumps(local))
        (input_dir / "values.csv").write_text("value\n2\n5\n", encoding="utf-8")
        scenarios = ["basic", "filter", "emit", "file", "reject", "empty"]
        if (hop_home / "plugins/misc/hop-geometry-type").is_dir():
            scenarios.append("geometry")
        for scenario in scenarios:
            tree = copy.deepcopy(template)
            pipeline = tree.getroot()
            py = next(t for t in pipeline.findall("transform") if t.findtext("type") == "GraalPyTransform")
            destination = root / scenario
            destination.mkdir()
            expected = [{"value": "2", "doubled": "4"}, {"value": "5", "doubled": "10"}]
            if scenario != "basic":
                py.find("outputFields").clear()
                set_text(py, "configurationVersion", 2)
                set_text(py, "executionTimeoutSeconds", 30)
                set_text(py, "maxEmittedRows", 1000)
                set_text(py, "maxLogBytes", 1048576)
            if scenario == "filter":
                set_text(py, "scriptText", "def process(row, ctx):\n    return {} if row['value'] == 2 else None\n")
                expected = [{"value": "2"}]
            elif scenario == "emit":
                set_text(py, "executionMode", "EMIT_MANY")
                set_text(py, "scriptText", "def process(row, ctx):\n    ctx.emit({'value': 1})\n    ctx.emit({'value': 2})\n")
                output_field(py, "value", "Integer", True)
                expected = [{"value": "1"}, {"value": "2"}] * 2
            elif scenario == "file":
                code = root / "process.py"
                code.write_text("def setup(ctx):\n    ctx.state['factor'] = int(ctx.parameters['factor'])\ndef process(row, ctx):\n    return {'doubled': row['value'] * ctx.state['factor']}\n", encoding="utf-8")
                set_text(py, "scriptSource", "FILE")
                set_text(py, "scriptPath", code)
                parameter = ET.SubElement(ET.SubElement(py, "parameters"), "parameter")
                set_text(parameter, "name", "factor")
                set_text(parameter, "value", "3")
                output_field(py, "doubled", "Integer")
                expected = [{"value": "2", "doubled": "6"}, {"value": "5", "doubled": "15"}]
            elif scenario == "reject":
                set_text(py, "executionMode", "EMIT_MANY")
                set_text(py, "scriptText", "def process(row, ctx):\n    ctx.emit({'value': row['value'] * 10})\n    if row['value'] == 5: ctx.reject('BAD', 'Rejected five', field='value')\n")
                output_field(py, "value", "Integer", True)
                writer = copy.deepcopy(next(t for t in pipeline.findall("transform") if t.findtext("type") == "TextFileOutput"))
                set_text(writer, "name", "Write rejects")
                set_text(writer.find("file"), "name", "${E2E_OUTPUT_DIR}/rejects")
                pipeline.append(writer)
                error = ET.SubElement(pipeline.find("transform_error_handling"), "error")
                for tag, value in dict(source_transform="Run GraalPy", target_transform="Write rejects", is_enabled="Y", codes_valuename="code", descriptions_valuename="message", fields_valuename="field", nr_valuename="errors").items():
                    set_text(error, tag, value)
                hop = ET.SubElement(pipeline.find("order"), "hop")
                for tag, value in {"from": "Run GraalPy", "to": "Write rejects", "enabled": "Y"}.items(): set_text(hop, tag, value)
                expected = [{"value": "20"}]
            elif scenario == "empty":
                empty = root / "empty-input"
                empty.mkdir()
                (empty / "values.csv").write_text("value\n", encoding="utf-8")
                set_text(py, "scriptText", "def setup(ctx):\n    ctx.log.info('EMPTY_SETUP_OK')\ndef process(row, ctx):\n    raise RuntimeError('No rows expected')\ndef close(ctx):\n    ctx.log.info('EMPTY_CLOSE_OK')\n")
                expected = []
            elif scenario == "geometry":
                set_text(py, "scriptText", "def process(row, ctx):\n    return {'geom': ctx.geometry.from_wkt('POINT (2 5)', srid=2056)}\n")
                output_field(py, "geom", "Geometry")
                downstream = copy.deepcopy(py)
                set_text(downstream, "name", "Inspect geometry")
                downstream.find("outputFields").clear()
                set_text(downstream, "scriptText", "def process(row, ctx):\n    g = row['geom']\n    assert g.srid == 2056\n    assert g.geom_type == 'Point'\n    return {'wkt': g.to_wkt(), 'srid': g.srid}\n")
                output_field(downstream, "wkt", "String")
                output_field(downstream, "srid", "Integer")
                writer = next(t for t in pipeline.findall("transform") if t.findtext("name") == "Write result")
                for name, kind in [("value", "Integer"), ("wkt", "String"), ("srid", "Integer")]:
                    selected = ET.SubElement(writer.find("fields"), "field")
                    for tag, value in dict(name=name, type=kind, length=-1, precision=-1).items():
                        set_text(selected, tag, value)
                pipeline.append(downstream)
                for hop in pipeline.find("order").findall("hop"):
                    if hop.findtext("from") == "Run GraalPy": set_text(hop, "to", "Inspect geometry")
                hop = ET.SubElement(pipeline.find("order"), "hop")
                for tag, value in {"from": "Inspect geometry", "to": "Write result", "enabled": "Y"}.items(): set_text(hop, tag, value)
                expected = [{"value": "2", "wkt": "POINT (2 5)", "srid": "2056"}, {"value": "5", "wkt": "POINT (2 5)", "srid": "2056"}]
            definition = destination / "pipeline.hpl"
            tree.write(definition, encoding="utf-8", xml_declaration=True)
            command = [str(hop_run), "-r", "local", "-f", str(definition), "-p", f"E2E_INPUT_DIR={root / 'empty-input' if scenario == 'empty' else input_dir}", "-p", f"E2E_OUTPUT_DIR={destination}"]
            environment = os.environ.copy()
            environment["HOP_CONFIG_FOLDER"] = str(root / "config")
            if os.name == "nt":
                command = ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(command)]
            completed = subprocess.run(command, text=True, capture_output=True, timeout=120, cwd=hop_home, env=environment)
            (destination / "hop.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
            if completed.returncode:
                print(completed.stdout)
                print(completed.stderr)
                raise SystemExit(f"{scenario}: hop-run failed ({completed.returncode})")
            result = destination / "graalpy.csv"
            actual = []
            if result.exists():
                with result.open(newline="") as stream: actual = list(csv.DictReader(stream, delimiter=";"))
            keys = list(expected[0]) if expected else []
            projected = [{key: row.get(key) for key in keys} for row in actual]
            if projected != expected:
                raise SystemExit(f"{scenario}: expected {expected}, got {projected}\n{completed.stdout}")
            if scenario == "reject":
                with (destination / "rejects.csv").open(newline="") as stream: bad = list(csv.DictReader(stream, delimiter=";"))
                if len(bad) != 1 or bad[0].get("value") != "5" or bad[0].get("code") != "BAD":
                    raise SystemExit(f"Invalid rejected input: {bad}")
            if scenario == "empty" and not all(token in completed.stdout for token in ["EMPTY_SETUP_OK", "EMPTY_CLOSE_OK"]):
                raise SystemExit(f"Empty-input lifecycle did not run:\n{completed.stdout}")
            print(f"Installed Hop GraalPy E2E OK: {scenario}")


if __name__ == "__main__":
    main()
