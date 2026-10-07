"""Installed row-validator scenarios adapted from the plugin's E2E suite."""
import csv
from datetime import datetime
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

FIXTURES = Path(__file__).resolve().parent / 'row-validator' / 'fixtures'
FIELDS = ('key', 'amount', 'start', 'finish', 'extra')
CASES = ('valid', 'late-unique', 'full-constraint', 'single-constraint',
         'single-invalid', 'empty', 'single-parallel', 'full-parallel', 'temporal')
VALIDATION_FAILURES = {'late-unique', 'full-constraint', 'single-invalid'}
INSTANT = '2024-02-29T23:30:00.123Z'


def input_rows(case):
    rows = [] if case == 'empty' else [
        (str(i), '9999' if case == 'single-invalid' and i == 1 else '3',
         '9' if 'constraint' in case else '1', '2', f' extra-{i}; "ä<&>" ')
        for i in range(4)
    ]
    if case == 'late-unique':
        rows[-1] = ('0', *rows[-1][1:])
    return rows


def transform(name, kind, body, x, copies=1):
    return (f'<transform><name>{name}</name><type>{kind}</type><copies>{copies}</copies>'
            f'<distribute>Y</distribute>{body}'
            f'<GUI><xloc>{x}</xloc><yloc>160</yloc></GUI></transform>')


def create_pipeline(work, fixtures, case):
    single = case.startswith('single')
    source = transform('Input', 'DataGrid', '<fields>' + ''.join(
        f'<field><name>{name}</name><type>String</type><length>-1</length>'
        '<precision>-1</precision></field>' for name in FIELDS
    ) + '</fields><data>' + ''.join(
        '<line>' + ''.join(f'<item>{escape(v)}</item>' for v in row) + '</line>'
        for row in input_rows(case)
    ) + '</data>', 100)
    mappings = '<mappings>' + ''.join(
        f'<mapping><attribute>{name}</attribute><field>{name}</field></mapping>'
        for name in FIELDS[:-1]
    ) + '</mappings>'
    validator = transform('Validate', 'INTERLIS_ROW_VALIDATOR_TRANSFORM',
        '<modelNames>Rows</modelNames><modelSources>${MODEL_DIR}</modelSources>'
        '<className>Rows.Data.Row</className>'
        f'<singlePassOnly>{"Y" if single else "N"}</singlePassOnly>'
        '<cacheRows>1</cacheRows><compress>Y</compress>'
        f'<tempDirectory>{escape(str(work / "spool"))}</tempDirectory>'
        f'<reportDirectory>{escape(str(work / "validation-reports"))}</reportDirectory>'
        f'<sourceRowField>extra</sourceRowField>{mappings}', 340,
        copies=2 if case.endswith('parallel') else 1)
    output = transform('Output', 'TextFileOutput',
        '<separator>;</separator><enclosure>"</enclosure><header>Y</header>'
        '<enclosure_forced>Y</enclosure_forced><enclosure_fix_disabled>N</enclosure_fix_disabled>'
        '<footer>N</footer><format>UNIX</format><encoding>UTF-8</encoding>'
        '<compression>None</compression>'
        f'<file><name>{escape(str(work / case))}</name><extension>csv</extension>'
        '<split>N</split><haspartno>N</haspartno><append>N</append>'
        '<add_date>N</add_date><add_time>N</add_time><splitevery>0</splitevery></file>'
        # Export every incoming field so schema changes cannot be hidden by selection.
        '<fields/>', 580)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><pipeline>'
        f'<info><name>row-validator-{case}</name><pipeline_type>Normal</pipeline_type>'
        '<parameters><parameter><name>MODEL_DIR</name>'
        f'<default_value>{escape(str(fixtures))}</default_value>'
        '</parameter></parameters></info><order>'
        '<hop><from>Input</from><to>Validate</to><enabled>Y</enabled></hop>'
        '<hop><from>Validate</from><to>Output</to><enabled>Y</enabled></hop></order>'
        f'{source}{validator}{output}</pipeline>')
    tree = ET.fromstring(xml)
    if case == 'temporal':
        source, validator, _ = tree.findall('transform')
        field = ET.SubElement(source.find('fields'), 'field')
        for name, value in {'name': 'instant', 'type': 'Date',
                            'format': "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
                            'length': '-1', 'precision': '-1'}.items():
            ET.SubElement(field, name).text = value
        for line in source.findall('data/line'):
            ET.SubElement(line, 'item').text = INSTANT
        validator.find('modelNames').text = 'TimeGate'
        validator.find('className').text = 'TimeGate.Data.Row'
        ET.SubElement(validator, 'timeZone').text = 'Europe/Zurich'
        mappings = validator.find('mappings')
        mappings.clear()
        for attribute, name in [('key', 'key'), ('day', 'instant'),
                                ('clock', 'instant'), ('moment', 'instant')]:
            mapping = ET.SubElement(mappings, 'mapping')
            ET.SubElement(mapping, 'attribute').text = attribute
            ET.SubElement(mapping, 'field').text = name
    path = work / (case + '.hpl')
    ET.ElementTree(tree).write(path, encoding='utf-8', xml_declaration=True)
    return path


