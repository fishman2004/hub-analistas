"""Gera as 5 planilhas de exemplo dos painéis em tools/exemplos/, com dados 100% FICTÍCIOS.

Mesmas colunas e formatos das planilhas de verdade (docs/paineis.md), para testar o Hub e
apresentar os painéis sem expor números da empresa:

    .venv\\Scripts\\python -m tools.gerar_exemplos

O resultado é sempre o mesmo (sorteio com semente fixa): os testes contam com isso.
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from hub.paineis import FILES_BY_KEY

OUT = Path(__file__).parent / "exemplos"
MONTH_START = date(2026, 9, 1)
LAST_DAY = date(2026, 9, 17)  # uma quinta-feira: o mês "em andamento"
PASTAS = "ABCDEFG"
# quanto cada pasta já fez da meta do mês até o último dia (fictício, para os gráficos variarem)
PACE = {"A": .68, "B": .52, "C": .61, "D": .40, "E": .57, "F": .33, "G": .63}
POS_SCALE = {"A": 1.1, "B": 1.5, "C": .9, "D": 1.8, "E": 1.2, "F": 1.4, "G": .8}


def _xlsx(path: Path, header: list[str], rows: list[list]) -> None:
    book = Workbook()
    sheet = book.active
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="000000")
    for row in rows:
        sheet.append(row)
    book.save(path)


def generate(out: Path = OUT) -> None:
    rnd = random.Random(2026)
    out.mkdir(parents=True, exist_ok=True)
    name = lambda key, ext: out / (FILES_BY_KEY[key].base + ext)

    sellers = [(str(10 + i), f"VENDEDOR {i:02d}", f"SUPERVISOR {'XYZ'[i % 3]}") for i in range(1, 11)]
    suppliers = []  # (id, nome, grupo, pasta)
    next_id = 1001
    for pasta in PASTAS:
        for n in range(1, 4):
            group = f"FORNECEDOR {pasta}{n}"
            parts = 2 if n == 1 else 1  # o primeiro de cada pasta tem duas divisões unificadas
            for k in range(parts):
                label = group + (f" DIV {k + 1}" if parts > 1 else "")
                suppliers.append((str(next_id), label, group + (" UNIFICADA" if parts > 1 else ""), pasta))
                next_id += 1
    _xlsx(name("fornecedores", ".xlsx"), ["ID FORNECEDOR", "FORNECEDOR", "FORNECEDOR II", "PASTA"],
          [[int(s[0]), s[1], s[2], s[3]] for s in suppliers])

    products = []  # (id, nome, fornecedor)
    for i in range(1, 161):
        supplier = suppliers[i % len(suppliers)]
        products.append((str(5000 + i), f"PRODUTO {i:03d}", supplier))
    focos = ["FOCO PILHAS", "FOCO SANDÁLIAS", "FOCO HIGIENE", "FOCO ESPONJAS", "FOCO CABELOS", "FOCO FARMA"]
    foco_of = {p[0]: focos[i % len(focos)] for i, p in enumerate(products[:60])}
    _xlsx(name("focos", ".xlsx"), ["ID PRODUTO", "PRODUTO", "PRODUTO FOCO"],
          [[int(p[0]), p[1], foco_of[p[0]]] for p in products[:60]])

    goal_suppliers = [s for s in suppliers if not s[1].endswith("DIV 2")]  # a meta vem num ID só do grupo
    goals = []
    for sid, sname, sup in sellers:
        for s in goal_suppliers:
            goals.append([int(sid), sname, sup, int(s[0]), s[1], round(rnd.uniform(2500, 9000), 4),
                          round(rnd.randint(16, 30) * POS_SCALE[s[3]])])
    _xlsx(name("metas", ".xlsx"), ["ID VENDEDOR", "NOME DO VENDEDOR", "SUPERVISOR", "ID FORN", "NOME FORNECEDOR",
                                   "META FINANCEIRA", "META POSITIVAÇÃO"], goals)

    kpis = []
    for sid, sname, sup in sellers:
        for i, foco in enumerate(focos):
            meta = rnd.randint(20, 36) + 12 * i
            # META = positivação (clientes); META II = financeiro (só em alguns focos, como na planilha real)
            kpis.append([int(sid), sname, sup, foco, "VAREJO" if i < 4 else "FARMA", meta,
                         round(rnd.uniform(3000, 7000) * (1 + i / 2), 2) if i % 2 == 0 else None])
    _xlsx(name("metas_kpi", ".xlsx"), ["ID", "VENDEDOR", "SUPERVISOR", "PRODUTO FOCO", "CLASSIFICACAO", "META",
                                       "META II"], kpis)

    # vendas: pedidos sorteados e depois escalados para cada pasta chegar no ritmo de PACE
    clients = [(str(200000 + i), f"CLIENTE {i:04d}") for i in range(1, 301)]
    days = [MONTH_START + timedelta(n) for n in range((LAST_DAY - MONTH_START).days + 1)]
    lines = []
    order = 31000000
    for d in days:
        if d.weekday() == 6:
            continue
        for sid, sname, sup in sellers:
            for _ in range(rnd.randint(2, 5) if d.weekday() == 5 else rnd.randint(6, 12)):
                order += 1
                client = rnd.choice(clients)
                status = rnd.choice("FFFFFFLMB")  # cancelado não vem na extração
                for product in rnd.sample(products, rnd.randint(2, 6)):
                    qty = rnd.randint(1, 24)
                    lines.append([sid, sname, sup, order, status, d, client, product, qty, rnd.uniform(5, 40) * qty])
    meta_by_pasta = {p: 0.0 for p in PASTAS}
    pasta_of = {s[0]: s[3] for s in suppliers}
    for g in goals:
        meta_by_pasta[pasta_of[str(g[3])]] += g[5]
    sold = {p: 0.0 for p in PASTAS}
    for line in lines:
        sold[line[7][2][3]] += line[9]
    factor = {p: meta_by_pasta[p] * PACE[p] / sold[p] for p in PASTAS}
    with open(name("vendas", ".csv"), "w", newline="", encoding="cp1252") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ID RCA", "NOME RCA", "NOME SUPERVISOR", "NUMERO PEDIDO", "POSICAO PED", "DATA PEDIDO",
                    "ID CLIENTE", "CLIENTE", "ID PRODUTO", "NOME PRODUTO", "ID FORNECEDOR", "NOME FORNECEDOR",
                    "QTDE CX", "QTDE UND", "VALOR", "QTDE CX VENDIDA"])
        for sid, sname, sup, order, status, d, client, product, qty, value in lines:
            value *= factor[product[2][3]]
            br = lambda x: f"{x:.2f}".replace(".", ",")
            w.writerow([sid, sname, sup, order, status, d.strftime("%d/%m/%Y"), client[0], client[1], product[0],
                        product[1], product[2][0], product[2][1], 12, qty, br(value), br(qty / 12)])


if __name__ == "__main__":
    generate()
    print(f"Exemplos gravados em {OUT}")
