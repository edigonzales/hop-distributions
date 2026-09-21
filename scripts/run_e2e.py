#!/usr/bin/env python3
"""Exercise the exact assembled distribution with local deterministic fixtures."""
from pathlib import Path
import argparse
import copy
import csv
import json
import os
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from build_hop_distribution import digest, normalize_zip_entry_name, validate_runtime

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'e2e'
sys.path.insert(0, str(FIXTURES))
import ili2db_cases
import validator_cases


def runtime_libraries(hop, system, machine):
    arch = 'arm64' if machine.lower() in {'arm64', 'aarch64'} else 'x86_64'
    platform_folder = 'win64' if system == 'win32' else ('osx/' if system == 'darwin' else 'linux/') + arch
    folders = [hop/'lib/core', hop/'lib/spark-client', hop/'lib/swt'/platform_folder]
    swt = folders[-1]/'swt.jar'
    if not swt.is_file():
        raise RuntimeError(f'Missing platform SWT: {swt}')
    return sorted(path for folder in folders for path in folder.glob('*.jar'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--work-dir',type=Path,required=True)
    args=p.parse_args()
    work=args.work_dir.resolve()
    if work.exists():
        raise SystemExit(f'Use a fresh E2E directory: {work}')
    work.mkdir(parents=True)
    validate_runtime(args.archive)
    with zipfile.ZipFile(args.archive) as z:
        for info in z.infolist():
            normalize_zip_entry_name(info.filename)
        z.extractall(work)
        for info in z.infolist():
            target=work/info.filename
            if target.is_file() and info.external_attr >> 16:
                target.chmod(info.external_attr >> 16)
    hop=work/'hop'
    reports=work/'reports';reports.mkdir()
    config=reports/'config'
    for kind in ['pipeline','workflow']:
        directory=config/f'metadata/{kind}-run-configuration';directory.mkdir(parents=True)
        (directory/'local.json').write_text(json.dumps({'name':'local','engineRunConfiguration':{'Local':{'safe_mode':True,'rowset_size':2}}}))
    env=dict(os.environ,HOP_CONFIG_FOLDER=str(config),HOP_AUDIT_FOLDER=str(reports/'audit'),
             HOP_METADATA_FOLDER=str(config/'metadata'),HOP_JAVA_HOME=os.environ.get('JAVA_HOME',''))
    launcher=hop/('hop-run.bat' if os.name=='nt' else 'hop-run.sh')
    java=Path(os.environ['JAVA_HOME'])/'bin'/('java.exe' if os.name=='nt' else 'java')
    javac=java.with_name('javac.exe' if os.name=='nt' else 'javac')
    counter=0
    def run(command, expected=0):
        nonlocal counter
        counter+=1
        logfile=reports/f'{counter:02d}.log'
        if Path(command[0]).stem in ('java','javac'):
            argfile=logfile.with_suffix('.args');argfile.write_text('\n'.join(json.dumps(str(a)) for a in command[1:]))
            command=[str(command[0]),'@'+str(argfile)]
        elif os.name=='nt' and str(command[0]).endswith('.bat'):
            command=['cmd.exe','/d','/s','/c',subprocess.list2cmdline([str(a) for a in command])]
        print(f'E2E {counter}: {Path(command[0]).name}',flush=True)
        with logfile.open('w',encoding='utf-8') as log:
            result=subprocess.run([str(a) for a in command],cwd=hop,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
        if (expected==0 and result.returncode!=0) or (expected!=0 and result.returncode==0):
            raise AssertionError(f'{logfile}: exit {result.returncode}\n'+logfile.read_text(errors='replace')[-16000:])
        return logfile.read_text(errors='replace')
    def pipeline(path, params=None, expected=0):
        command=[str(launcher),'-r','local','-f',str(path)]
        for key,value in (params or {}).items():command.extend(['-p',f'{key}={value}'])
        return run(command,expected)
    def rows(path):
        with path.open(newline='',encoding='utf-8') as f:return list(csv.reader(f,delimiter=';'))
    classes=reports/'classes';classes.mkdir()
    core_cp=os.pathsep.join(str(p) for p in runtime_libraries(hop, sys.platform, platform.machine()))
    full_cp=core_cp+os.pathsep+os.pathsep.join(str(p) for p in (hop/'plugins').rglob('*.jar'))
    run([str(javac),'-proc:none','-cp',core_cp,'-d',str(classes),str(FIXTURES/'RuntimeIdentityProbe.java'),str(FIXTURES/'DistributionRuntimeProbe.java')])
    for order in ['raster-first','geometry-first']:
        run([str(java),'-cp',str(classes)+os.pathsep+core_cp,'RuntimeIdentityProbe',order])
    run([str(java),*(['-XstartOnFirstThread'] if sys.platform=='darwin' else []),'-cp',str(classes)+os.pathsep+core_cp,'DistributionRuntimeProbe'])
    # Separate fixture process: its broad classpath is never used to execute Hop pipelines.
    run([str(javac),'-proc:none','-cp',full_cp,'-d',str(classes),str(FIXTURES/'RasterFixtures.java')])
    data=reports/'raster';data.mkdir()
    fixture_cmd=[str(java),'-cp',str(classes)+os.pathsep+full_cp,'RasterFixtures',str(FIXTURES),str(data)]
    run(fixture_cmd+['prepare'])
    pipeline(FIXTURES/'raster/clip.hpl',dict(INPUT_RASTER=data/'input.tif',OUTPUT_FILE=data/'clip.tif',BBOX_CRS='EPSG:2056',MIN_X=2600001,MIN_Y=1200001,MAX_X=2600003,MAX_Y=1200003,NODATA=255))
    tree=ET.parse(FIXTURES/'raster/reproject.hpl')
    raster=next(t for t in tree.getroot().findall('transform') if t.findtext('type')=='SOGIS_RASTER_VALUE_REPROJECT')
    raster.find('extentMode').text='AUTO'
    definition=reports/'reproject.hpl';tree.write(definition)
    pipeline(definition,dict(INPUT_RASTER=data/'input.tif',OUTPUT_FILE=data/'reproject.tif',TARGET_CRS='EPSG:21781',PIXEL_SIZE_X=1,PIXEL_SIZE_Y=1,OUTPUT_NODATA=255))
    pipeline(FIXTURES/'raster/zonal.hpl',dict(INPUT_VECTOR=data/'zones.gpkg',INPUT_LAYER='zones',INPUT_RASTER=data/'input.tif',GEOMETRY_CRS='EPSG:2056',NODATA=255,OUTPUT_FILE=data/'zonal.csv'))
    with (data/'zonal.csv').open(newline='') as f:zonal=list(csv.DictReader(f,delimiter=';'))
    assert len(zonal)==1 and zonal[0]['name']=='whole raster',zonal
    for key,value in {'raster_mean':5.5,'raster_min':0,'raster_max':11,'raster_count':12}.items():assert abs(float(zonal[0][key])-value)<1e-9,zonal
    for case,suffix in [('flatgeobuf','fgb'),('parquet','parquet')]:
        pipeline(FIXTURES/f'raster/{case}.hpl',dict(INPUT_VECTOR=data/'zones.gpkg',INPUT_LAYER='zones',OUTPUT_FILE=data/f'zones.{suffix}'))
        assert (data/f'zones.{suffix}').stat().st_size>4
    assert (data/'zones.parquet').read_bytes()[:4]==b'PAR1'
    run(fixture_cmd+['check'])
    geo=reports/'geometry';geo.mkdir();(geo/'geometry.csv').write_text('geometry\nPOINT (3 4)\nPOINT (7 8)\n')
    for case,expected in [('calculator',[['geometry','x_coord'],['POINT (3 4)','3.0'],['POINT (7 8)','7.0']]),('geoprocessing',[['geometry','centroid'],['POINT (3 4)','POINT (3 4)'],['POINT (7 8)','POINT (7 8)']])]:
        pipeline(FIXTURES/f'geometry/{case}.hpl',dict(E2E_INPUT_DIR=geo,E2E_OUTPUT_DIR=geo))
        output=geo/('geometry-calculator.csv' if case=='calculator' else 'geoprocessing.csv')
        assert rows(output)==expected,rows(output)
    # Exchange native Geometry rows across the independently packaged plugins.
    flow=ET.Element('pipeline')
    info=ET.SubElement(flow,'info');ET.SubElement(info,'name').text='geometry-interop'
    ET.SubElement(info,'pipeline_type').text='Normal'
    reader=copy.deepcopy(next(t for t in ET.parse(FIXTURES/'raster/zonal.hpl').getroot().findall('transform') if t.findtext('type')=='SOGIS_VECTOR_READER'))
    reader.find('fileName').text=str(data/'zones.gpkg')
    for element in reader.iter():
        if element.text=='${INPUT_LAYER}':element.text='zones'
    calculator=copy.deepcopy(next(t for t in ET.parse(FIXTURES/'geometry/calculator.hpl').getroot().findall('transform') if t.findtext('type')=='GEOMETRY_CALCULATOR_TRANSFORM'))
    calculator.find('operationId').text='AREA';calculator.find('outputFieldName').text='polygon_area'
    operation=copy.deepcopy(next(t for t in ET.parse(FIXTURES/'geometry/geoprocessing.hpl').getroot().findall('transform') if t.findtext('type')=='GEOMETRY_OPERATION_TRANSFORM'))
    writer=copy.deepcopy(next(t for t in ET.parse(FIXTURES/'geometry/calculator.hpl').getroot().findall('transform') if t.findtext('type')=='TextFileOutput'))
    writer.find('file/name').text=str(geo/'interop')
    writer.find('enclosure_forced').text='Y'
    conversion=copy.deepcopy(next(t for t in ET.parse(FIXTURES/'geometry/geoprocessing.hpl').getroot().findall('transform') if t.findtext('type')=='SelectValues'))
    geometry_meta=copy.deepcopy(conversion.find('fields/meta'));geometry_meta.find('name').text='geometry'
    conversion.find('fields').append(geometry_meta)
    chain=[reader,calculator,operation,conversion,writer]
    for transform in chain:flow.append(transform)
    order=ET.SubElement(flow,'order')
    for before,after in zip(chain,chain[1:]):
        link=ET.SubElement(order,'hop')
        for key,value in {'from':before.findtext('name'),'to':after.findtext('name'),'enabled':'Y'}.items():ET.SubElement(link,key).text=value
    definition=geo/'interop.hpl';ET.ElementTree(flow).write(definition);pipeline(definition)
    with (geo/'interop.csv').open(newline='') as f:interoperability=list(csv.DictReader(f,delimiter=';'))
    assert len(interoperability)==1 and abs(float(interoperability[0]['polygon_area'])-12)<1e-9,interoperability
    assert '2600002 1200001.5' in interoperability[0]['centroid'],interoperability
    json_output=reports/'json';json_output.mkdir()
    for case,output_name,expected_name in [
        ('stac-item','stac-item.json','stac-item.json'),
        ('links-array','links.json','links.json'),
    ]:
        pipeline(FIXTURES/f'json/{case}.hpl',dict(OUTPUT_DIR=json_output))
        actual=json.loads((json_output/output_name).read_text(encoding='utf-8'))
        expected=json.loads((FIXTURES/'json/expected'/expected_name).read_text(encoding='utf-8'))
        assert actual==expected, f'JSON builder example {case} differs from its expected document'
    interlis=reports/'interlis';interlis.mkdir()
    env['E2E_INPUT_DIR']=str(FIXTURES/'interlis/input');env['E2E_OUTPUT_DIR']=str(interlis)
    for case in ['roundtrip','check']:pipeline(FIXTURES/f'interlis/{case}.hpl',dict(E2E_INPUT_DIR=FIXTURES/'interlis/input',E2E_OUTPUT_DIR=interlis))
    result=rows(interlis/'interlis-roundtrip.csv')
    assert len(result)==3 and result[1][0]=='o1' and result[2][0]=='o2',result
    assert 'CIRCULARSTRING' in result[2][5] and '2600050 1200050' in result[2][5],result
    db=reports/'ili2db';db.mkdir()
    fixtures=FIXTURES/'ili2db/fixtures'
    for case in ['transform','action']:
        target=db/f'{case}.gpkg'
        definition=ili2db_cases.create_pipeline(db,fixtures,target) if case=='transform' else ili2db_cases.action_xml(fixtures,target)
        pipeline(definition)
        ili2db_cases.verify_gpkg(target)
    validation=reports/'validator';validation.mkdir()
    fixtures=validation/'fixtures';shutil.copytree(FIXTURES/'validator/fixtures',fixtures)
    shutil.copyfile(fixtures/'valid.xtf',fixtures/'second.xtf')
    for case in ['field','configured','missing-field']:
        definition=validator_cases.pipeline(validation,fixtures,case)
        log=pipeline(definition,expected=1 if case=='missing-field' else 0)
        if case=='missing-field':assert 'missing_path' in log
        else:
            result=rows(validation/f'{case}.csv')
            assert len(result)==(3 if case=='field' else 2),result
            assert all(row[0].lower() in ('y','true') for row in result[1:]),result
    # Reuse workflow scaffolding, replacing its ili2db action with ilivalidator.
    tree=ET.parse(ili2db_cases.action_xml(FIXTURES/'ili2db/fixtures',validation/'unused.gpkg'))
    action=next(a for a in tree.getroot().findall('./actions/action') if a.findtext('type')=='INTERLIS_ILI2DB_ACTION')
    original_name=action.findtext('name');action.clear()
    for name,value in {'name':original_name,'type':'INTERLIS_ILIVALIDATOR_ACTION','inputMode':'SINGLE','filePath':str(fixtures/'valid.xtf'),'modelNames':'TransferInputTest','repositoryUrls':str(fixtures)}.items():ET.SubElement(action,name).text=value
    definition=validation/'action.hwf';tree.write(definition);pipeline(definition)
    # Malformed input must fail both action and transform validation.
    (fixtures/'invalid.xtf').write_text('<broken>')
    action.find('filePath').text=str(fixtures/'invalid.xtf');tree.write(definition);pipeline(definition,expected=1)
    # Fail-on-invalid is exercised with actual incoming rows (field mode).
    invalid=ET.parse(validator_cases.pipeline(validation,fixtures,'field'))
    source=next(t for t in invalid.getroot().findall('transform') if t.findtext('name')=='Files')
    for item in source.findall('data/line/item'):item.text=str(fixtures/'invalid.xtf')
    definition=validation/'invalid.hpl';invalid.write(definition);pipeline(definition,expected=1)
    run([sys.executable,str(FIXTURES/'python/scripts/run-e2e.py'),'--hop-home',str(hop),'--work-dir',str(reports/'python')])
    (reports/'results.json').write_text(json.dumps({'result':'passed','archive_sha256':digest(args.archive),'commands':counter},indent=2)+'\n')
    print('All distribution E2E scenarios passed',flush=True)

if __name__=='__main__':main()
