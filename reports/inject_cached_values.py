#!/usr/bin/env python3
"""openpyxl が書いた数式セルに「計算済みの値」を後から埋める。

なぜ必要か（2026-09-11）:
    openpyxl は数式を文字列として書くだけで、キャッシュ値を持たない。そのため
    recalc（LibreOffice）を通すまで pandas / load_workbook(data_only=True) /
    各種プレビューからは数式セルが全部 None に見える。
    このサンドボックスでは soffice が繰り返し OOM kill（exit 137）されるため、
    recalc を通せない日がある。数式を値に置き換えてしまうと「入力を変えても
    再計算されない」ため、**数式は数式のまま残し、キャッシュ値だけを注入する**。

    Excel / LibreOffice で開けば通常どおり再計算される（キャッシュ値は
    開いた時点の表示用）。

使い方:
    from inject_cached_values import FormulaCache
    fc = FormulaCache()
    fc.put(ws, row, col, "=H5/G5*1000", 0.791, number_format="0.000")
    ...
    wb.save(path)
    fc.inject(path)   # 保存後に呼ぶ
"""

import re
import shutil
import zipfile
from xml.sax.saxutils import escape


class FormulaCache:
    """(シート名, セル座標) → 計算済み値 を覚えておき、保存後に XML へ注入する。"""

    def __init__(self):
        self._vals = {}   # sheet_title -> {coord: value}

    def put(self, ws, row, col, formula, value, number_format=None, font=None, border=None):
        """数式を書きつつ、その計算結果を控えておく。"""
        cell = ws.cell(row=row, column=col, value=formula)
        if number_format:
            cell.number_format = number_format
        if font is not None:
            cell.font = font
        if border is not None:
            cell.border = border
        self._vals.setdefault(ws.title, {})[cell.coordinate] = value
        return cell

    # -----------------------------------------------------------------
    def inject(self, path):
        """保存済み xlsx の各数式セルに <v> を足す。数式自体は消さない。"""
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            blobs = {n: z.read(n) for n in names}

        # シート名 → xl/worksheets/sheetN.xml の対応を作る
        wb_xml = blobs["xl/workbook.xml"].decode("utf-8")
        rels = blobs["xl/_rels/workbook.xml.rels"].decode("utf-8")
        # openpyxl は Target を Id より前に書く（Type → Target → Id の順）。
        # 属性の順序に依存しないよう、Relationship 要素ごとに個別に取り出す。
        rel_map = {}
        for el in re.findall(r"<Relationship\b[^>]*/?>", rels):
            rid = re.search(r'Id="([^"]+)"', el)
            tgt = re.search(r'Target="([^"]+)"', el)
            if rid and tgt:
                rel_map[rid.group(1)] = tgt.group(1)
        sheet_files = {}
        for m in re.finditer(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wb_xml):
            name, rid = m.group(1), m.group(2)
            tgt = rel_map.get(rid, "")
            tgt = tgt[1:] if tgt.startswith("/") else "xl/" + tgt.lstrip("/")
            sheet_files[name] = tgt.replace("xl/xl/", "xl/")

        injected = 0
        for sheet, coords in self._vals.items():
            fn = sheet_files.get(sheet)
            if not fn or fn not in blobs:
                continue
            xml = blobs[fn].decode("utf-8")

            def repl(m):
                nonlocal injected
                head, formula = m.group(1), m.group(2)
                coord = re.search(r'r="([A-Z]+\d+)"', head)
                if not coord or coord.group(1) not in coords:
                    return m.group(0)
                val = coords[coord.group(1)]
                if val is None or val == "":
                    return m.group(0)
                if isinstance(val, (int, float)):
                    body = f"<f>{formula}</f><v>{val!r}</v>"
                else:
                    head = re.sub(r'\st="[^"]*"', "", head) + ' t="str"'
                    body = f"<f>{formula}</f><v>{escape(str(val))}</v>"
                injected += 1
                return f"{head}>{body}</c>"

            # openpyxl は数式セルを次の形で書く（<v> は空のまま）:
            #   <c r="I5" s="6"><f>IF(G5=0,"",H5/G5*1000)</f><v></v></c>
            # 空の <v></v> も、<v> が無い形も両方受ける。値が既に入っているセルは触らない。
            xml = re.sub(r"(<c\b[^>]*?)><f>(.*?)</f>(?:<v\s*/>|<v>\s*</v>)?</c>",
                         repl, xml, flags=re.S)
            blobs[fn] = xml.encode("utf-8")

        tmp = path + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for n in names:
                z.writestr(n, blobs[n])
        shutil.move(tmp, path)
        return injected
