"""Extract contract terms from TXT documents with traceable citations."""
import re
from datetime import date

MONTHS = {'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12}
DATE_RX = r'(?:\d{1,2}[./]\d{1,2}[./]\d{4}|\d{1,2}\s+(?:'+'|'.join(MONTHS)+r')\s+\d{4}(?:\s*года|\s*г\.?)?)'
ID = re.compile(r'\b[A-ZА-Я]{2,8}[-–]\d{2,8}(?:[-/]\d+)?\b',re.I)
MONEY = re.compile(r'(\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?|\d{4,12}(?:[.,]\d{1,2})?)\s*(?:руб(?:лей|ля|ль|\.)?|₽)',re.I)
DATES = re.compile(DATE_RX,re.I)
AMOUNT_KEY = re.compile(r'сумм\w*|стоимост\w*|цен\w*\s+(?:договора|контракта|поставки)',re.I)
DELIVERY_KEY = re.compile(r'срок\w*\s+поставк\w*|поставк\w*\s+(?:до|не\s+позднее|запланир\w*|осуществ\w*)|дат\w*\s+поставк\w*|поставить\s+(?:товар\s+)?до',re.I)

def parse_date(s):
    s=s.lower().strip().replace('года','').replace('г.','').strip()
    m=re.fullmatch(r'(\d{1,2})[./](\d{1,2})[./](\d{4})',s)
    if m:
        try: return date(int(m[3]),int(m[2]),int(m[1]))
        except ValueError: return None
    m=re.fullmatch(r'(\d{1,2})\s+([а-яё]+)\s+(\d{4})',s)
    if m and m[2] in MONTHS:
        try: return date(int(m[3]),MONTHS[m[2]],int(m[1]))
        except ValueError: return None
    try: return date.fromisoformat(s)
    except ValueError: return None

def paragraphs(t):
    return [x.strip() for x in t.replace('\r\n','\n').replace('\r','\n').split('\n') if x.strip()]

def kind_of(p):
    first=' '.join(p[:4]).lower()
    if re.search('проект|черновик|неподписанн',first): return 'draft'
    if re.search('письмо|предложение поставщика|уведомление',first) and not re.search('дополнительное соглашение',first):return 'letter'
    if re.search(r'дополнительн\w*\s+соглашени',first):return 'amendment'
    if re.search(r'договор\w*\s+поставк',first):return 'contract'
    return 'unknown'

def signatures(t,kind):
    if kind!='amendment':return 'not_applicable'
    if re.search(r'не\s+подписан|без\s+подпис|подпис\w*\s+отсутств|ожидает\s+подпис|проект',t,re.I):return 'unsigned'
    if re.search(r'подписан\w*\s+(?:обеими\s+сторонами|сторонами|поставщиком\s+и\s+покупателем)',t,re.I):return 'signed'
    if re.search(r'подпись\s+поставщика\s*[:—-]\s*\S+',t,re.I) and re.search(r'подпись\s+покупателя\s*[:—-]\s*\S+',t,re.I):return 'signed'
    return 'unknown'

def effective_date(t):
    m=re.search(r'(?:вступает\s+в\s+силу|действует|применяется)\s+с\s*('+DATE_RX+')',t,re.I)
    if not m:m=re.search(r'дата\s+вступления\s+в\s+силу\s*[:—-]\s*('+DATE_RX+')',t,re.I)
    if m:return parse_date(m[1])
    if re.search('с момента подписания|со дня подписания',t,re.I):
        m=re.search(r'(?:подписано|дата подписания)\s*[:—-]?\s*('+DATE_RX+')',t,re.I)
        if m:return parse_date(m[1])
    return None

def extract(p,field):
    key=AMOUNT_KEY if field=='amount' else DELIVERY_KEY
    result=[]
    for i,para in enumerate(p):
        if not key.search(para):continue
        for j in [i]+([i+1] if len(para)<100 and i+1<len(p) else []):
            text=p[j]
            if field=='amount':
                m=MONEY.search(text)
                if not m:continue
                raw=re.sub(r'[ \u00a0\u202f]','',m[1])
                try:value=int(re.split(r'[,.]',raw)[0])
                except ValueError:continue
            else:
                matches=list(DATES.finditer(text))
                if not matches:continue
                # A date following "до" or "не позднее" is preferred to incidental dates.
                m=next((x for x in matches if re.search(r'(?:до|не позднее|на дату|по|к)\s*$',text[:x.start()],re.I)),matches[0])
                d=parse_date(m[0])
                if not d:continue
                value=d.isoformat()
            result.append({'value':value,'quote':text,'paragraph':j})
            break
    unique={}
    for a in result:unique.setdefault(str(a['value']),a)
    return list(unique.values())

def parse_document(name,text,index):
    p=paragraphs(text);kind=kind_of(p)
    ids=list(dict.fromkeys(x.upper().replace('–','-') for x in ID.findall(text)))
    cid=None
    # Prefer an explicit reference to the contract rather than a date or filename.
    for line in p[:8]:
        if re.search(r'договор|контракт',line,re.I):
            m=ID.search(line)
            if m:cid=m[0].upper().replace('–','-');break
    if not cid and len(ids)==1:cid=ids[0]
    supplier=None
    if kind=='contract':
        for line in p[:15]:
            m=re.search(r'поставщик\s*[:—-]\s*(.+)',line,re.I)
            if m:supplier=m[1].strip(' .;,');break
    eff=effective_date(text) if kind=='amendment' else None
    return {'id':f'doc-{index}','name':name,'text':text,'paragraphs':p,'kind':kind,
            'contract_id':cid,'referenced_ids':ids,'supplier':supplier,'signature':signatures(text,kind),
            'effective':eff.isoformat() if eff else None,
            'fields':{'amount':extract(p,'amount'),'delivery':extract(p,'delivery')}}

def display(field,v):
    if v is None:return 'нет данных'
    if field=='amount':return f'{v:,}'.replace(',',' ')+' ₽'
    return date.fromisoformat(v).strftime('%d.%m.%Y')

def answer_questions(contracts,as_of):
    byid={x['contract_id']:x for x in contracts}
    questions=[]
    for cid,field,q in [('STN-101','delivery','Какой срок поставки действует по договору STN-101?'),
                        ('STN-102','amount','Какова сумма договора STN-102?'),
                        ('STN-103','amount','Какова сумма договора STN-103?')]:
        c=byid.get(cid)
        questions.append({'question':q,'answer':c[field]['display'] if c else 'договор не загружен',
                          'evidence':c[field]['evidence'] if c else None,
                          'warning':bool(c and (c['warnings'] or c[field]['status']=='review'))})
    matches=[]
    for c in contracts:
        f=c['delivery']
        if f['value'] and date.fromisoformat(f['value'])<date(2026,4,1):
            matches.append({'contract_id':c['contract_id'],'delivery':f['display'],
                            'unsanctioned_change':bool(f['proposals']),
                            'review':bool(f['to_review'] or c['warnings']),'evidence':f['evidence']})
    questions.append({'question':'По каким договорам поставка раньше 1 апреля 2026 года? Есть ли несогласованные изменения?',
                      'answer':'; '.join(f"{m['contract_id']} ({m['delivery']}, несогласованное изменение: {'да' if m['unsanctioned_change'] else 'нет'})" for m in matches) or 'Нет подтвержденных сроков раньше 01.04.2026',
                      'matches':matches,'warning':any(c['delivery']['status'] in ('missing','review') or c['warnings'] for c in contracts)})
    return questions

def check_documents(items,as_of='2026-03-10'):
    target=date.fromisoformat(as_of)
    docs=[parse_document(x['name'],x['text'],i) for i,x in enumerate(items)]
    result=[]
    for base in (d for d in docs if d['kind']=='contract'):
        cid=base['contract_id']; alerts=[];related=[]
        if not cid:alerts.append('Не удалось установить номер договора')
        for d in docs:
            if d['id']==base['id']:continue
            if cid and d['contract_id']==cid:related.append(d)
            elif cid and cid in d['referenced_ids']:alerts.append('Неоднозначная связь с '+d['name'])
        fields={}
        for field in ('amount','delivery'):
            originals=base['fields'][field];changes=[];proposals=[];review=[]
            winner={**originals[0],'file':base['name'],'doc_id':base['id']} if len(originals)==1 else None
            status='ok' if winner else ('review' if len(originals)>1 else 'missing')
            if len(originals)>1:alerts.append('Противоречивое значение в исходном договоре: '+field)
            for d in related:
                entries=[{**e,'file':d['name'],'doc_id':d['id']} for e in d['fields'][field]]
                if not entries:continue
                if d['kind']=='amendment':
                    eff=parse_date(d['effective']) if d['effective'] else None
                    if d['signature']=='signed' and eff and eff<=target:
                        if len(entries)==1:changes.append((eff,entries[0]))
                        else:review.append({'reason':'Несколько значений в допсоглашении','entries':entries})
                    elif d['signature']=='signed' and eff and eff>target:
                        proposals.append({'reason':'Вступит в силу после даты проверки','entries':entries})
                    else:review.append({'reason':'Не подтверждены подписи или дата действия','entries':entries})
                else:
                    proposals.append({'reason':'Письмо / проект: условия не изменены','entries':entries})
            changes.sort(key=lambda x:x[0])
            if changes:
                last=changes[-1][0];tied=[v for dt,v in changes if dt==last]
                if len({str(v['value']) for v in tied})>1:
                    winner=None;status='review';alerts.append('Конфликт действующих изменений')
                else:winner=tied[-1];status='changed'
            if review:alerts.append('Нужно проверить статус изменений: '+field)
            fields[field]={'value':winner['value'] if winner else None,
                           'display':display(field,winner['value'] if winner else None),
                           'status':status,'evidence':winner,
                           'applied_changes':[{'effective':dt.isoformat(),'evidence':e} for dt,e in changes],
                           'proposals':proposals,'to_review':review}
        result.append({'contract_id':cid or 'не определён','supplier':base['supplier'] or 'нет данных',
                       'base_file':base['name'],'amount':fields['amount'],'delivery':fields['delivery'],
                       'related':[{'name':d['name'],'kind':d['kind'],'signature':d['signature'],'effective':d['effective']} for d in related],
                       'warnings':list(dict.fromkeys(alerts))})
    for c in result:
        if sum(x['contract_id']==c['contract_id'] for x in result)>1:
            c['warnings'].append('Повторный номер договора')
    known={c['contract_id'] for c in result}
    orphan=[{'name':d['name'],'contract_id':d['contract_id'],'kind':d['kind'],'reason':'Нет соответствующего договора'} for d in docs if d['kind']!='contract' and d['contract_id'] not in known]
    return {'as_of':as_of,'contracts':result,'documents':docs,'unlinked':orphan,'questions':answer_questions(result,as_of)}
