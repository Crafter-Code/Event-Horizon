import asyncio
from copy import deepcopy
import json
import unittest

from app import MatchSession
from foundry_narrative import FoundryNarrator, NumericGroundingError, compact_for_model, validate_draft
from simulation import GeneratorSettings


class Agent:
    def __init__(self, responses):
        self.responses=iter(responses)
        self.calls=[]

    async def run(self, prompt):
        self.calls.append(prompt)
        return json.dumps(next(self.responses))


class NumericGroundingTests(unittest.TestCase):
    def packet(self):
        return {'id':'moment-test','revision':1,'time':706,'team':0,'kind':'chance',
            'what':'Blue created a shot.','why':'The attack reached a shot after 6 completed passes.',
            'change':'In the last minute: shots 1:0, possession 58%:42%. A minute earlier, shots were 0:0.',
            'evidence_ids':[1],'evidence':[{'id':1,'time':706,'kind':'shot','team':0}],
            'facts':{'score':[0,0],'window':{'start':646,'end':706,'possession':[58,42],
                'shots':[1,0],'previous_shots':[0,0]}},'fact_fingerprint':'test-fingerprint'}

    def draft(self, packet):
        return {key:deepcopy(packet[key]) for key in ('what','why','change','evidence_ids')}

    def wrong_change(self):
        return ('In the last minute, Blue increased possession to 58% compared to 42% previously '
            'and recorded 1 shot while opponents had none, indicating a more active offense by '
            'Blue during this period. The score remains 0:0.')

    def test_writer_contract_errors_receive_one_checked_repair(self):
        packet=self.packet();safe=self.draft(packet)
        for invalid in ({**safe,'what':'x'*401},
                        {**safe,'what':'Invented score 999:999.'},
                        {**safe,'evidence_ids':[999]}):
            writer=Agent([invalid,safe]);verifier=Agent([{'approved':True,'unsupported_claims':[]}])
            narrator=FoundryNarrator(Agent([{'evidence_ids':[1]}]),writer,verifier)
            with self.subTest(invalid=invalid):
                self.assertEqual(asyncio.run(narrator.compose(packet)),safe)
                self.assertEqual(len(writer.calls),2)
                self.assertEqual(len(verifier.calls),1)
                self.assertEqual(narrator.trace()[0]['stages'][1]['reason'],'draft_contract')
                self.assertIn(json.dumps(safe,ensure_ascii=False),writer.calls[1])

    def test_repeated_writer_contract_error_cannot_be_verified(self):
        packet=self.packet();invalid={**self.draft(packet),'what':'x'*401}
        writer=Agent([invalid,invalid]);verifier=Agent([])
        narrator=FoundryNarrator(Agent([{'evidence_ids':[1]}]),writer,verifier)
        with self.assertRaises(ValueError):asyncio.run(narrator.compose(packet))
        self.assertEqual(len(writer.calls),2)
        self.assertEqual(verifier.calls,[])
        self.assertEqual(narrator.trace()[0]['status'],'fallback')

    def test_recorded_58_42_counterexample_is_rejected_in_every_text_field(self):
        packet=self.packet()
        for field in ('what','why','change'):
            with self.subTest(field=field):
                draft=self.draft(packet);draft[field]=self.wrong_change()
                with self.assertRaises(NumericGroundingError):validate_draft(draft,packet)

    def test_swapping_team_or_metric_with_existing_numbers_is_rejected(self):
        packet=self.packet()
        for wording in ('Blue had 42% possession and Red had 58%.',
                        'Blue completed 58 passes while Red completed 42.',
                        'Blue previously had 58% possession.',
                        'Blue increased possession compared with Red.'):
            draft=self.draft(packet);draft['what']=wording
            with self.subTest(wording=wording),self.assertRaises(NumericGroundingError):
                validate_draft(draft,packet)

    def test_reworded_percentage_claims_in_supported_languages_are_rejected(self):
        packet=self.packet()
        for wording in ('Blue had fifty-eight percent possession.',
                        'Blue hatte mehr Ballbesitz.', 'Blue měla vyšší držení míče.',
                        'Blue avait davantage de possession.', 'Blue aveva più possesso.',
                        'Blue tenía más posesión.', 'Blue tinha mais posse.'):
            draft=self.draft(packet);draft['why']=wording
            with self.subTest(wording=wording),self.assertRaises(NumericGroundingError):
                validate_draft(draft,packet)

    def test_calculated_numeric_copy_and_qualitative_explanation_are_accepted(self):
        packet=self.packet();draft=self.draft(packet)
        self.assertEqual(validate_draft(draft,packet),draft)
        draft['why']='The completed passing sequence led to a shot and an opportunity to score.'
        self.assertEqual(validate_draft(draft,packet),draft)

    def test_binding_labels_distinguish_team_shares_and_historical_shots(self):
        source=compact_for_model(self.packet())
        possession=[x for x in source['metric_bindings'] if x['metric']=='possession_percent']
        self.assertEqual([(x['team'],x['value'],x['start'],x['end']) for x in possession],
                         [('Blue',58,646,706),('Red',42,646,706)])
        previous=[x for x in source['metric_bindings'] if x['metric']=='shots' and x['end']==646]
        self.assertEqual([(x['team'],x['value'],x['start']) for x in previous],
                         [('Blue',0,586),('Red',0,586)])
        self.assertTrue(source['numeric_policy']['window_possession_is_current_team_pair'])

    def test_invalid_relation_is_repaired_before_the_verifier_can_approve(self):
        packet=self.packet();safe=self.draft(packet);unsafe={**safe,'change':self.wrong_change()}
        analyst=Agent([{'evidence_ids':[1]}]);writer=Agent([unsafe,safe])
        verifier=Agent([{'approved':True,'unsupported_claims':[]}])
        narrator=FoundryNarrator(analyst,writer,verifier)
        self.assertEqual(asyncio.run(narrator.compose(packet)),safe)
        self.assertEqual(len(verifier.calls),1)
        self.assertEqual(json.loads(verifier.calls[0])['draft'],safe)
        self.assertIn('copy source.change verbatim',writer.calls[1])
        self.assertEqual(narrator.trace()[0]['status'],'verified')
        self.assertEqual(narrator.trace()[0]['stages'][1]['reason'],'numeric_grounding')

    def test_repeated_invalid_relation_uses_fallback_without_verifier_approval(self):
        packet=self.packet();unsafe={**self.draft(packet),'change':self.wrong_change()}
        verifier=Agent([{'approved':True,'unsupported_claims':[]}])
        narrator=FoundryNarrator(Agent([{'evidence_ids':[1]}]),Agent([unsafe,unsafe]),verifier)
        with self.assertRaises(NumericGroundingError):asyncio.run(narrator.compose(packet))
        self.assertEqual(verifier.calls,[])
        self.assertEqual(narrator.trace()[0]['status'],'fallback')

    def test_application_rechecks_even_a_pretend_approved_model_result(self):
        live=MatchSession(GeneratorSettings(42,'counterattack'),wall_clock=lambda:0)
        live.pump(30)
        moment=next(m for m in live.insights.moments.values() if m.complete)
        packet=live.insights.moment_data(moment);before=deepcopy(packet['facts'])
        draft=self.draft(packet)
        draft['change']=packet['change']+' Blue increased possession.'
        self.assertTrue(live.apply_narrative((live.run_id,moment.id,moment.revision),draft))
        self.assertEqual(moment.ai_status,'fallback')
        self.assertEqual(moment.source,'local')
        self.assertIsNone(moment.interpretation)
        self.assertEqual(live.insights.moment_data(moment)['facts'],before)
        self.assertEqual(moment.change,packet['change'])

    def test_trusted_localized_copy_does_not_allow_translated_false_comparisons(self):
        from locales import story
        live=MatchSession(GeneratorSettings(42,'counterattack'),wall_clock=lambda:0)
        live.pump(15)
        packet=live.insights.moment_data(next(iter(live.insights.moments.values())))
        before=deepcopy(packet)
        for language in ('en','cs','de','fr','it','es','pt'):
            for audience in ('fan','analyst','player'):
                local=story(packet,language,audience)
                safe={field:local[field] for field in ('what','why','change')}
                safe['evidence_ids']=packet['evidence_ids'][:]
                if (language,audience)==('en','analyst'):safe=self.draft(packet)
                unsafe={**safe,'change':safe['change']+' Previously possession was higher.'}
                verifier=Agent([{'approved':True,'unsupported_claims':[]}])
                narrator=FoundryNarrator(Agent([{'evidence_ids':packet['evidence_ids']}]),
                    Agent([unsafe,safe]),verifier)
                with self.subTest(language=language,audience=audience):
                    self.assertEqual(asyncio.run(narrator.compose(packet,language,audience)),safe)
                    self.assertEqual(len(verifier.calls),1)
        self.assertEqual(packet,before)