def verify_reports(paths, case):
    """Reject partial reports and inconsistent validation/release accounting."""
    copies = 2 if case == 'single-parallel' else 1
    assert len(paths) == copies, (case, 'Report count', paths)
    failed = case in VALIDATION_FAILURES
    ends, copy_ids, run_ids = [], set(), set()
    for path in paths:
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        types = [record['record_type'] for record in records]
        assert types and types[0] == 'run_start' and types[-1] == 'run_end', (path, types)
        assert all(types.count(kind) == 1 for kind in
                   ('run_start', 'validation_end', 'run_end')), (path, types)
        start, end = records[0], records[-1]
        validation = next(r for r in records if r['record_type'] == 'validation_end')
        assert start['schema_version'] == 1, start
        assert start['mode'] == ('single_pass' if case.startswith('single') else 'full'), start
        assert start['class'] == ('TimeGate.Data.Row' if case == 'temporal' else 'Rows.Data.Row'), start
        if case == 'temporal':
            assert start['time_zone'] == 'Europe/Zurich', start
        copy_ids.add(start['copy'])
        run_ids.add(start['run_id'])
        assert validation['release'] is (not failed), validation
        assert validation['complete'] is (case != 'single-invalid'), validation
        assert (validation['errors'] > 0) == failed and validation['warnings'] >= 0, validation
        assert end['status'] == ('validation_failed' if failed else 'success'), end
        assert end['input_rows'] == validation['input_rows'], (validation, end)
        assert 0 <= end['output_rows'] <= end['input_rows'], end
        if not failed:
            assert end['output_rows'] == end['input_rows'], end
        elif case != 'single-invalid':
            assert end['output_rows'] == 0, end
        issues = [r for r in records if r['record_type'] == 'issue']
        if failed:
            assert any(r['severity'] == 'ERROR' for r in issues), (path, issues)
        for issue in issues:
            if 'copy' in issue:
                assert issue['copy'] == start['copy'], issue
            if 'input_number' in issue:
                assert 1 <= issue['input_number'] <= end['input_rows'], issue
        ends.append(end)
    assert copy_ids == set(range(copies)) and len(run_ids) == copies, (copy_ids, run_ids)
    expected_input = 0 if case == 'empty' else (2 if case == 'single-invalid' else 4)
    expected_output = 1 if case == 'single-invalid' else (0 if failed else expected_input)
    assert sum(end['input_rows'] for end in ends) == expected_input, ends
    assert sum(end['output_rows'] for end in ends) == expected_output, ends
    return ends


def verify_output(work, case):
    path = work / (case + '.csv')
    if case in VALIDATION_FAILURES or case == 'full-parallel':
        # A stopped pipeline may not drain already emitted single-pass rowsets.
        # Their exact emission count is asserted in the validator's report instead.
        if path.exists():
            with path.open(newline='', encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream, delimiter=';'))
            if case == 'single-invalid':
                assert [tuple(row[name] for name in FIELDS) for row in rows] in (
                    [], input_rows(case)[:1]), rows
            else:
                assert not rows, (case, rows)
        return
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream, delimiter=';')
        assert reader.fieldnames == list(FIELDS) + (['instant'] if case == 'temporal' else []), reader.fieldnames
        rows = list(reader)
    actual = [tuple(row[name] for name in FIELDS) for row in rows]
    expected = input_rows(case)
    if case == 'single-parallel':
        actual, expected = sorted(actual), sorted(expected)
    assert actual == expected, (case, actual, expected)
    if case == 'temporal':
        expected_instant = datetime.fromisoformat(INSTANT.replace('Z', '+00:00'))
        assert all(datetime.fromisoformat(row['instant'].replace('Z', '+00:00')) == expected_instant
                   for row in rows), rows


def verify(pipeline, reports):
    work = reports / 'row-validator'
    work.mkdir()
    results = []
    for case in CASES:
        case_work = work / case
        (case_work / 'spool').mkdir(parents=True)
        definition = create_pipeline(case_work, FIXTURES, case)
        failed = case in VALIDATION_FAILURES or case == 'full-parallel'
        print(f'Row Validator E2E: {case}', flush=True)
        log = pipeline(definition, expected=1 if failed else 0)
        if case == 'full-parallel':
            assert 'Full validation requires exactly one transform copy and no partitioning' in log, log[-8000:]
            assert not list((case_work / 'validation-reports').glob('*.jsonl'))
            ends = []
        else:
            ends = verify_reports(sorted((case_work / 'validation-reports').glob('*.jsonl')), case)
        verify_output(case_work, case)
        assert not list((case_work / 'spool').iterdir()), (case, 'Temporary files leaked')
        results.append({'case': case, 'expected_failure': failed, 'reports': ends})
    (work / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
