                                                                                     

import hashlib

from content import CAPTION_LIMIT, caption_text


class EditorialConflict(ValueError):
    pass


class EditorialDesk:
    def __init__(self):
        self.records = {}
        self.active_id = None
        self.active_language = "en"
        self.revision = 0
        self.history = []

    def state(self, moment, insights=None, language="en"):
        record = self.records.get(moment.id if language=="en" else moment.id+":"+language)
        changed_source = (record is not None and insights is not None and
                          record.get('fact_fingerprint') != insights.fact_fingerprint(moment))
        if record is None or record['moment_revision'] != moment.revision or changed_source:
            packet = insights.moment_data(moment) if insights and all(key in insights.events for key in moment.evidence_ids) else None
            return {'status': 'draft', 'moment_revision': moment.revision,
                    'copy': caption_text(moment,language,packet), 'receipt': None, 'language':language}
        return record.copy()

    def act(self, insights, moment_id, revision, action, text=None, language="en"):
        moment = insights.moments.get(moment_id)
        if moment is None:
            raise ValueError('Episode not found.')
        if revision != moment.revision:
            raise EditorialConflict('The episode changed. Review the current revision.')
        record = self.state(moment, insights, language)
        if action == 'review':
            if not moment.complete or not insights.verified(moment):
                raise ValueError('Wait for the episode to finish and its sources to be verified.')
            if (not isinstance(text, str) or not 1 <= len(text.strip()) <= CAPTION_LIMIT
                    or text.strip().count('\n') > 1):
                raise ValueError(f'Broadcast caption: up to {CAPTION_LIMIT} characters and no more than two lines.')
            record.update(status='checked', copy=text.strip())
            record['fact_fingerprint'] = insights.fact_fingerprint(moment)
            record['copy_fingerprint'] = hashlib.sha256(record['copy'].encode()).hexdigest()
            record['receipt'] = hashlib.sha256((language + record['fact_fingerprint'] + record['copy_fingerprint']).encode()).hexdigest()[:16]
        elif action == 'select':
            if record['status'] != 'checked' or not moment.complete or not insights.verified(moment):
                raise ValueError('Confirm your review of the current material revision before selecting it.')
            if text is not None and (not isinstance(text, str) or text.strip() != record['copy']):
                raise EditorialConflict('The text changed after review. Confirm the review again.')
            record['status'] = 'selected'
            self.active_id = moment_id
            self.active_language = language
        elif action == 'hold':
            record['status'] = 'held'
            if self.active_id == moment_id and self.active_language==language:
                self.active_id = None
        else:
            raise ValueError('Unknown editorial action.')
        self.records[moment_id if language=="en" else moment_id+":"+language] = record
        self.revision += 1
        self.history.append({'action': action, 'moment_id': moment_id, 'revision': revision,
                             'language':language, 'time': round(insights.clock, 2), 'receipt': record.get('receipt')})
        return record.copy()

    def snapshot(self, insights, language="en"):
        items = []
        for moment in reversed(list(insights.moments.values())):
            data = insights.moment_data(moment)
            data['editorial'] = self.state(moment, insights, language)
            items.append(data)
        active = next((item for item in items if item['id'] == self.active_id and self.active_language==language and item['editorial']['status'] == 'selected'), None)
        return {'revision': self.revision, 'items': items, 'active': active,
                'selected_count': sum(item['editorial']['status'] == 'selected' for item in items),
                'audit': self.history[-12:]}
