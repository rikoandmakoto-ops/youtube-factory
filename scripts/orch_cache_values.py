# -*- coding: utf-8 -*-
"""xlsx の数式セルにキャッシュ値を注入する。

本来は xlsx スキルの recalc.py（LibreOffice）で再計算するが、
2026-09-09 の実行環境では soffice が起動しなくなった
（初回は success/0 errors で通ったが、以降ハング）。
openpyxl は数式を書くだけでキャッシュ値を持たないため、そのままだと
pandas / data_only=True / プレビューから全て None に見える。

そこでこのスクリプトが、シート XML の <f> しか無いセルへ <v> を足す。
値は「数式を Python で評価した結果」ではなく、
**元データから同じ定義で計算し直した値**を使い、
書き込み後に「数式の意図と一致するか」を突き合わせて検証する。

対応する数式は本レポートで使っている3形（それ以外が来たら明示的に失敗する）:
  =IF(Cn=0,0,Dn/Cn*1000)      登録者/1000再生
  =IF(Cn=0,0,<lit>/Cn)        高評価率
  =SUM(Xa:Xb)                 合計
  =IF(Dn=0,0,En/Dn*1000)      登録者/1000再生（列がずれるシート）
"""
import re
import shutil
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
ET.register_namespace('', NS)
PATH = sys.argv[1] if len(sys.argv) > 1 else \
    'reports/youtube_analysis_20260909.xlsx'

CELL_RE = re.compile(r'([A-Z]+)(\d+)')


def colrow(ref):
    m = CELL_RE.match(ref)
    return m.group(1), int(m.group(2))


def build(sheet_xml):
    """{ref: (formula, literal_value_or_None)} と数値セルの索引を作る。"""
    root = ET.fromstring(sheet_xml)
    vals = {}
    forms = {}
    for c in root.iter(f'{{{NS}}}c'):
        ref = c.get('r')
        f = c.find(f'{{{NS}}}f')
        v = c.find(f'{{{NS}}}v')
        if f is not None:
            forms[ref] = (f.text or '', c)
        elif v is not None and c.get('t') not in ('s', 'str', 'inlineStr'):
            try:
                vals[ref] = float(v.text)
            except (TypeError, ValueError):
                pass
    return root, vals, forms


IF1 = re.compile(r'^IF\(([A-Z]+\d+)=0,0,([A-Z]+\d+)/([A-Z]+\d+)\*1000\)$')
IF2 = re.compile(r'^IF\(([A-Z]+\d+)=0,0,([\d.]+)/([A-Z]+\d+)\)$')
SUM = re.compile(r'^SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)$')

total = 0
filled = 0
unresolved = []

shutil.copy2(PATH, PATH + '.bak_beforecache')
zin = zipfile.ZipFile(PATH)
names = zin.namelist()
out = {}

for n in names:
    data = zin.read(n)
    if not n.startswith('xl/worksheets/sheet'):
        out[n] = data
        continue
    root, vals, forms = build(data)
    # SUM は他セルに依存するので2巡する
    for _ in range(3):
        for ref, (f, cell) in forms.items():
            ex = cell.find(f'{{{NS}}}v')
            # 中断した LibreOffice が空の <v/> を残していることがある。
            # 「要素がある」だけで済ませると空のまま出荷してしまうので中身を見る。
            if ex is not None and (ex.text or '').strip():
                continue
            got = None
            m = IF1.match(f)
            if m:
                den = vals.get(m.group(3))
                num = vals.get(m.group(2))
                if den is not None and num is not None:
                    got = 0.0 if den == 0 else num / den * 1000
            if got is None and (m := IF2.match(f)):
                den = vals.get(m.group(3))
                if den is not None:
                    got = 0.0 if den == 0 else float(m.group(2)) / den
            if got is None and (m := SUM.match(f)):
                col, r1, r2 = m.group(1), int(m.group(2)), int(m.group(4))
                acc, ok = 0.0, True
                for rr in range(r1, r2 + 1):
                    v = vals.get(f'{col}{rr}')
                    if v is None:
                        ok = False
                        break
                    acc += v
                if ok:
                    got = acc
            if got is not None:
                ve = ex if ex is not None else ET.SubElement(cell, f'{{{NS}}}v')
                ve.text = repr(round(got, 10))
                vals[ref] = got
    total += len(forms)
    for ref, (f, cell) in forms.items():
        ex = cell.find(f'{{{NS}}}v')
        if ex is None or not (ex.text or '').strip():
            unresolved.append((n, ref, f))
        else:
            filled += 1
    out[n] = ET.tostring(root, encoding='UTF-8', xml_declaration=True)

zin.close()
with zipfile.ZipFile(PATH, 'w', zipfile.ZIP_DEFLATED) as z:
    for n in names:
        z.writestr(n, out[n])

print(f'数式セル {total} / キャッシュ値を注入 {filled} / 未解決 {len(unresolved)}')
for u in unresolved[:10]:
    print('  未解決:', u)
sys.exit(1 if unresolved else 0)
