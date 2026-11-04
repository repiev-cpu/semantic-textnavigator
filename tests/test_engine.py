import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import check_documents,parse_date
SAMPLES=Path(__file__).resolve().parents[1]/'samples'
def doc(name,text):return {'name':name,'text':text}
class ContractTests(unittest.TestCase):
    def test_sample_six_files(self):
        result=check_documents([doc(p.name,p.read_text(encoding='utf8')) for p in sorted(SAMPLES.glob('*.txt'))])
        self.assertEqual(len(result['contracts']),3)
        byid={c['contract_id']:c for c in result['contracts']}
        self.assertEqual(byid['STN-101']['delivery']['value'],'2026-03-28')
        self.assertEqual(byid['STN-101']['delivery']['status'],'changed')
        self.assertEqual(byid['STN-102']['amount']['value'],750000)
        self.assertIsNone(byid['STN-103']['amount']['value'])
        self.assertEqual(byid['STN-103']['amount']['display'],'нет данных')
        self.assertTrue(byid['STN-101']['delivery']['proposals'])
        self.assertTrue(byid['STN-102']['delivery']['proposals'])
    def test_changed_amount_not_hardcoded(self):
        c=doc('new.txt','Договор поставки № ABC-888\nПоставщик: ООО «Звезда»\nСумма договора 45 600 руб.\nСрок поставки до 20 мая 2026 года.')
        self.assertEqual(check_documents([c])['contracts'][0]['amount']['value'],45600)
        c['text']=c['text'].replace('45 600','91 300')
        self.assertEqual(check_documents([c])['contracts'][0]['amount']['value'],91300)
    def test_unsigned_does_not_override(self):
        base=doc('a.txt','Договор поставки № ABC-777\nСрок поставки до 17 марта 2026 года.')
        amend=doc('b.txt','Дополнительное соглашение к договору ABC-777\nСрок поставки до 19 мая 2026 года.\nНе подписано сторонами.')
        v=check_documents([base,amend])['contracts'][0]['delivery']
        self.assertEqual(v['value'],'2026-03-17')
        self.assertTrue(v['to_review'])
    def test_future_signed_not_active(self):
        base=doc('a.txt','Договор поставки № ABC-777\nСрок поставки до 17 марта 2026 года.')
        amend=doc('b.txt','Дополнительное соглашение к договору ABC-777\nСрок поставки до 19 мая 2026 года.\nВступает в силу с 11 марта 2026 года.\nПодписано обеими сторонами.')
        v=check_documents([base,amend])['contracts'][0]['delivery']
        self.assertEqual(v['value'],'2026-03-17')
        self.assertTrue(v['proposals'])
    def test_signed_amount_evidence(self):
        base=doc('a.txt','Договор поставки № ABC-777\nСумма договора 50 000 рублей.')
        amend=doc('b.txt','Дополнительное соглашение к договору ABC-777\nСумма договора 120 000 руб.\nВступает в силу с 02 марта 2026 года.\nПодписано обеими сторонами.')
        v=check_documents([base,amend])['contracts'][0]['amount']
        self.assertEqual(v['value'],120000)
        self.assertEqual(v['evidence']['file'],'b.txt')
        self.assertEqual(v['evidence']['quote'],'Сумма договора 120 000 руб.')
    def test_missing_delivery(self):
        c=check_documents([doc('a.txt','Договор поставки № ABC-123\nСумма договора 7 000 руб.')])['contracts'][0]
        self.assertIsNone(c['delivery']['value'])
    def test_conflicting_amendments(self):
        base=doc('a.txt','Договор поставки № ABC-777\nСумма договора 100 000 руб.')
        mods=[doc(f'm{i}.txt',f'Дополнительное соглашение к договору ABC-777\nСумма договора {v} руб.\nВступает в силу с 05 марта 2026 года.\nПодписано обеими сторонами.') for i,v in enumerate([200000,300000])]
        v=check_documents([base,*mods])['contracts'][0]['amount']
        self.assertEqual(v['status'],'review')
        self.assertIsNone(v['value'])
    def test_invalid_date(self):
        self.assertEqual(parse_date('10 марта 2026 года').isoformat(),'2026-03-10')
        self.assertIsNone(parse_date('31 февраля 2026 года'))
    def test_before_effective_date(self):
        base=doc('a.txt','Договор поставки № ABC-777\nСрок поставки до 18 апреля 2026 года.')
        amend=doc('b.txt','Дополнительное соглашение к договору ABC-777\nСрок поставки до 28 марта 2026 года.\nВступает в силу с 05 марта 2026 года.\nПодписано обеими сторонами.')
        self.assertEqual(check_documents([base,amend],'2026-03-01')['contracts'][0]['delivery']['value'],'2026-04-18')
    def test_orphan(self):
        a=doc('letter.txt','Письмо поставщика по договору XYZ-444\nПросим изменить срок поставки до 18 апреля 2026 года.')
        self.assertEqual(len(check_documents([a])['unlinked']),1)
if __name__=='__main__':unittest.main()
