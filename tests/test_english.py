                                                                              
from pathlib import Path
import re
import unittest

from app import MatchSession
from locales import LANGUAGES
from simulation import GeneratorSettings


class EnglishProjectTests(unittest.TestCase):
    def test_source_and_documentation_have_no_cyrillic_copy(self):
        root = Path(__file__).resolve().parents[1]
        for path in root.rglob('*'):
            if path.suffix not in ('.py', '.js', '.cjs', '.html', '.md', '.json', '.bicep'):
                continue
            with self.subTest(file=str(path.relative_to(root))):
                self.assertIsNone(re.search(r'[\u0400-\u04ff]', path.read_text()))

    def test_english_default_and_german_copy_preserve_episode_facts(self):
        self.assertEqual(LANGUAGES, ('en', 'cs', 'de', 'fr', 'it', 'es', 'pt'))
        session = MatchSession(GeneratorSettings(42, 'counterattack'), wall_clock=lambda: 0)
        session.pump(15)
        english = session.snapshot(selected='moment-8')
        german = session.snapshot(language='de', selected='moment-8')
        a = english['experience']['selected']
        b = german['experience']['selected']
        self.assertEqual(a['language'], 'en')
        self.assertIn('Shot', a['title'])
        self.assertIn('Schuss', b['title'])
        self.assertEqual(a['facts'], b['facts'])
        self.assertEqual(a['evidence_ids'], b['evidence_ids'])
        self.assertEqual(a['fact_fingerprint'], b['fact_fingerprint'])
        self.assertNotEqual(a['what'], b['what'])
        self.assertIn('Raumgewinn', german['pipeline']['receipts'][-1]['explanation'])
