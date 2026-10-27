                                                                                   
from pathlib import Path
from copy import deepcopy
import json,re
from functools import lru_cache

LANGUAGES=('en','cs','de','fr','it','es','pt')
NEW_LANGUAGES=('fr','it','es','pt')
PACKS=json.loads(Path(__file__).with_name('global-locales.json').read_text())
PROTECTED={'name','names','audience','kind','status','type','id','run_id','viewer_key','token','mode','stage','action','metric','key','unit','scenario','provider','source','code','format','layout','target','role','state','facts','protected','frame','frame_png','geometry','observation','calibration','metadata','settings','event','source_event','scene_event','source_title','source_text','interpretation','fact_fingerprint','protected_sha256','evidence_ids','source_event_ids','event_sha256','run_key','match_id'}

NATIVE_WORDS={
 'fr':r'\b(?:ballon|équipe|séquence|réussies|joueur|faits|aperçu|résumé|mi-temps|pression|précédente)\b',
 'it':r'\b(?:pallone|palla|squadra|passaggi|giocatore|punteggio|possesso|partita|riepilogo|precedente|fotogrammi|primo|secondo)\b',
 'es':r'\b(?:balón|equipo|jugador|jugada|marcador|posesión|pases|partido|resumen|pantalla|anterior)\b',
 'pt':r'\b(?:bola|equipa|jogador|lance|marcador|posse|jogo|resumo|ecrã|remates|anterior)\b',
}
@lru_cache(maxsize=8)
def _native_values(language):return {v.casefold() for v in PACKS[language].values()}

@lru_cache(maxsize=8)
def _rules(language):
    pack=PACKS[language]
    folded={}
    for key,value in pack.items():folded.setdefault(key.casefold(),value)
    pattern=re.compile(r'(?<![\w])(?:'+'|'.join(re.escape(k) for k in sorted(pack,key=len,reverse=True))+r')(?![\w])',re.IGNORECASE)
    return pack,folded,pattern

@lru_cache(maxsize=8)
def _templates(language):
    result=[]
    for source,target in PACKS[language].items():
        fields=list(re.finditer(r'\{([A-Za-z_][A-Za-z_0-9]*)\}',source))
        if not fields:continue
        chunks=[];at=0
        for field in fields:
            chunks.append(re.escape(source[at:field.start()]))
            chunks.append(r'((?:(?!\. |\n).)*?)');at=field.end()
        chunks.append(re.escape(source[at:]))
        result.append((re.compile(''.join(chunks),re.IGNORECASE),[f.group(1) for f in fields],target))
    return sorted(result,key=lambda row:len(row[0].pattern),reverse=True)

@lru_cache(maxsize=8192)
def translate_text(text,language):
    if language not in PACKS or not isinstance(text,str) or 'EVENT HORIZON' in text.upper() or text.startswith(('/', 'https://', 'http://')):return text
    if text.casefold() in _native_values(language):return text
    if language in NATIVE_WORDS and re.search(NATIVE_WORDS[language],text,re.IGNORECASE):return text
    pack,folded,pattern=_rules(language)
    if text in pack:return pack[text]
    stripped=text.strip()
    if stripped in pack:return text.replace(stripped,pack[stripped],1)
                                                                              
    if '{' not in text:
        for regex,fields,target in _templates(language):
            match=regex.fullmatch(text)
            if match:
                values={field:translate_text(value,language) for field,value in zip(fields,match.groups())}
                return re.sub(r'\{([A-Za-z_][A-Za-z_0-9]*)\}',lambda m:values[m.group(1)],target)
    parts=re.split(r'(?<=\.) ',text)
    if len(parts)>1:
        return ' '.join(translate_text(part,language) for part in parts)
    tokens=[]
    def protect(match):
        tokens.append(match.group())
        return chr(0xe000)+str(len(tokens)-1)+chr(0xe001)
    safe=re.sub(r'\{[^{}]+\}',protect,text)
    safe=pattern.sub(lambda m:pack.get(m.group(),folded.get(m.group().casefold(),m.group())),safe)
    for index,token in enumerate(tokens):safe=safe.replace(chr(0xe000)+str(index)+chr(0xe001),token)
    return safe


def translate_tree(value,language,key='',audience='analyst'):
    if key in PROTECTED or key.endswith(('_id','_ids','_key','_hash','_fingerprint','_sha256','_version')) or key in {'href','url','endpoint','channel','metric_id','event_kind'}:return deepcopy(value)
    if isinstance(value,str):return translate_text(value,language)
    if isinstance(value,list):return [translate_tree(v,language,key,audience) for v in value]
    if isinstance(value,tuple):return tuple(translate_tree(v,language,key,audience) for v in value)
    if not isinstance(value,dict):return value
    result={k:(language if k=='language' and v in LANGUAGES else translate_tree(v,language,k,audience)) for k,v in value.items()}
    if language in NEW_LANGUAGES and {'kind','facts','evidence','what','why','change'}<=value.keys():
        from story_languages import native_story
        result.update(native_story(value,language,audience))
    if language in NEW_LANGUAGES and value.get('facts',{}).get('complete') and value.get('facts',{}).get('end')==5400 and 'text' in value:
        from story_languages import recap
        result['text']=recap(value,language,audience)['text']
    return result


class LocaleMap(dict):
    def __contains__(self,key):
        return dict.__contains__(self,key) or key in NEW_LANGUAGES and dict.__contains__(self,'en')
    def __missing__(self,key):
        if key in NEW_LANGUAGES and 'en' in self:return translate_tree(dict.__getitem__(self,'en'),key)
        raise KeyError(key)
    def get(self,key,default=None):
        try:return self[key]
        except KeyError:return default


def locale_map(value):return LocaleMap(value)
