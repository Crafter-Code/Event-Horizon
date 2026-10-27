                                                               

                                                                                
                                                                             
                                                                             
   
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4
from cloud_contract import encode


class BlobEventJournal:
    def __init__(self, container, credential=None):
        self.container, self.credential = container, credential

    @classmethod
    def from_environment(cls):
        from azure.identity import ManagedIdentityCredential
        from azure.storage.blob import ContainerClient
        credential = ManagedIdentityCredential(client_id=os.getenv('AZURE_CLIENT_ID'))
        container = ContainerClient(account_url=os.environ['EVENT_HORIZON_BLOB_ACCOUNT_URL'],
            container_name=os.getenv('EVENT_HORIZON_BLOB_CONTAINER','match-evidence'),credential=credential,
            connection_timeout=3,read_timeout=5,retry_total=1)
        return cls(container,credential)

    def _put(self, name, payload):
        from azure.core.exceptions import ResourceExistsError, AzureError
        body = encode(payload)
        try:
            self.container.upload_blob(name,body,overwrite=False)
        except ResourceExistsError:
            try:existing = self.container.download_blob(name).readall()
            except AzureError as error:raise OSError('Azure event archive unavailable') from error
            if existing!=body:raise ValueError('Conflicting archived event')
        except AzureError as error:raise OSError('Azure event archive unavailable') from error

    def start(self, metadata):
        key = uuid4().hex
        self._put(f'{key}/metadata.json',{'metadata':metadata,'created_utc':datetime.now(timezone.utc).isoformat()})
        return key

    def append(self, key, events):
        for event in events:self._put(f'{key}/events/{event["id"]:09d}.json',event)

    def append_batch(self, key, events):
        if not events:return
        with ThreadPoolExecutor(max_workers=min(4,len(events))) as executor:
            futures=[executor.submit(self._put,f'{key}/events/{event["id"]:09d}.json',event) for event in events]
            for future in futures:future.result()

    def find(self, key, event_id):
        from azure.core.exceptions import ResourceNotFoundError, AzureError
        try:
            event = json.loads(self.container.download_blob(f'{key}/events/{event_id:09d}.json').readall())
            metadata = json.loads(self.container.download_blob(f'{key}/metadata.json').readall())['metadata']
            return {'event':event,'metadata':metadata,'run_key':key}
        except ResourceNotFoundError:return None
        except AzureError as error:raise OSError('Azure event archive unavailable') from error

    def runs(self):
        from azure.core.exceptions import AzureError
        try:
                                                                               
                                                                              
            result = []
            for prefix in self.container.walk_blobs(delimiter='/'):
                key = prefix.name.rstrip('/')
                meta_blob = self.container.get_blob_client(f'{key}/metadata.json')
                meta = json.loads(meta_blob.download_blob().readall())
                result.append({'run_key':key,**meta,'event_count':sum(1 for _ in self.container.list_blobs(name_starts_with=f'{key}/events/'))})
            return sorted(result,key=lambda r:r['created_utc'],reverse=True)[:30]
        except AzureError as error:raise OSError('Azure event archive unavailable') from error

    def close(self):
        self.container.close()
        if self.credential:self.credential.close()
