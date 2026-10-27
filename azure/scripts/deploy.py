                                                                                

                                                                                
                                                                               
   
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit
from package_function import package

ROOT=Path(__file__).resolve().parents[2]
STATE_DIR=Path.home()/'.event-horizon'
sys.path.insert(0,str(ROOT))
from demo_archive import validate as validate_demo


def write_private_json(path, value):
    path=Path(path)
    if path.is_symlink():raise OSError('Private output must not be a symbolic link')
    fd, temporary = tempfile.mkstemp(prefix='.eh-private-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            os.fchmod(stream.fileno(),0o600)
            json.dump(value,stream,indent=2)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def az(*args, json_output=True):
    result = subprocess.run(['az',*args,'--only-show-errors','-o','json' if json_output else 'none'],
                            capture_output=True,text=True)
    if result.returncode:
                                                                                 
        if args[:2] == ('acr','build') and 'TasksOperationsNotAllowed' in result.stderr:
            raise RuntimeError('Azure free-credit subscriptions cannot run ACR Tasks. Use --build-method local with a working Docker engine; no container image was built.')
        raise RuntimeError(f'Azure command failed: {args[0]} {args[1] if len(args)>1 else ""}; inspect Azure deployment diagnostics securely')
    return json.loads(result.stdout) if json_output and result.stdout.strip() else None


def deploy(group, name, template, parameters):
    with tempfile.TemporaryDirectory(prefix='eh-arm-') as folder:
        path=Path(folder)/'parameters.json'
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:
            json.dump({'$schema':'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#',
                       'contentVersion':'1.0.0.0','parameters':{k:{'value':v} for k,v in parameters.items()}},stream)
        response=az('deployment','group','create','--resource-group',group,'--name',name,
                    '--template-file',str(ROOT/'azure/infra'/template),'--parameters','@'+str(path))
    return {k:v['value'] for k,v in response['properties']['outputs'].items()}


def validate_foundry_endpoint(value):
    if not value:return
    parsed=urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or
            not parsed.hostname.endswith('.services.ai.azure.com') or
            not parsed.path.startswith('/api/projects/') or
            len(parsed.path.split('/')) != 4 or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            '[' in value or ']' in value or '(' in value or ')' in value):
        raise ValueError('Foundry endpoint must be the plain HTTPS project URL, without Markdown link syntax')


def check_build_method(method, subscription):
    if method == 'local':
        if not shutil.which('docker'):
            raise RuntimeError('Local image build requires Docker; install and start Docker before --apply --build-method local')
        for command in (['docker','info','--format','{{.ServerVersion}}'],['docker','buildx','version']):
            result=subprocess.run(command,capture_output=True,text=True)
            if result.returncode:
                raise RuntimeError('Docker engine and buildx must be running before --apply --build-method local')
        return
    subscription_info=az('rest','--method','get','--url',
        f'https://management.azure.com/subscriptions/{subscription}?api-version=2022-12-01')
    quota=subscription_info.get('subscriptionPolicies',{}).get('quotaId','')
    if quota.startswith(('FreeTrial','AzureForStudents')):
        raise RuntimeError('ACR Tasks are paused for this free-credit subscription. Use --build-method local with Docker; no Azure resources were changed by this run.')


