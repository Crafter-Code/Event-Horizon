                                                                                  
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[2]


def package(target):
    with ZipFile(target,'w',ZIP_DEFLATED) as archive:
        for name in ('function_app.py','host.json','requirements.txt'):
            archive.write(ROOT/'azure/function'/name,name)
        for name in ('cloud_contract.py','ingress.py','observability.py'):
            archive.write(ROOT/name,name)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    print(package(parser.parse_args().output))
