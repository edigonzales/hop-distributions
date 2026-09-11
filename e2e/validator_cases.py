from pathlib import Path
from xml.sax.saxutils import escape
import sqlite3


def transform(name, kind, body, x):
    return f'<transform><name>{name}</name><type>{kind}</type><copies>1</copies><distribute>Y</distribute>{body}<GUI><xloc>{x}</xloc><yloc>160</yloc></GUI></transform>'

def pipeline(work, fixtures, case):
    configured = case == 'configured'
    field = 'missing_path' if case == 'missing-field' else 'file_path'
    source = '' if configured else transform('Files', 'DataGrid', '''<fields><field><name>file_path</name><type>String</type><length>-1</length><precision>-1</precision></field></fields><data>'''+''.join(f'<line><item>{escape(str(fixtures / f))}</item></line>' for f in ('valid.xtf','second.xtf'))+'</data>', 100)
    validator = transform('Validate', 'INTERLIS_ILIVALIDATOR_TRANSFORM', f'''<useFilePathField>{'N' if configured else 'Y'}</useFilePathField><filePathField>{field}</filePathField><staticFilePath>${{FIXTURES}}/valid.xtf</staticFilePath><modelNames>TransferInputTest</modelNames><repositoryUrls>{escape(str(fixtures))}</repositoryUrls><configMode>STATIC</configMode><metaConfigMode>STATIC</metaConfigMode><failPipelineOnInvalid>Y</failPipelineOnInvalid><outputIsValidField>is_valid</outputIsValidField><outputValidationMessageField>validation_message</outputValidationMessageField>''', 340)
    output = transform('Results', 'TextFileOutput', f'''<separator>;</separator><enclosure>"</enclosure><header>Y</header><footer>N</footer><format>UNIX</format><encoding>UTF-8</encoding><compression>None</compression><file><name>{escape(str(work/case))}</name><extension>csv</extension><split>N</split><haspartno>N</haspartno><append>N</append><add_date>N</add_date><add_time>N</add_time><splitevery>0</splitevery></file><fields><field><name>is_valid</name><type>Boolean</type><format/></field><field><name>validation_message</name><type>String</type></field></fields>''', 570)
    hops = ('' if configured else '<hop><from>Files</from><to>Validate</to><enabled>Y</enabled></hop>')+'<hop><from>Validate</from><to>Results</to><enabled>Y</enabled></hop>'
    xml = f'<?xml version="1.0" encoding="UTF-8"?><pipeline><info><name>{case}</name><pipeline_type>Normal</pipeline_type><parameters><parameter><name>FIXTURES</name><default_value>{escape(str(fixtures))}</default_value></parameter></parameters></info><order>{hops}</order>{source}{validator}{output}</pipeline>'
    path=work/(case+'.hpl'); path.write_text(xml); return path