def check_foundry(resource_id, deployment, subscription):
    match=re.fullmatch(
        r'/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft\.CognitiveServices/accounts/([^/]+)/projects/([^/]+)',
        resource_id,re.IGNORECASE)
    if not match or match.group(1).lower() != subscription.lower():
        raise RuntimeError('Foundry resource ID must name a project in the selected subscription')
    result=az('cognitiveservices','account','deployment','show',
              '--resource-group',match.group(2),'--name',match.group(3),
              '--deployment-name',deployment)
    if result.get('properties',{}).get('provisioningState') != 'Succeeded':
        raise RuntimeError('Foundry model deployment is not ready')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subscription',required=True)
    parser.add_argument('--resource-group',required=True)
    parser.add_argument('--location',required=True)
    parser.add_argument('--prefix',required=True)
    parser.add_argument('--foundry-resource-id',default='')
    parser.add_argument('--foundry-endpoint',default='')
    parser.add_argument('--model-deployment',default='')
    parser.add_argument('--build-method',choices=('acr','local'),default='acr',
                        help='Build in ACR Tasks or locally with Docker and push to ACR')
    parser.add_argument('--factual-only',action='store_true',help='Explicitly deploy without a cloud model for infrastructure testing')
    parser.add_argument('--operator-credentials',type=Path,default=STATE_DIR/'operator.json')
    parser.add_argument('--receipt',type=Path,default=STATE_DIR/'deployment.json')
    parser.add_argument('--apply',action='store_true',help='Create billable resources and deploy code')
    args=parser.parse_args()
    if not re.fullmatch('[a-z][a-z0-9]{2,11}',args.prefix):parser.error('prefix: 3–12 lowercase letters/digits, starting with a letter')
    foundry=[args.foundry_resource_id,args.foundry_endpoint,args.model_deployment]
    if any(foundry) and not all(foundry):parser.error('Supply all three Foundry arguments or none')
    if all(foundry) and args.factual_only:parser.error('Foundry and --factual-only cannot be combined')
    try:validate_foundry_endpoint(args.foundry_endpoint)
    except ValueError as error:parser.error(str(error))
    if args.operator_credentials.resolve().is_relative_to(ROOT):
        parser.error('Store operator credentials outside the source directory so they cannot enter a later build')
    if args.receipt.resolve().is_relative_to(ROOT):
        parser.error('Store deployment receipts outside the source directory')
    if args.operator_credentials.is_symlink():parser.error('Operator credentials path must not be a symbolic link')
    if args.apply and not all(foundry) and not args.factual_only:
        parser.error('Supply the three Foundry arguments for the assignment, or explicitly use --factual-only for infrastructure testing')
    try:demo=validate_demo()
    except ValueError as error:parser.error(str(error))
    print(json.dumps({'mode':'apply' if args.apply else 'plan','subscription':args.subscription,
        'resource_group':args.resource_group,'location':args.location,'prefix':args.prefix,
        'build_method':args.build_method,
        'resources':['Container Registry Basic','Container Apps (one always-on replica, 1 CPU / 2Gi)',
                     'Functions Linux Consumption Python 3.12','Blob Storage LRS','Application Insights','Log Analytics (1 GB/day cap)'],
        'foundry':'existing project and model' if all(foundry) else 'local factual fallback; no model configured',
        'demo_archive':demo,
        'operator_access':'Public viewer; password required for editorial controls and restart',
        'cost_notice':'Apply creates billable resources. Limits are not a subscription spending cap.',
        'not_production':'One demo match and one replica; shared editor login is intended for a controlled demo.'},ensure_ascii=False,indent=2))
    if not args.apply:return
    if args.operator_credentials.parent==STATE_DIR or args.receipt.parent==STATE_DIR:
        if STATE_DIR.is_symlink():raise ValueError('Private state directory must not be a symbolic link')
        STATE_DIR.mkdir(mode=0o700,exist_ok=True)
        STATE_DIR.chmod(0o700)
    if not shutil.which('az'):raise RuntimeError('Azure CLI is required')
    if not args.operator_credentials.parent.is_dir():raise ValueError('Operator credentials directory does not exist')
    account=az('account','show')
    if account['id']!=args.subscription:raise RuntimeError('Signed-in subscription differs; select it explicitly before deployment')
    if all(foundry):check_foundry(args.foundry_resource_id,args.model_deployment,args.subscription)
    check_build_method(args.build_method,args.subscription)
    with tempfile.TemporaryDirectory(prefix='eh-bicep-') as folder:
        az('bicep','build','--file',str(ROOT/'azure/infra/foundation.bicep'),'--outfile',str(Path(folder)/'foundation.json'),json_output=False)
        az('bicep','build','--file',str(ROOT/'azure/infra/app.bicep'),'--outfile',str(Path(folder)/'app.json'),json_output=False)
    az('group','create','--name',args.resource_group,'--location',args.location,json_output=False)
    az('deployment','group','validate','--resource-group',args.resource_group,
       '--template-file',str(ROOT/'azure/infra/foundation.bicep'),
       '--parameters',f'prefix={args.prefix}',f'location={args.location}',
       'ingestToken=validation-only-placeholder-1234567890')
    token=secrets.token_urlsafe(48)
    operator_password=secrets.token_urlsafe(32)
    outputs=deploy(args.resource_group,'eh-foundation','foundation.bicep',{'prefix':args.prefix,'location':args.location,'ingestToken':token})
    with tempfile.TemporaryDirectory(prefix='eh-function-') as folder:
        path=package(Path(folder)/'function.zip')
        az('functionapp','deployment','source','config-zip','--resource-group',args.resource_group,
           '--name',outputs['functionName'],'--src',str(path),'--build-remote','true',json_output=False)
    keys=az('functionapp','keys','list','--resource-group',args.resource_group,'--name',outputs['functionName'])
    function_key=keys['functionKeys']['default']
    tag='point11-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    if args.build_method == 'local':
        image_tag=f'{outputs["registryServer"]}/event-horizon:{tag}'
        az('acr','login','--name',outputs['registryName'],json_output=False)
        result=subprocess.run(['docker','buildx','build','--platform','linux/amd64',
            '--tag',image_tag,'--push',str(ROOT)],capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError('Local Docker build or push failed; inspect Docker diagnostics securely')
    else:
        az('acr','build','--registry',outputs['registryName'],'--image',f'event-horizon:{tag}',str(ROOT),json_output=False)
    manifest=az('acr','repository','show','--name',outputs['registryName'],'--image',f'event-horizon:{tag}')
    image=f'{outputs["registryServer"]}/event-horizon@{manifest["digest"]}'
    if all(foundry):
        foundry_account_scope=args.foundry_resource_id.rsplit('/projects/',1)[0]
        az('role','assignment','create','--assignee-object-id',outputs['identityPrincipalId'],
           '--assignee-principal-type','ServicePrincipal','--scope',foundry_account_scope,
           '--role','53ca6127-db72-4b80-b1b0-d745d6d5456d',json_output=False)
    app=deploy(args.resource_group,'eh-app','app.bicep',{'prefix':args.prefix,'location':args.location,
        'image':image,'functionUrl':outputs['functionUrl'],'functionKey':function_key,'ingestToken':token,
        'operatorPassword':operator_password,
        'foundryEndpoint':args.foundry_endpoint,'modelDeployment':args.model_deployment})
    write_private_json(args.operator_credentials,{'url':app['url']+'/editor','username':'editor','password':operator_password})
    receipt={**app,'image':image,'resource_group':args.resource_group,'monitor':outputs['monitorName'],
             'operator_credentials_file':str(args.operator_credentials),
             'deployed_utc':datetime.now(timezone.utc).isoformat(),'live_inference_verified':False,
             'monitor_delivery_verified':False,'next':'Run smoke.py against the URL and confirm trace delivery in Azure Monitor.'}
    write_private_json(args.receipt,receipt)
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
