                                                                                 
import json,re,unittest
from pathlib import Path
from global_localization import LANGUAGES,NEW_LANGUAGES,PACKS,translate_text,translate_tree

class GlobalLocalizationTests(unittest.TestCase):
    def test_seven_supported_languages_and_static_asset_parity(self):
        self.assertEqual(LANGUAGES,('en','cs','de','fr','it','es','pt'))
        script=Path('global-locales.js').read_text()
        self.assertEqual(json.loads(script.removeprefix('window.EH_LOCALES=').rstrip(';\n')),PACKS)

    def test_placeholders_are_never_translated(self):
        for language,pack in PACKS.items():
            for source,target in pack.items():
                with self.subTest(language=language,source=source):
                    self.assertEqual(sorted(re.findall(r'\{[^{}]+\}',source)),sorted(re.findall(r'\{[^{}]+\}',target)))
        for lang in NEW_LANGUAGES:
            self.assertIn('{start}',translate_text('From {start} to {end}, the score stayed at {after}.',lang))

    def test_machine_fields_evidence_and_names_are_preserved(self):
        original={'audience':'analyst','kind':'shot','status':'completed','type':'pass','id':'moment-8','moment_id':'pressure-180','href':'/event?id=8&kind=pressure','schema_version':'eh-material-1','unit':'percent','language':'en','title':'Match statistics','actors':[{'name':'Max Rowan'}], 'facts':{'shots':[1,0],'team':'Blue'},'event':{'id':8,'kind':'shot'},'frame':[{'x':10,'y':20}],'evidence_ids':[8,9],'fact_fingerprint':'abc123'}
        for language in NEW_LANGUAGES:
            got=translate_tree(original,language)
            for key in original.keys()-{'language','title'}:self.assertEqual(got[key],original[key],key)
            self.assertEqual(got['language'],language);self.assertNotEqual(got['title'],original['title'])

    def test_authored_arc_preserves_score_and_time(self):
        for language in NEW_LANGUAGES:
            text=translate_text('From 00:00 to 45:00, the score moved from 0:0 to 2:1.',language)
            self.assertNotIn('the score',text)
            self.assertEqual(re.findall(r'\d+',text),['00','00','45','00','0','0','2','1'])

if __name__=='__main__':unittest.main()
