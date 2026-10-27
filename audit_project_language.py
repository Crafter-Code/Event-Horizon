                                                                               

                                                                            
                                                                             
   
import argparse
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote
import zlib

CYRILLIC = re.compile(r'[\u0400-\u04ff]')


def inspect_text(text, location, findings):
    if CYRILLIC.search(text):
        findings.append(location)


def inspect_value(value, location, findings):
    if isinstance(value, str):
        inspect_text(value, location, findings)
    elif isinstance(value, dict):
        for key, item in value.items():
            inspect_text(key, location, findings)
            inspect_value(item, location, findings)
    elif isinstance(value, list):
        for item in value:
            inspect_value(item, location, findings)


def audit(root):
    root = Path(root).resolve()
    findings = []
    files = records = 0
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if '.git' in relative.parts or '__pycache__' in relative.parts:
            continue
        files += 1
        if path.suffix == '.sqlite3':
            connection = sqlite3.connect('file:' + quote(str(path)) + '?mode=ro', uri=True)
            try:
                tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                for (table,) in tables:
                    identifier = '"' + table.replace('"', '""') + '"'
                    for row in connection.execute('SELECT * FROM ' + identifier):
                        records += 1
                        for value in row:
                            if isinstance(value, bytes):
                                try:
                                    value = zlib.decompress(value).decode('utf-8')
                                except (zlib.error, UnicodeDecodeError):
                                    continue
                            if isinstance(value, str):
                                inspect_text(value, str(relative) + ':' + table, findings)
                                try:
                                    inspect_value(json.loads(value), str(relative) + ':' + table, findings)
                                except json.JSONDecodeError:
                                    pass
            finally:
                connection.close()
        else:
            try:
                text = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                continue
            inspect_text(text, str(relative), findings)
            if path.suffix == '.json':
                inspect_value(json.loads(text), str(relative), findings)
    return {'files_checked': files, 'database_records_checked': records,
            'findings': sorted(set(findings)), 'passed': not findings}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    result = audit(args.root)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
