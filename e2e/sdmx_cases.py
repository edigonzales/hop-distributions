"""Installed SDMX scenarios using a local server; no BFS access or plugin rebuild."""
import csv
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

FIXTURES = Path(__file__).resolve().parent / 'sdmx'


class FixtureHandler(BaseHTTPRequestHandler):
    mode = 'normal'
    requests = []

    def do_GET(self):
        type(self).requests.append(self.path)
        assert 'application/vnd.sdmx.' in self.headers.get('Accept', '')
        if '/dataflow/' in self.path:
            body = (FIXTURES / 'structure.json').read_bytes()
            if self.mode == 'schema-change':
                body = body.replace(b'Float', b'Decimal')
            content = 'application/vnd.sdmx.structure+json;version=1.0'
        elif '/data/' in self.path:
            query = parse_qs(urlsplit(self.path).query)
            year = query['startPeriod'][0]
            assert query['endPeriod'] == [year]
            assert '/Q_1.F_1.CHF.A?' in self.path
            assert 'labels=id' in self.headers['Accept']
            lines = (FIXTURES / 'observations.csv').read_text().splitlines()
            body = ('\n'.join([lines[0]] + [line for line in lines[1:] if f',{year},' in line]) + '\n').encode()
            if self.mode == 'delete':
                body = body.replace(b',I,', b',D,')
            content = 'application/vnd.sdmx.data+csv;version=2'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', content)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def verify(pipeline, reports):
    work = reports / 'sdmx'
    work.mkdir()
    FixtureHandler.mode = 'normal'
    FixtureHandler.requests = []
    server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f'http://127.0.0.1:{server.server_port}/rest'
    def execute(name, year='2023', expected=0):
        return pipeline(FIXTURES / 'health-financing.hpl', dict(
            SDMX_ENDPOINT=endpoint, START_PERIOD=year, END_PERIOD=year,
            OUTPUT_FILE=work / name), expected=expected)
    try:
        headers = []
        for year in ('2023', '2024'):
            execute(year, year)
            with (work / f'{year}.csv').open(newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file, delimiter=';')
                rows = list(reader)
                headers.append(reader.fieldnames)
            assert len(rows) == 1, rows
            row = rows[0]
            assert row['TIME_PERIOD'] == year and row['Q'] == 'Q_1' and row['Q_LABEL'] == 'Bund', row
            assert row['MULT'] == '6' and row['OBS_STATUS'] == 'A', row
            if year == '2023':
                assert float(row['OBS_VALUE']) == 397.708, row
            else:
                assert row['OBS_VALUE'] == '', row
        assert headers[0] == headers[1], headers
        FixtureHandler.mode = 'schema-change'
        FixtureHandler.requests.clear()
        log = execute('changed', expected=1)
        assert 'schema changed' in log, log
        assert not any('/data/' in path for path in FixtureHandler.requests)
        FixtureHandler.mode = 'delete'
        log = execute('delete', expected=1)
        assert 'Unsupported SDMX action D' in log, log
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print('Installed SDMX parameters, stable schema, labels, values and rejection checks passed', flush=True)
