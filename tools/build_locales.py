                                                                           
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
pack=json.loads((ROOT/'global-locales.json').read_text())
assert set(pack)=={'cs','de','fr','it','es','pt'}
for language,entries in pack.items():
    for source,target in entries.items():
        assert isinstance(target,str) and target
        assert sorted(re.findall(r'\{[^{}]+\}',source))==sorted(re.findall(r'\{[^{}]+\}',target)),(language,source)
(ROOT/'global-locales.js').write_text('window.EH_LOCALES='+json.dumps(pack,ensure_ascii=False,separators=(',',':'))+';\n')
print('Validated six additional UI catalogues and regenerated the browser asset.')
