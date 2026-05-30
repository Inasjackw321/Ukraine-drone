#!/usr/bin/env python3
"""
Ukraine Drone Map
Run:  python app.py           (prompts for credentials on first run)
      python app.py --setup   (re-run credential setup)
      python app.py --browser (open in browser instead of desktop window)
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Dependency pre-check — show a readable error before anything can crash
# ─────────────────────────────────────────────────────────────────────────────
def _check_deps() -> None:
    import importlib.util as _ilu
    required = {
        "fastapi":   "pip install fastapi",
        "uvicorn":   "pip install uvicorn[standard]",
        "telethon":  "pip install telethon",
        "aiofiles":  "pip install aiofiles",
        "websockets":"pip install websockets",
    }
    missing = [f"  {pkg:12s}  →  {cmd}" for pkg, cmd in required.items()
               if _ilu.find_spec(pkg) is None]
    if missing:
        print("\n  ── Missing packages ──────────────────────────────────")
        print("\n".join(missing))
        print("\n  Fix all at once:  pip install -r requirements.txt")
        print("─" * 54)
        input("\n  Press Enter to close…")
        sys.exit(1)

_check_deps()

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("ukraine-drone")

HERE   = Path(__file__).parent
WEB    = HERE / "web"
CONFIG = HERE / "config.json"

# ─────────────────────────────────────────────────────────────────────────────
# Ukrainian Locations  (lat, lon)
# ─────────────────────────────────────────────────────────────────────────────
LOCS: dict[str, tuple[float, float]] = {
    # ── oblasts (nominative + accusative + locative) ──────────────────────────
    "київська":          (50.52, 30.87),  "київщина":        (50.52, 30.87),
    "київщину":          (50.52, 30.87),  "київщині":        (50.52, 30.87),
    "харківська":        (49.99, 36.23),  "харківщина":      (49.99, 36.23),
    "харківщину":        (49.99, 36.23),  "харківщині":      (49.99, 36.23),
    "дніпропетровська":  (48.46, 35.05),  "дніпровська":     (48.46, 35.05),  "дніпропетровщина": (48.46, 35.05),
    "дніпропетровщину":  (48.46, 35.05),  "дніпропетровщині":(48.46, 35.05),
    "одеська":           (46.48, 30.72),  "одещина":         (46.48, 30.72),
    "одещину":           (46.48, 30.72),  "одещині":         (46.48, 30.72),
    "запорізька":        (47.84, 35.14),  "запоріжжя область":(47.84, 35.14), "запоріжщина":      (47.84, 35.14),
    "запоріжщину":       (47.84, 35.14),  "запоріжщині":     (47.84, 35.14),
    "миколаївська":      (46.98, 31.99),  "миколаївщина":    (46.98, 31.99),
    "миколаївщину":      (46.98, 31.99),  "миколаївщині":    (46.98, 31.99),
    "херсонська":        (46.64, 32.62),  "херсонщина":      (46.64, 32.62),
    "херсонщину":        (46.64, 32.62),  "херсонщині":      (46.64, 32.62),
    "донецька":          (48.02, 37.80),  "донеччина":       (48.02, 37.80),
    "донеччину":         (48.02, 37.80),  "донеччині":       (48.02, 37.80),
    "луганська":         (48.57, 39.31),  "луганщина":       (48.57, 39.31),
    "луганщину":         (48.57, 39.31),  "луганщині":       (48.57, 39.31),
    "сумська":           (50.91, 34.80),  "сумщина":         (50.91, 34.80),
    "сумщину":           (50.91, 34.80),  "сумщині":         (50.91, 34.80),
    "чернігівська":      (51.50, 31.29),  "чернігівщина":    (51.50, 31.29),
    "чернігівщину":      (51.50, 31.29),  "чернігівщині":    (51.50, 31.29),
    "полтавська":        (49.59, 34.55),  "полтавщина":      (49.59, 34.55),
    "полтавщину":        (49.59, 34.55),  "полтавщині":      (49.59, 34.55),
    "черкаська":         (49.44, 32.06),  "черкащина":       (49.44, 32.06),
    "черкащину":         (49.44, 32.06),  "черкащині":       (49.44, 32.06),
    "кіровоградська":    (48.51, 32.26),  "кіровоградщина":  (48.51, 32.26),
    "кіровоградщину":    (48.51, 32.26),  "кіровоградщині":  (48.51, 32.26),
    "вінницька":         (49.23, 28.47),  "вінниччина":      (49.23, 28.47),
    "вінниччину":        (49.23, 28.47),  "вінниччині":      (49.23, 28.47),
    "житомирська":       (50.25, 28.66),  "житомирщина":     (50.25, 28.66),
    "житомирщину":       (50.25, 28.66),  "житомирщині":     (50.25, 28.66),
    "хмельницька":       (49.42, 26.99),  "хмельниччина":    (49.42, 26.99),
    "хмельниччину":      (49.42, 26.99),  "хмельниччині":    (49.42, 26.99),
    "тернопільська":     (49.55, 25.59),  "тернопільщина":   (49.55, 25.59),
    "тернопільщину":     (49.55, 25.59),  "тернопільщині":   (49.55, 25.59),
    "рівненська":        (50.62, 26.25),  "рівненщина":      (50.62, 26.25),
    "рівненщину":        (50.62, 26.25),  "рівненщині":      (50.62, 26.25),
    "волинська":         (50.75, 25.33),  "волинь":          (50.75, 25.33),
    "волині":            (50.75, 25.33),
    "львівська":         (49.84, 24.03),  "львівщина":       (49.84, 24.03),
    "львівщину":         (49.84, 24.03),  "львівщині":       (49.84, 24.03),
    "закарпатська":      (48.62, 22.29),  "закарпаття":      (48.62, 22.29),
    "закарпатті":        (48.62, 22.29),
    "івано-франківська": (48.92, 24.71),  "прикарпаття":     (48.92, 24.71),
    "прикарпатті":       (48.92, 24.71),
    "чернівецька":       (48.29, 25.94),  "буковина":        (48.29, 25.94),
    "буковині":          (48.29, 25.94),

    # ── oblast centres ───────────────────────────────────────────────────────
    "київ":              (50.45, 30.52),  "kyiv":            (50.45, 30.52),   "києві": (50.45, 30.52),
    "харків":            (49.99, 36.23),  "kharkiv":         (49.99, 36.23),   "харкові": (49.99, 36.23),  "харкова": (49.99, 36.23),
    "дніпро":            (48.46, 35.05),  "dnipro":          (48.46, 35.05),   "дніпрі": (48.46, 35.05),
    "одеса":             (46.48, 30.72),  "одесі":           (46.48, 30.72),   "odesa": (46.48, 30.72),
    "запоріжжя":         (47.84, 35.14),  "запоріжжям":      (47.84, 35.14),   "запоріжжі": (47.84, 35.14),
    "миколаїв":          (46.98, 31.99),  "миколаєві":       (46.98, 31.99),   "миколаєвом": (46.98, 31.99), "миколаєва": (46.98, 31.99),
    "херсон":            (46.64, 32.62),  "херсоні":         (46.64, 32.62),
    "донецьк":           (48.02, 37.80),  "донецьку":        (48.02, 37.80),
    "луганськ":          (48.57, 39.31),  "луганську":       (48.57, 39.31),
    "суми":              (50.91, 34.80),  "сумах":           (50.91, 34.80),   "сумами": (50.91, 34.80),
    "чернігів":          (51.50, 31.29),  "чернігові":       (51.50, 31.29),
    "полтава":           (49.59, 34.55),  "полтаві":         (49.59, 34.55),
    "черкаси":           (49.44, 32.06),  "черкасах":        (49.44, 32.06),
    "вінниця":           (49.23, 28.47),  "вінниці":         (49.23, 28.47),
    "житомир":           (50.25, 28.66),  "житомирі":        (50.25, 28.66),
    "хмельницький":      (49.42, 26.99),  "хмельницькому":   (49.42, 26.99),
    "тернопіль":         (49.55, 25.59),  "тернополі":       (49.55, 25.59),
    "рівне":             (50.62, 26.25),  "рівного":         (50.62, 26.25),   "рівному": (50.62, 26.25),
    "луцьк":             (50.75, 25.33),  "луцьку":          (50.75, 25.33),
    "львів":             (49.84, 24.03),  "львові":          (49.84, 24.03),
    "ужгород":           (48.62, 22.29),  "ужгороді":        (48.62, 22.29),
    "івано-франківськ":  (48.92, 24.71),  "івано-франківську":(48.92, 24.71),
    "чернівці":          (48.29, 25.94),  "чернівцях":       (48.29, 25.94),
    "кропивницький":     (48.51, 32.26),  "кропивницькому":  (48.51, 32.26),

    # ── front-line / eastern cities ──────────────────────────────────────────
    "маріуполь":         (47.10, 37.54),  "маріуполі":       (47.10, 37.54),
    "бахмут":            (48.60, 37.99),  "бахмуті":         (48.60, 37.99),
    "авдіївка":          (48.14, 37.75),  "авдіївці":        (48.14, 37.75),
    "покровськ":         (48.28, 37.18),  "покровську":      (48.28, 37.18),
    "краматорськ":       (48.72, 37.58),  "краматорську":    (48.72, 37.58),
    "слов'янськ":        (48.86, 37.63),  "слов'янську":     (48.86, 37.63),
    "лиман":             (49.02, 37.83),  "лимані":          (49.02, 37.83),
    "вугледар":          (47.77, 37.25),  "вугледарі":       (47.77, 37.25),
    "торецьк":           (48.41, 37.85),  "торецьку":        (48.41, 37.85),
    "часів яр":          (48.58, 38.11),
    "костянтинівка":     (48.52, 37.71),  "костянтинівці":   (48.52, 37.71),
    "дружківка":         (48.62, 37.53),  "дружківці":       (48.62, 37.53),
    "куп'янськ":         (49.71, 37.61),  "куп'янська":      (49.71, 37.61),   "куп'янську": (49.71, 37.61),
    "ізюм":              (49.21, 37.27),  "ізюмі":           (49.21, 37.27),
    "лозова":            (48.89, 36.32),  "лозовій":         (48.89, 36.32),
    "чугуїв":            (49.83, 36.68),  "чугуєві":         (49.83, 36.68),
    "балаклія":          (49.46, 36.85),  "балаклії":        (49.46, 36.85),
    "сєвєродонецьк":     (48.95, 38.49),  "лисичанськ":      (48.89, 38.43),
    "рубіжне":           (49.02, 38.38),  "попасна":         (48.64, 38.37),
    "оріхів":            (47.57, 35.79),  "оріхові":         (47.57, 35.79),
    "гуляйполе":         (47.66, 36.26),  "токмак":          (47.25, 35.70),
    "пологи":            (47.49, 36.26),  "бердянськ":       (46.76, 36.80),
    "велика новосілка":  (47.85, 36.79),
    "мар'їнка":          (47.93, 37.52),  "мар'їнці":        (47.93, 37.52),
    "курахове":          (47.99, 37.27),  "курахові":        (47.99, 37.27),
    "новомихайлівка":    (47.83, 37.35),
    "очеретине":         (48.17, 37.53),

    # ── south / Kherson / Zaporizhzhia ───────────────────────────────────────
    "нікополь":          (47.57, 34.40),  "нікополі":        (47.57, 34.40),
    "мелітополь":        (46.85, 35.37),  "мелітополі":      (46.85, 35.37),
    "енергодар":         (47.50, 34.65),  "енергодарі":      (47.50, 34.65),
    "нова каховка":      (46.76, 33.38),  "новій каховці":   (46.76, 33.38),
    "каховка":           (46.82, 33.48),
    "генічеськ":         (46.17, 34.82),  "скадовськ":       (46.12, 32.91),
    "берислав":          (46.83, 33.42),  "олешки":          (46.61, 32.67),
    "гола пристань":     (46.52, 32.52),
    "василівка":         (47.44, 35.29),  "михайлівка":      (47.57, 35.23),

    # ── Dnipro / Zaporizhzhia region ─────────────────────────────────────────
    "кривий ріг":        (47.91, 33.39),  "кривому розі":    (47.91, 33.39),
    "кременчук":         (49.07, 33.42),  "кременчуці":      (49.07, 33.42),
    "марганець":         (47.65, 34.63),  "жовті води":      (48.35, 33.51),
    "павлоград":         (48.53, 35.87),
    "новомосковськ":     (48.63, 35.23),  "синельникове":    (48.32, 35.52),
    "дніпродзержинськ":  (48.50, 34.61),  "кам'янське":      (48.50, 34.61),

    # ── Mykolaiv / Odesa region ───────────────────────────────────────────────
    "вознесенськ":       (47.56, 31.32),  "южноукраїнськ":   (47.83, 31.17),
    "первомайськ":       (48.04, 30.85),  "нова одеса":      (47.31, 31.78),
    "вилкове":           (45.40, 29.58),  "білгород-дністровський": (46.19, 30.35),
    "ізмаїл":            (45.35, 28.84),  "рені":            (45.46, 28.29),

    # ── Kharkiv region suburbs / districts ───────────────────────────────────
    "мерефа":            (49.82, 36.07),  "дергачі":         (50.11, 36.10),
    "вовчанськ":         (50.29, 36.94),  "богодухів":       (50.17, 35.54),
    "золочів":           (50.08, 36.33),  "первомайський":   (49.40, 36.72),
    "великий бурлук":    (50.02, 37.17),  "великому бурлуку":(50.02, 37.17),
    "зміїв":             (49.68, 36.37),  "зміїві":          (49.68, 36.37),
    "шевченкове":        (49.69, 37.09),  "борова":          (49.37, 37.46),
    "сахновщина":        (48.77, 35.88),  "красноград":      (49.37, 35.45),
    "нова водолага":     (49.72, 35.89),

    # ── Sumy region ───────────────────────────────────────────────────────────
    "конотоп":           (51.24, 33.21),  "конотопі":        (51.24, 33.21),
    "шостка":            (51.87, 33.47),  "шостці":          (51.87, 33.47),
    "охтирка":           (50.31, 34.90),  "охтирці":         (50.31, 34.90),
    "глухів":            (51.68, 33.91),  "ромни":           (50.75, 33.47),
    "середина-буда":     (52.18, 34.03),  "путивль":         (51.33, 33.87),
    "лебедин":           (50.98, 34.48),  "лебедині":        (50.98, 34.48),
    "тростянець":        (50.48, 34.97),  "тростянці":       (50.48, 34.97),
    "недригайлів":       (50.86, 33.87),  "буринь":          (51.20, 33.79),
    "кролевець":         (51.55, 33.39),  "кролевці":        (51.55, 33.39),
    "дубов'язівка":      (51.36, 33.24),  "дубов'язівці":    (51.36, 33.24),
    "дубов'язівку":      (51.36, 33.24),
    "есмань":            (52.06, 33.98),  "хотінь":          (51.47, 34.57),
    "ямпіль":            (51.65, 33.59),  "білопілля":       (51.15, 34.30),
    "велика писарівка":  (50.34, 35.62),

    # ── Chernihiv region ──────────────────────────────────────────────────────
    "ніжин":             (51.05, 31.88),  "прилуки":         (50.59, 32.39),
    "новгород-сіверський":(51.99, 33.26), "коропець":        (52.49, 32.19),
    "семенівка":         (52.18, 32.57),
    "ічня":              (50.85, 32.40),  "ічні":            (50.85, 32.40),
    "борзна":            (51.25, 32.41),  "борзні":          (51.25, 32.41),
    "мена":              (51.52, 32.22),  "корюківка":       (51.78, 32.25),
    "козелець":          (51.12, 31.12),  "остер":           (50.95, 30.88),
    "городня":           (51.92, 31.59),

    # ── Kyiv region ───────────────────────────────────────────────────────────
    "буча":              (50.55, 30.23),  "бучі":            (50.55, 30.23),
    "ірпінь":            (50.52, 30.25),  "ірпені":          (50.52, 30.25),
    "бровари":           (50.51, 30.79),  "броварах":        (50.51, 30.79),
    "біла церква":       (49.80, 30.12),  "білій церкві":    (49.80, 30.12),
    "борисків":          (50.35, 30.96),  "васильків":       (50.18, 30.33),
    "фастів":            (50.07, 29.91),  "вишгород":        (50.59, 30.49),
    "обухів":            (50.11, 30.64),  "переяслав":       (50.06, 31.45),
    "бориспіль":         (50.35, 30.96),
    "яготин":            (50.26, 31.77),  "яготині":         (50.26, 31.77),
    "березань":          (50.35, 31.49),

    # ── Poltava region ────────────────────────────────────────────────────────
    "лубни":             (50.02, 33.00),  "гадяч":           (50.37, 33.99),
    "миргород":          (49.96, 33.61),  "пирятин":         (50.24, 32.51),
    "горішні плавні":    (49.01, 33.64),  "комсомольськ":    (49.01, 33.64),
    "нові санжари":      (49.36, 34.33),

    # ── Cherkasy / Kirovohrad region ──────────────────────────────────────────
    "умань":             (48.75, 30.22),  "умані":           (48.75, 30.22),
    "сміла":             (49.22, 31.87),  "золотоноша":      (49.66, 31.97),
    "олександрія":       (48.67, 33.11),  "світловодськ":    (49.05, 33.24),
    "знам'янка":         (48.72, 32.67),  "кропивницьк":     (48.51, 32.26),

    # ── Vinnytsia region ──────────────────────────────────────────────────────
    "козятин":           (49.72, 28.83),  "хмільник":        (49.56, 27.95),
    "бар":               (49.08, 27.69),  "тульчин":         (48.67, 28.86),
    "могилів-подільський":(48.45, 27.80),

    # ── Zhytomyr region ───────────────────────────────────────────────────────
    "бердичів":          (49.90, 28.60),  "коростень":       (50.95, 28.65),
    "новоград-волинський":(50.59, 27.61), "малин":           (50.77, 29.23),
    "коростишів":        (50.31, 29.06),

    # ── Khmelnytskyi / Vinnytsia region ──────────────────────────────────────
    "шепетівка":         (50.18, 27.06),  "нетішин":         (50.34, 26.65),
    "кам'янець-подільський":(48.68, 26.58), "хотин":         (48.51, 26.49),

    # ── Ternopil / Ivano-Frankivsk region ────────────────────────────────────
    "кременець":         (50.10, 25.73),  "збараж":          (49.66, 25.78),
    "чортків":           (49.02, 25.80),  "коломия":         (48.53, 25.05),
    "надвірна":          (48.63, 24.57),  "снятин":          (48.44, 25.57),
    "калуш":             (49.01, 24.36),  "долина":          (48.97, 23.99),

    # ── Lviv region ───────────────────────────────────────────────────────────
    "дрогобич":          (49.35, 23.51),  "борислав":        (49.29, 23.43),
    "трускавець":        (49.28, 23.50),  "стрий":           (49.26, 23.85),
    "самбір":            (49.52, 23.20),  "яворів":          (49.94, 23.39),
    "червоноград":       (50.39, 24.23),  "нововолинськ":    (50.73, 24.17),

    # ── Zakarpattia region ────────────────────────────────────────────────────
    "мукачеве":          (48.44, 22.72),  "мукачеві":        (48.44, 22.72),
    "берегове":          (48.20, 22.65),  "хуст":            (48.17, 23.29),
    "тячів":             (47.99, 23.57),  "рахів":           (48.05, 24.21),

    # ── Rivne / Volyn region ──────────────────────────────────────────────────
    "ковель":            (51.21, 24.71),
    "берестечко":        (50.36, 25.10),  "сарни":           (51.34, 26.59),
    "дубно":             (50.41, 25.74),  "острог":          (50.33, 26.52),
    "здолбунів":         (50.51, 26.25),  "костопіль":       (50.88, 26.44),

    # ── Luhansk region ────────────────────────────────────────────────────────
    "кремінна":          (49.06, 38.21),  "кремінній":       (49.06, 38.21),
    "старобільськ":      (49.27, 38.91),  "сватове":         (49.42, 38.17),

    # ── Military airfields ────────────────────────────────────────────────────
    "миргородський аеродром":  (49.96, 33.61),
    "старокостянтинів":        (49.75, 27.20),  "старокостянтинові":    (49.75, 27.20),
    "озерне":                  (50.57, 28.73),
    "канатове":                (48.55, 32.35),
    "авіабаза":                (49.75, 27.20),

    # ── geographic / cross-border ─────────────────────────────────────────────
    "крим":              (44.95, 34.10),  "crimea":          (44.95, 34.10),
    "керч":              (45.36, 36.47),  "керчі":           (45.36, 36.47),
    "севастополь":       (44.60, 33.52),  "севастополі":     (44.60, 33.52),
    "сімферополь":       (44.95, 34.10),  "джанкой":         (45.71, 34.38),
    "євпаторія":         (45.19, 33.37),  "феодосія":        (45.03, 35.38),
    "чорне море":        (45.50, 31.50),  "азовське море":   (46.00, 36.50),
    "білорусь":          (52.50, 28.00),  "мінськ":          (53.90, 27.57),
    "росія":             (51.00, 38.00),  "бєлгород":        (50.59, 36.59),
    "курськ":            (51.73, 36.19),  "воронеж":         (51.67, 39.18),
    "брянськ":           (53.24, 34.36),  "таганрог":        (47.21, 38.93),
    "ростов":            (47.23, 39.72),  "краснодар":       (45.04, 38.98),

    # ── English region names (for English-language posts) ────────────────────
    "zaporizhzhia region": (47.84, 35.14), "zaporizhia region": (47.84, 35.14),
    "kharkiv region":    (49.99, 36.23),   "chernihiv region":  (51.50, 31.29),
    "sumy region":       (50.91, 34.80),   "kyiv region":       (50.52, 30.87),
    "donetsk region":    (48.02, 37.80),   "luhansk region":    (48.57, 39.31),
    "dnipropetrovsk region": (48.46, 35.05), "kherson region":  (46.64, 32.62),
    "mykolaiv region":   (46.98, 31.99),   "odesa region":      (46.48, 30.72),
    "poltava region":    (49.59, 34.55),   "vinnytsia region":  (49.23, 28.47),
    "zhytomyr region":   (50.25, 28.66),   "cherkasy region":   (49.44, 32.06),

    # ── English city transliterations ────────────────────────────────────────
    "ichnya":            (50.85, 32.40),   "bakhmut":           (48.60, 37.99),
    "kupiansk":          (49.71, 37.61),   "kramatorsk":        (48.72, 37.58),
    "sloviansk":         (48.86, 37.63),   "lyman":             (49.02, 37.83),
    "avdiivka":          (48.14, 37.75),   "pokrovsk":          (48.28, 37.18),
    "toretsk":           (48.41, 37.85),   "chasiv yar":        (48.58, 38.11),
    "vuhledar":          (47.77, 37.25),   "izium":             (49.21, 37.27),
    "nikopol":           (47.57, 34.40),   "melitopol":         (46.85, 35.37),
    "zaporizhzhia":      (47.84, 35.14),   "chernihiv":         (51.50, 31.29),
    "mykolaiv":          (46.98, 31.99),   "odessa":            (46.48, 30.72),
    "mariupol":          (47.10, 37.54),   "kherson":           (46.64, 32.62),
    "poltava":           (49.59, 34.55),   "nizhyn":            (51.05, 31.88),
    "konotop":           (51.24, 33.21),   "shostka":           (51.87, 33.47),
    "okhtyrka":          (50.31, 34.90),   "lebedyn":           (50.98, 34.48),
    "brovary":           (50.51, 30.79),   "bila tserkva":      (49.80, 30.12),
    "fastiv":            (50.07, 29.91),   "boryspil":          (50.35, 30.96),
    "kremenchuk":        (49.07, 33.42),   "kryvyi rih":        (47.91, 33.39),
    "dnipropetrovsk":    (48.46, 35.05),   "severodonetsk":     (48.95, 38.49),
    "lysychansk":        (48.89, 38.43),   "rubizhne":          (49.02, 38.38),
    "kreminna":          (49.06, 38.21),   "svatove":           (49.42, 38.17),
    "starobilsk":        (49.27, 38.91),   "berdyansk":         (46.76, 36.80),
    "enerhodar":         (47.50, 34.65),   "nova kakhovka":     (46.76, 33.38),
    "henichesk":         (46.17, 34.82),   "novomoskovsk":      (48.63, 35.23),
    "pavlohrad":         (48.53, 35.87),   "vovchansk":         (50.29, 36.94),
    "chuhuiv":           (49.83, 36.68),   "izium":             (49.21, 37.27),
    "lozova":            (48.89, 36.32),   "balakliya":         (49.46, 36.85),
    "velykyi burluk":    (50.02, 37.17),   "zmiiv":             (49.68, 36.37),
}

# Pre-sorted once for find_locations() — longest key first for greedy matching
_LOCS_SORTED = sorted(LOCS.keys(), key=len, reverse=True)

# Cyrillic word pattern used in stem-matching pass
_CYR_WORD_RE = re.compile(r'[а-яґєіїА-ЯҐЄІЇ]{5,}')


def find_locations(text: str) -> list[dict]:
    """Return list of {name, lat, lon} found in text.

    Pass 1 — exact substring match (fast, covers explicit LOCS entries).
    Pass 2 — stem match: strips up to 6 trailing chars from Cyrillic words
              to handle Ukrainian case endings and adjectival forms not
              explicitly listed (e.g. "харківського" → "харків",
              "конотопом" → "конотоп", "краматорського" → "краматорськ").
    """
    tl = text.lower()
    results: list[dict] = []
    covered: list[tuple[int, int]] = []

    # ── Pass 1: exact match ───────────────────────────────────────────────────
    for key in _LOCS_SORTED:
        i = tl.find(key)
        if i == -1:
            continue
        end = i + len(key)
        if any(s <= i and end <= e for s, e in covered):
            continue
        covered.append((i, end))
        results.append({"name": text[i:end], "lat": LOCS[key][0], "lon": LOCS[key][1]})

    # ── Pass 2: stem match for words not already covered ─────────────────────
    for m in _CYR_WORD_RE.finditer(tl):
        word = m.group()
        s, e = m.start(), m.end()
        if any(cs <= s and e <= ce for cs, ce in covered):
            continue
        # Try trimming 1–6 chars; stop at the first LOCS key found
        for trim in range(1, min(7, len(word) - 3)):
            stem = word[:-trim]
            if len(stem) < 4:
                break
            if stem in LOCS:
                covered.append((s, e))
                results.append({
                    "name": text[s:e],
                    "lat": LOCS[stem][0],
                    "lon": LOCS[stem][1],
                })
                break

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Message Parser
# ─────────────────────────────────────────────────────────────────────────────

# Ordered by priority — first match wins for primary type
THREAT_RE: list[tuple[re.Pattern, str]] = [
    (re.compile(r"кинджал|kinzhal",         re.I), "kinzhal"),
    (re.compile(r"іскандер|iskander",        re.I), "iskander"),
    (re.compile(r"х-22|x-22",               re.I), "x22"),
    (re.compile(r"х-101|x-101|х101",        re.I), "x101"),
    (re.compile(r"х-59|x-59",               re.I), "x59"),
    (re.compile(r"х-69|x-69",               re.I), "x59"),
    (re.compile(r"онікс|oniks",              re.I), "oniks"),
    (re.compile(r"калібр|kalibr|caliber",   re.I), "kalibr"),
    (re.compile(r"шахед|shaheed|shahed",    re.I), "shahed"),
    (re.compile(r"герань|geran",             re.I), "geran"),
    (re.compile(r"балістич|ballistic",       re.I), "ballistic"),
    (re.compile(r"\bkar\b",                  re.I), "drone"),   # KAR kamikaze drone
    (re.compile(r"ракет|missile|rocket",     re.I), "missile"),
    (re.compile(r"бпла|дрон|uav\b|uavs\b|unmanned aerial", re.I), "drone"),
    (re.compile(
        r"літак|авіац|винищувач|штурмовик|бомбард|гелікоптер|"
        r"f-16|су-\d+|міг-\d+|helicopter|aircraft|aviation|tactical aviation",
        re.I), "aviation"),
]

STATUS_RE = {
    "destroyed": re.compile(
        r"збито|знищено|перехоплено|ліквідовано|збили|знищили|впало|впав|впала|збитий|"
        r"shot\s+down|downed|intercepted|destroyed|eliminated|neutralized",
        re.I,
    ),
    "moving": re.compile(
        r"рухається|летить|летять|прямує|рухаються|летів|летіла|прямують|"
        r"повз|курсом|у напрямку|в напрямку|на\/повз|зафіксовано|виявлено|"
        r"помічено|спостерігається|наближається|наближаються|пролетів|пролетіла|"
        r"heading|flying|spotted|detected|direction of|moving|approaching|"
        r"in the direction|from the",
        re.I,
    ),
    "launch": re.compile(
        r"запущено|пуск|виліт|вилетів|піднявся|launched|fired|took\s+off",
        re.I,
    ),
    "alert": re.compile(
        r"тривога|загроза|увага|небезпека|попередження|alert|threat|warning|danger",
        re.I,
    ),
}

FROM_RE = re.compile(
    r"(?:з боку|з напрямку|від|із|from\s+the?)\s+([\w\-'іїєА-ЯіїєҐґЄєІіЇї]{3,}(?:\s+[\w\-'іїєА-ЯіїєҐґЄєІіЇї]{3,})?)",
    re.I,
)
TO_RE = re.compile(
    r"(?:у напрямку|в напрямку|\bдо\b|towards?|direction\s+of)\s+([\w\-'іїєА-ЯіїєҐґЄєІіЇї]{3,}(?:\s+[\w\-'іїєА-ЯіїєҐґЄєІіЇї]{3,})?)",
    re.I,
)
COUNT_RE = re.compile(
    r"(\d+)\s*(?:шахед|бпла|бпл|ракет|дрон|калібр|кинджал|uav|uavs|drone|drones|missile|missiles|kar)",
    re.I,
)
GROUP_RE = re.compile(
    r"груп[аиі]|кількох|декількох|декілька|кілька|кільком|group|several|multiple",
    re.I,
)

CHANNEL_NAMES = {
    "kpszsu":    "КПСЗСУ",
    "war_monitor": "War Monitor",
    "mon1tor_ua":  "Monitor UA",
    "eradar_ua":   "eRadar UA",
}

# ── Cardinal direction parsing ────────────────────────────────────────────────
# Diagonal cardinals checked first (more specific than plain N/S/E/W).
# These are TRAVEL direction (where the drone is going).
_TRAVEL_DIR_RE: list[tuple[int, re.Pattern]] = [
    (45,  re.compile(r"північно.?схід|north.?east|ne\s+course|northeast(?:ern)?\s+(?:course|direction)", re.I)),
    (135, re.compile(r"південно.?схід|south.?east|se\s+course|southeast(?:ern)?\s+(?:course|direction)", re.I)),
    (225, re.compile(r"південно.?захід|south.?west|sw\s+course|southwest(?:ern)?\s+(?:course|direction)", re.I)),
    (315, re.compile(r"північно.?захід|north.?west|nw\s+course|northwest(?:ern)?\s+(?:course|direction)", re.I)),
    (0,   re.compile(r"курсом\s+на\s+північ|north(?:ern)?\s+course|heading\s+north|на\s+північ", re.I)),
    (90,  re.compile(r"курсом\s+на\s+схід|east(?:ern)?\s+course|heading\s+east|на\s+схід", re.I)),
    (180, re.compile(r"курсом\s+на\s+південь|south(?:ern)?\s+course|heading\s+south|на\s+південь", re.I)),
    (270, re.compile(r"курсом\s+на\s+захід|west(?:ern)?\s+course|heading\s+west|на\s+захід", re.I)),
]
# Origin direction — drone came FROM this direction, so travel = +180°
_ORIGIN_DIR_RE: list[tuple[int, re.Pattern]] = [
    (45,  re.compile(r"з\s+(?:боку\s+)?північного\s+сходу|from\s+the\s+north.?east", re.I)),
    (135, re.compile(r"з\s+(?:боку\s+)?південного\s+сходу|from\s+the\s+south.?east", re.I)),
    (225, re.compile(r"з\s+(?:боку\s+)?південного\s+заходу|from\s+the\s+south.?west", re.I)),
    (315, re.compile(r"з\s+(?:боку\s+)?північного\s+заходу|from\s+the\s+north.?west", re.I)),
    (90,  re.compile(r"зі?\s+сходу|з\s+(?:боку\s+)?сходу|from\s+the\s+east", re.I)),
    (270, re.compile(r"зі?\s+заходу|з\s+(?:боку\s+)?заходу|from\s+the\s+west", re.I)),
    (0,   re.compile(r"з\s+(?:боку\s+)?півночі|from\s+the\s+north", re.I)),
    (180, re.compile(r"з\s+(?:боку\s+)?півдня|from\s+the\s+south", re.I)),
]

# Regex that splits combined multi-threat messages into individual segments.
# Splits on ";" or on whitespace + action emoji (leading emoji not split).
_SEGMENT_SPLIT_RE = re.compile(
    r';\s*|\s(?:🚀|💥|⚡|✈️|🛩️|🔴|🟡|🟠|🔵|☠️|💣|🎯)\s*',
)


def split_segments(text: str) -> list[str]:
    """Split a combined report into individual threat segments."""
    parts = _SEGMENT_SPLIT_RE.split(text)
    return [p.strip() for p in parts if len(p.strip()) >= 12]


def parse_message(text: str, channel: str, msg_id: int = 0, msg_date=None) -> dict | None:
    if not text or len(text) < 15:
        return None

    # Detect primary threat type
    threat = "unknown"
    for pat, name in THREAT_RE:
        if pat.search(text):
            threat = name
            break

    locs = find_locations(text)
    if not locs:
        return None  # no location = nothing to plot

    # Status
    status = "unknown"
    for st, pat in STATUS_RE.items():
        if pat.search(text):
            status = st
            break

    # Count
    import random
    m = COUNT_RE.search(text)
    if m:
        count = int(m.group(1))
    elif GROUP_RE.search(text):
        count = random.randint(4, 10)
    else:
        count = 1

    # Directions (named from/to locations)
    frm = (FROM_RE.search(text) or type("", (), {"group": lambda s, i: None})()).group(1)
    to  = (TO_RE.search(text)   or type("", (), {"group": lambda s, i: None})()).group(1)

    # Cardinal travel direction — checked travel keywords first, then origin (reversed)
    direction_deg = None
    for deg, pat in _TRAVEL_DIR_RE:
        if pat.search(text):
            direction_deg = deg
            break
    if direction_deg is None:
        for deg, pat in _ORIGIN_DIR_RE:
            if pat.search(text):
                direction_deg = (deg + 180) % 360  # "from east" → going west
                break

    primary = locs[0] if locs else None

    return {
        "id":        str(uuid.uuid4()),
        "ts":        (msg_date.isoformat() if msg_date else datetime.now(timezone.utc).isoformat()),
        "channel":   CHANNEL_NAMES.get(channel, channel),
        "msg_id":    msg_id,
        "text":      text[:400],
        "type":      threat,
        "status":    status,
        "count":     count,
        "from":      frm,
        "to":        to,
        "direction": direction_deg,
        "lat":       primary["lat"] if primary else None,
        "lon":       primary["lon"] if primary else None,
        "location":  primary["name"] if primary else None,
        "waypoints": [{"lat": l["lat"], "lon": l["lon"], "name": l["name"]} for l in locs],
    }


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI + WebSocket hub
# ─────────────────────────────────────────────────────────────────────────────
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

_events: deque[dict] = deque(maxlen=500)
_clients: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None
_stats = {"total": 0, "channels": set()}


@asynccontextmanager
async def _lifespan(app):
    global _loop
    _loop = asyncio.get_running_loop()
    yield


web_app = FastAPI(lifespan=_lifespan)


def push_event(evt: dict) -> None:
    _events.appendleft(evt)
    _stats["total"] += 1
    _stats["channels"].add(evt.get("channel", ""))
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(_broadcast({"type": "event", "data": evt}), _loop)


async def _broadcast(msg: dict) -> None:
    text = json.dumps(msg)
    dead: set[WebSocket] = set()
    for ws in _clients.copy():
        try:
            await ws.send_text(text)
        except Exception:
            dead.add(ws)
    _clients -= dead


@web_app.get("/")
def _index():
    return FileResponse(WEB / "index.html")


@web_app.get("/api/events")
def _get_events():
    return {"events": _recent_events()}


@web_app.get("/api/stats")
def _get_stats():
    return {**_stats, "channels": list(_stats["channels"]), "clients": len(_clients)}


_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

# ── Tile proxy — serves map tiles through localhost so pywebview can load them
_tile_cache: dict[str, bytes] = {}

_TILE_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "image/png,image/*,*/*",
    "Referer": "https://www.openstreetmap.org/",
}

# Candidate tile URLs tried in order until one succeeds
def _tile_urls(z: int, x: int, y: int) -> list[str]:
    sub = "abc"[int(x + y) % 3]
    return [
        f"https://{sub}.basemaps.cartocdn.com/dark_matter_nolabels/{z}/{x}/{y}.png",
        f"https://cartodb-basemaps-{sub}.global.ssl.fastly.net/dark_matter_nolabels/{z}/{x}/{y}.png",
        f"https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    ]


def _fetch_tile_sync(z: int, x: int, y: int) -> bytes | None:
    import urllib.request
    cache_key = f"{z}/{x}/{y}"
    if cache_key in _tile_cache:
        return _tile_cache[cache_key]
    for url in _tile_urls(z, x, y):
        try:
            req = urllib.request.Request(url, headers=_TILE_HEADERS)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            if len(_tile_cache) < 4000:
                _tile_cache[cache_key] = data
            return data
        except Exception:
            continue
    return None


@web_app.get("/tiles/{z}/{x}/{y}.png")
async def _tile_dark(z: int, x: int, y: int):
    data = await asyncio.to_thread(_fetch_tile_sync, z, x, y)
    if data is None:
        return Response(status_code=503)
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "max-age=86400", "Access-Control-Allow-Origin": "*"})


def _recent_events(max_age_seconds: int = 1800) -> list[dict]:
    """Return events younger than max_age_seconds (default 30 min)."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    out = []
    for evt in _events:
        try:
            ts = datetime.fromisoformat(evt["ts"].replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                out.append(evt)
        except Exception:
            pass
    return out


@web_app.websocket("/ws")
async def _ws(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "history", "data": _recent_events()}))
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=25)
            except asyncio.TimeoutError:
                await ws.send_text('{"type":"ping"}')
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _clients.discard(ws)


