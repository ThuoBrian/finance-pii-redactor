"""Build the synthetic corpus: a master list, documents, and gold labels.

Gold labels come from construction: every value inserted into a document is
recorded with its scenario category, so nothing is labelled by hand. Within
one document no two gold values share a surname or organization word, so a
value found in the output can only be that value leaking.

Everything is returned as bytes; nothing is written into the repository.
"""

from __future__ import annotations

import random
import re
from dataclasses import asdict, dataclass
from io import BytesIO

import fitz
from docx import Document
from openpyxl import Workbook

from eval import names, scenarios

FILE_TYPES = ("xlsx", "docx", "pdf", "pdf_scanned")

_STAFF, _VENDORS, _FUNDERS = 60, 40, 15
_UNLISTED_PEOPLE, _UNLISTED_ORGS = 80, 40
_FIRST_ID = 10001


@dataclass(frozen=True)
class Gold:
    """One value placed in one document."""

    doc: str
    file_type: str
    category: str
    value: str

    @property
    def negative(self) -> bool:
        """Whether this value must survive redaction (a false-positive probe)."""
        return self.category in scenarios.NEGATIVE

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-ready dict."""
        return asdict(self)


@dataclass(frozen=True)
class Doc:
    """One generated document."""

    name: str
    file_type: str
    data: bytes


@dataclass(frozen=True)
class Corpus:
    """The master-list workbook, the documents, and every gold value."""

    master_list: bytes
    docs: list[Doc]
    gold: list[Gold]


@dataclass(frozen=True)
class _Item:
    category: str
    value: str
    text: str  # what goes into the document: a sentence, or the bare value


@dataclass(frozen=True)
class _Pools:
    staff: list[names.Person]
    vendors: list[str]
    funders: list[str]
    people: list[names.Person]  # not in the master list
    orgs: list[str]  # not in the master list


def build(seed: int, size: int, *, ocr: bool = False) -> Corpus:
    """Build ``size`` documents spread across the file types.

    Without ``ocr`` no scanned PDFs are made, since nothing could read them.
    """
    rng = random.Random(seed)
    pools = _pools(rng)
    types = [t for t in FILE_TYPES if ocr or t != "pdf_scanned"]
    docs: list[Doc] = []
    gold: list[Gold] = []
    for index in range(size):
        file_type = types[index % len(types)]
        name = f"doc{index:03d}.{file_type.removesuffix('_scanned')}"
        items = _items(rng, pools, file_type)
        docs.append(Doc(name, file_type, _render(file_type, items, rng)))
        gold += [Gold(name, file_type, item.category, item.value) for item in items]
    return Corpus(_master_list(pools), docs, gold)


def _pools(rng: random.Random) -> _Pools:
    seen_surnames: set[str] = set()
    seen_orgs: set[str] = set()

    def people(count: int) -> list[names.Person]:
        out: list[names.Person] = []
        while len(out) < count:
            candidate = names.person(rng)
            if candidate.surname not in seen_surnames:
                seen_surnames.add(candidate.surname)
                out.append(candidate)
        return out

    def orgs(count: int, make) -> list[str]:  # noqa: ANN001 - a names.* factory
        out: list[str] = []
        while len(out) < count:
            candidate = make(rng)
            if candidate not in seen_orgs:
                seen_orgs.add(candidate)
                out.append(candidate)
        return out

    return _Pools(
        staff=people(_STAFF),
        vendors=orgs(_VENDORS, names.vendor),
        funders=orgs(_FUNDERS, names.funder),
        people=people(_UNLISTED_PEOPLE),
        orgs=orgs(_UNLISTED_ORGS, names.vendor),
    )


def _master_list(pools: _Pools) -> bytes:
    """Return the workbook in the format data/README.md describes."""
    workbook = Workbook()
    del workbook["Sheet"]  # the default empty tab
    next_id = _FIRST_ID
    for sheet, category, values in (
        ("Staff", "Staff", [p.full for p in pools.staff]),
        ("Vendors", "Vendor", pools.vendors),
        ("Funders", "Funder", pools.funders),
    ):
        ws = workbook.create_sheet(sheet)
        ws.append(["Category", "Internal ID", "Name", "Primary Subsidiary", "Country"])
        for value in values:
            ws.append([category, str(next_id), value, "Synthetic", "Testland"])
            next_id += 1
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class _Picker:
    """Draws values for one document so no two share a distinctive word."""

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._used: set[str] = set()

    def take[T](self, pool: list[T], key) -> T:  # noqa: ANN001 - str-returning key
        for candidate in self._rng.sample(pool, len(pool)):
            word = key(candidate).casefold()
            if word not in self._used:
                self._used.add(word)
                return candidate
        raise RuntimeError("name pool exhausted; enlarge it in eval/corpus.py")

    def person(self, pool: list[names.Person]) -> names.Person:
        return self.take(pool, lambda p: p.surname)

    def org(self, pool: list[str]) -> str:
        return self.take(pool, lambda o: o.split()[0])


def _items(rng: random.Random, pools: _Pools, file_type: str) -> list[_Item]:
    pick = _Picker(rng)
    master_orgs = pools.vendors + pools.funders
    aliasable = [v for v in pools.vendors if names.alias_of(v)]

    def sentence(category: str, value: str, template: str | None = None) -> _Item:
        template = template or rng.choice(scenarios.TEMPLATES[category])
        return _Item(category, value, template.format(x=value))

    items: list[_Item] = []
    staff = pick.person(pools.staff)
    items.append(sentence("master_person", staff.full))
    items.append(sentence("master_org", pick.org(master_orgs)))
    items.append(sentence("alias_org", str(names.alias_of(pick.org(aliasable)))))
    items.append(sentence("unlisted_person", pick.person(pools.people).full))
    items.append(sentence("unlisted_org", pick.org(pools.orgs)))
    upper = pick.person(pools.staff).full
    items.append(
        sentence("case_variant", upper.upper() if rng.random() < 0.5 else upper.lower())
    )
    initial = pick.person(pools.staff)
    items.append(sentence("initials", f"{initial.given[0]}. {initial.surname}"))
    items.append(_Item("in_table", value := pick.person(pools.people).full, value))
    items.append(_Item("in_table", value := pick.org(master_orgs), value))
    items.append(_bank_item(rng))
    items.append(_email_url_item(rng, pick, pools))

    if file_type == "xlsx":
        items.append(
            _Item("excel_header", value := pick.person(pools.people).full, value)
        )
        items.append(_Item("excel_tab", value := pick.org(pools.vendors), value))
    if file_type.startswith("pdf"):
        items.append(sentence("pdf_linebreak", pick.person(pools.people).full))

    items.append(sentence("surname_only", pick.person(pools.staff).surname))
    reordered = pick.person(pools.staff)
    items.append(sentence("reordered_name", f"{reordered.surname}, {reordered.given}"))

    for term in rng.sample(scenarios.LEGAL_TERMS, 2):
        items.append(sentence("legal_terms", term))
    for term in rng.sample(scenarios.PLACES_MONTHS_FINANCE, 2):
        items.append(sentence("places_months_finance", term))
    return items


def _bank_item(rng: random.Random) -> _Item:
    account, till, swift = scenarios.TEMPLATES["bank_payment"]
    letters = "ABCDEFGHJKLMNPRSTUVWXYZ"
    template, value = rng.choice(
        [
            (account, " ".join(f"{rng.randrange(10**4):04d}" for _ in range(3))),
            (till, f"{rng.randrange(10**5, 10**6)}"),
            (
                swift,
                "".join(rng.choices(letters, k=4))
                + "KE"
                + "".join(rng.choices(letters, k=2)),
            ),
        ]
    )
    return _Item("bank_payment", value, template.format(x=value))


def _email_url_item(rng: random.Random, pick: _Picker, pools: _Pools) -> _Item:
    email, url = scenarios.TEMPLATES["email_url"]
    if rng.random() < 0.5:
        p = pick.person(pools.people)
        value = f"{p.given}.{p.surname}@example.org".lower()
        return _Item("email_url", value, email.format(x=value))
    slug = re.sub(r"\W+", "", pick.org(pools.orgs).split()[0]).lower()
    value = f"https://www.{slug}.example.org/prices"
    return _Item("email_url", value, url.format(x=value))


def _render(file_type: str, items: list[_Item], rng: random.Random) -> bytes:
    rng.shuffle(items)
    if file_type == "xlsx":
        return _xlsx(items, rng)
    if file_type == "docx":
        return _docx(items, rng)
    return _pdf(items, rng, scanned=file_type == "pdf_scanned")


def _amount(rng: random.Random) -> int:
    return rng.randrange(50, 9000)


def _xlsx(items: list[_Item], rng: random.Random) -> bytes:
    workbook = Workbook()
    del workbook["Sheet"]  # the default empty tab
    ws = workbook.create_sheet("Payments")
    ws.append(["Date", "Payee", "Description", "Amount"])
    header = next((i.value for i in items if i.category == "excel_header"), "Budget")
    tab = next((i.value for i in items if i.category == "excel_tab"), "Summary")
    for day, item in enumerate(items, start=1):
        if item.category in ("excel_header", "excel_tab"):
            continue
        date = f"2026-03-{day:02d}"
        if item.category == "in_table":
            ws.append([date, item.text, "Monthly retainer", _amount(rng)])
        else:
            ws.append([date, None, item.text, _amount(rng)])
    summary = workbook.create_sheet(tab)
    summary.append(["Line", header])
    summary.append([1, _amount(rng)])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _docx(items: list[_Item], rng: random.Random) -> bytes:
    document = Document()
    document.add_heading("Expense notes", level=1)
    table_rows = []
    for item in items:
        if item.category == "in_table":
            table_rows.append(item.text)
        else:
            document.add_paragraph(item.text)
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Payee", "Amount"
    for payee in table_rows:
        cells = table.add_row().cells
        cells[0].text, cells[1].text = payee, f"{_amount(rng):,}"
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


_LEFT, _TOP, _LINE, _FONT = 72, 72, 16, 10
_SCAN_DPI = 200


def _pdf(items: list[_Item], rng: random.Random, *, scanned: bool) -> bytes:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    y = _TOP
    table_rows = []
    for item in items:
        if item.category == "in_table":
            table_rows.append(item.text)
            continue
        lines = _split_name(item) if item.category == "pdf_linebreak" else [item.text]
        for line in lines:
            page.insert_text((_LEFT, y), line, fontsize=_FONT)
            y += _LINE
    y += _LINE
    page.insert_text((_LEFT, y), "Payee", fontsize=_FONT)
    page.insert_text((360, y), "Amount", fontsize=_FONT)
    for payee in table_rows:
        y += _LINE
        page.insert_text((_LEFT, y), payee, fontsize=_FONT)
        page.insert_text((360, y), f"{_amount(rng):,}", fontsize=_FONT)
    if scanned:
        document = _as_scan(document)
    data = document.tobytes()
    document.close()
    return data


def _split_name(item: _Item) -> list[str]:
    """Break the line inside the surname with a hyphen, as typeset text does."""
    start = item.text.index(item.value)
    cut = start + item.value.index(" ") + 4  # three letters into the surname
    return [item.text[:cut] + "-", item.text[cut:]]


def _as_scan(document: fitz.Document) -> fitz.Document:
    """Return an image-only copy, as a scanner would produce."""
    scan = fitz.open()
    for page in document:
        image = page.get_pixmap(dpi=_SCAN_DPI)
        new = scan.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, pixmap=image)
    document.close()
    return scan