if WEB.exists():
    web_app.mount("/static", StaticFiles(directory=str(WEB)), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# Telegram polling  (10-minute cycle)
# ─────────────────────────────────────────────────────────────────────────────
CHANNELS  = ["kpszsu", "war_monitor", "mon1tor_ua", "eradar_ua"]
POLL_SECS = 60  # 1 minute


async def _telegram_loop(cfg: dict) -> None:
    try:
        from telethon import TelegramClient
    except ImportError:
        log.error("telethon not installed — pip install telethon")
        return

    tg = cfg.get("telegram", {})
    client = TelegramClient(
        str(HERE / "session"),
        int(tg["api_id"]),
        tg["api_hash"],
    )

    phone = tg.get("phone", "")

    async def _code_cb() -> str:
        # Must use terminal input here — tkinter can't be called safely from threads
        print(f"\n  [Telegram] Check your phone ({phone}) for a verification code.")
        return input("  Code: ").strip()

    async def _pw_cb() -> str:
        import getpass
        return getpass.getpass("  [Telegram] 2FA password: ").strip()

    await client.start(phone=phone, code_callback=_code_cb, password=_pw_cb)
    log.info("Telegram authenticated")

    entities: dict[int, str] = {}
    for slug in cfg.get("channels", CHANNELS):
        try:
            ent = await client.get_entity(slug)
            entities[ent.id] = slug
            log.info("  channel ready: @%s", slug)
        except Exception as e:
            log.warning("  can't resolve @%s — %s", slug, e)

    last_ids: dict[str, int] = {s: 0 for s in entities.values()}

    while True:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=900)  # 15 min startup window

        for eid, slug in entities.items():
            try:
                msgs = await client.get_messages(eid, limit=50)
            except Exception as e:
                log.warning("fetch error %s: %s", slug, e)
                continue

            for msg in reversed(msgs or []):
                if not msg.date:
                    continue
                # Telethon may return naive or aware datetimes — normalise to UTC
                msg_date = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=timezone.utc)
                if msg_date < cutoff:
                    continue  # older than 30 minutes, skip
                if msg.id <= last_ids[slug]:
                    continue  # already processed
                last_ids[slug] = max(last_ids[slug], msg.id)

                # Split combined messages (e.g. "Сумщина: БПЛА; 🚀 Харківщина: ракета")
                # into individual segments and parse each one separately
                raw = msg.message or ""
                segments = split_segments(raw) or [raw]
                for i, seg in enumerate(segments):
                    evt = parse_message(seg, slug, msg.id, msg_date=msg_date)
                    if evt:
                        evt["id"] = f"{msg.id}_{i}"  # stable, unique per segment
                        log.info("[%s] %-10s  %s", slug, evt["type"], evt.get("location", "?"))
                        push_event(evt)

        nxt = (datetime.now(timezone.utc) + timedelta(seconds=POLL_SECS)).isoformat()
        if _loop and _loop.is_running():
            asyncio.run_coroutine_threadsafe(
                _broadcast({"type": "next_update", "at": nxt}), _loop
            )
        log.info("Next Telegram poll in %d minutes", POLL_SECS // 60)
        await asyncio.sleep(POLL_SECS)


def _run_telegram(cfg: dict) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_telegram_loop(cfg))
    except Exception as e:
        log.error("Telegram monitor crashed: %s", e)
    finally:
        loop.close()



# ─────────────────────────────────────────────────────────────────────────────
# GUI helpers — use tkinter dialogs so the user can paste freely
# ─────────────────────────────────────────────────────────────────────────────
def _ask(title: str, prompt: str, password: bool = False) -> str:
    """Show a tkinter input dialog; returns stripped text or raises SystemExit."""
    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        root.lift()
        root.attributes("-topmost", True)
        val = simpledialog.askstring(title, prompt, parent=root, show="*" if password else None)
        root.destroy()
        if val is None:
            raise SystemExit("Cancelled")
        return val.strip()
    except ImportError:
        # tkinter not available — fall back to terminal
        import getpass
        if password:
            return getpass.getpass(f"{prompt}: ").strip()
        return input(f"{prompt}: ").strip()


def _show_info(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(title, message, parent=root)
        root.destroy()
    except ImportError:
        print(f"\n  [{title}] {message}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Setup wizard
# ─────────────────────────────────────────────────────────────────────────────
def _run_setup() -> dict:
    print("\n" + "━" * 54)
    print("  Ukraine Drone Map — Telegram Setup")
    print("━" * 54)
    print("  Popup dialogs will appear — you can paste into them.\n")
    _show_info(
        "Telegram Setup",
        "Get free API credentials at:\nhttps://my.telegram.org/apps\n\n"
        "You will be asked for:\n  • API ID\n  • API Hash\n  • Phone number",
    )
    api_id   = _ask("Telegram Setup", "API ID (number from my.telegram.org/apps)")
    api_hash = _ask("Telegram Setup", "API Hash (long hex string)")
    phone    = _ask("Telegram Setup", "Phone number (e.g. +380XXXXXXXXX)")
    cfg = {
        "telegram": {"api_id": int(api_id), "api_hash": api_hash, "phone": phone},
        "channels": CHANNELS,
    }
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)
    print("\n  ✓ Saved to config.json — starting app now…\n")
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Download Leaflet + ant-path once so the desktop window works fully offline
# ─────────────────────────────────────────────────────────────────────────────
_LIB_ASSETS = {
    "leaflet.css": [
        "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css",
        "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
    ],
    "leaflet.js": [
        "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js",
        "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
    ],

}

def _ensure_web_libs() -> None:
    import urllib.request
    lib = WEB / "lib"
    lib.mkdir(exist_ok=True)
    for name, urls in _LIB_ASSETS.items():
        path = lib / name
        if path.exists():
            continue
        for url in urls:
            try:
                log.info("Downloading %s …", name)
                req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
                with urllib.request.urlopen(req, timeout=10) as r:
                    path.write_bytes(r.read())
                log.info("  ✓ %s", name)
                break
            except Exception as e:
                log.warning("  ✗ %s from %s: %s", name, url, e)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Ukraine Drone Map")
    ap.add_argument("--setup",   action="store_true", help="Configure Telegram")
    ap.add_argument("--browser", action="store_true", help="Open in browser only")
    ap.add_argument("--port",    type=int, default=8765)
    args = ap.parse_args()

    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║  🛡️  UKRAINE DRONE MAP                ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    # ── Config ────────────────────────────────────────────────────────────────
    if args.setup or not CONFIG.exists():
        cfg = _run_setup()
    else:
        with open(CONFIG) as f:
            cfg = json.load(f)

    # ── Download Leaflet libs BEFORE server starts so page always has them ───
    _ensure_web_libs()

    # ── Server ────────────────────────────────────────────────────────────────
    import uvicorn
    t = threading.Thread(
        target=lambda: uvicorn.run(
            web_app, host="127.0.0.1", port=args.port,
            log_level="warning", reload=False,
        ),
        daemon=True, name="server",
    )
    t.start()
    time.sleep(1.2)
    url = f"http://127.0.0.1:{args.port}"
    log.info("Server ready at %s", url)

    # ── Start Telegram in background ──────────────────────────────────────────
    threading.Thread(target=_run_telegram, args=(cfg,), daemon=True, name="telegram").start()

    # ── Open UI ────────────────────────────────────────────────────────────────
    if not args.browser:
        try:
            import webview
            log.info("Opening desktop window")
            webview.create_window(
                "Ukraine Drone Map", url=url,
                width=1440, height=900, resizable=True,
                background_color="#080c10",
            )
            webview.start(private_mode=False)
            return
        except Exception as e:
            if not isinstance(e, ImportError):
                log.warning("pywebview failed (%s) — falling back to browser", e)

    import webbrowser
    webbrowser.open(url)
    log.info("Opened in browser — press Ctrl+C to quit")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        msg = traceback.format_exc()
        # Write to a file so the error is readable even if the window closes
        try:
            (Path(__file__).parent / "error.log").write_text(msg)
        except Exception:
            pass
        print("\n" + "─" * 54)
        print("  APP CRASHED — error also saved to error.log")
        print("─" * 54)
        print(msg)
        print("─" * 54)
        input("\n  Press Enter to close…")
