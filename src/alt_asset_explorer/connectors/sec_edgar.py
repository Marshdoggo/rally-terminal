from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from requests import RequestException
from dotenv import load_dotenv

from alt_asset_explorer.paths import DATA_RAW
from alt_asset_explorer.schemas import ExitEvent, SecFilingSeries

SEC_FORMS = {"1-A", "1-A/A", "1-K", "1-SA", "1-U", "253G2"}
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions"
TICKER_ALIASES = {"BIRKINBLEU": "BIRKINBLU"}


@dataclass(frozen=True)
class EdgarClient:
    user_agent: str
    cache_dir: Path = DATA_RAW / "sec"
    cache_only: bool = False

    @classmethod
    def from_env(cls, *, cache_only: bool = False) -> "EdgarClient":
        load_dotenv()
        user_agent = os.getenv("SEC_USER_AGENT") or os.getenv("EDGAR_USER_AGENT")
        if not user_agent:
            raise RuntimeError("Set SEC_USER_AGENT in .env before fetching SEC EDGAR data.")
        return cls(user_agent=user_agent, cache_only=cache_only)

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}

    def _get(self, url: str, cache_path: Path) -> bytes:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if cache_path.exists():
            return cache_path.read_bytes()
        if self.cache_only:
            raise FileNotFoundError(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(url, headers=self._headers(), timeout=30)
        response.raise_for_status()
        cache_path.write_bytes(response.content)
        return response.content

    def fetch_submissions(self, cik: str) -> dict:
        cik10 = cik.zfill(10)
        import json

        raw = self._get(f"{SEC_SUBMISSIONS}/CIK{cik10}.json", self.cache_dir / f"CIK{cik10}.json")
        return json.loads(raw.decode("utf-8"))

    def filing_text(self, cik: str, accession_number: str, primary_document: str) -> str:
        compact = accession_number.replace("-", "")
        url = f"{SEC_ARCHIVES}/{int(cik)}/{compact}/{primary_document}"
        path = self.cache_dir / str(int(cik)) / compact / primary_document
        raw = self._get(url, path)
        return raw.decode("utf-8", errors="replace")


def issuer_ciks(path: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(path or DATA_RAW / "sec_issuers_seed.csv", dtype={"cik": str})


def discover_filings(client: EdgarClient, cik: str) -> pd.DataFrame:
    submissions = client.fetch_submissions(cik)
    recent = submissions.get("filings", {}).get("recent", {})
    if not recent:
        return pd.DataFrame()
    df = pd.DataFrame(recent)
    if df.empty or "form" not in df.columns:
        return pd.DataFrame()
    return df[df["form"].isin(SEC_FORMS)].copy()


def _money(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = re.sub(r"[^0-9.]", "", match.group(1))
    return float(value) if value else None


def _parse_money(value: object) -> float | None:
    if pd.isna(value):
        return None
    parsed = re.sub(r"[^0-9.]", "", str(value))
    number = float(parsed) if parsed else None
    return number if number and number > 0 else None


def _parse_int(value: object) -> int | None:
    if pd.isna(value):
        return None
    parsed = re.sub(r"[^0-9]", "", str(value))
    number = int(parsed) if parsed else None
    return number if number and number > 0 else None


def _parse_date(value: object) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce")
    return parsed.date() if pd.notna(parsed) else None


def _first_money(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        value = _money(pattern, text)
        if value is not None:
            return value
    return None


def _shares(text: str) -> int | None:
    match = re.search(r"([0-9,]+)\s+(?:shares|interests|units)", text, re.IGNORECASE)
    if not match:
        match = re.search(r"(?:shares|interests|units)[^0-9]{0,40}([0-9,]+)", text, re.IGNORECASE)
    if not match:
        return None
    value = re.sub(r"[^0-9]", "", match.group(1))
    return int(value) if value else None


def _series_name(text: str) -> str | None:
    patterns = [
        r"(Series\s+#[A-Za-z0-9_-]+)",
        r"(Series\s+[A-Za-z0-9_-]+)",
        r"(?:series name|series title)[^A-Za-z0-9#]{0,40}([A-Za-z0-9 #_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return None


def _sale_date(text: str) -> date | None:
    match = re.search(r"(?:accepted|closed|completed)\s+on\s+([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", text, re.IGNORECASE)
    if not match:
        return None
    return _parse_date(match.group(1))


def parse_filing_text(
    *,
    cik: str,
    accession_number: str,
    filing_type: str,
    filing_date: date,
    filing_url: str,
    text: str,
) -> tuple[SecFilingSeries, ExitEvent | None]:
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    series_name = _series_name(clean)
    offering_price = _first_money(
        [
            r"offering price[^$]{0,80}(\$[0-9,.]+)",
            r"price per share[^$]{0,80}(\$[0-9,.]+)",
            r"public offering price[^$]{0,80}(\$[0-9,.]+)",
        ],
        clean,
    )
    acquisition_cost = _first_money(
        [
            r"acquisition cost[^$]{0,80}(\$[0-9,.]+)",
            r"purchase price[^$]{0,80}(\$[0-9,.]+)",
        ],
        clean,
    )
    offering_expenses = _first_money(
        [
            r"offering expenses[^$]{0,80}(\$[0-9,.]+)",
            r"expenses of the offering[^$]{0,80}(\$[0-9,.]+)",
        ],
        clean,
    )
    sale_price = _first_money(
        [
            r"sale price[^$]{0,80}(\$[0-9,.]+)",
            r"sold[^$]{0,120}(\$[0-9,.]+)",
            r"sold[^$]{0,120}(?:for|at)[^$]{0,40}(\$[0-9,.]+)",
        ],
        clean,
    )
    status = "exit" if sale_price else None
    series_id = f"{cik}-{accession_number}-{series_name or 'unknown'}"
    series = SecFilingSeries(
        series_id=series_id,
        cik=cik,
        accession_number=accession_number,
        filing_type=filing_type,
        filing_date=filing_date,
        filing_url=filing_url,
        series_name=series_name,
        asset_name=series_name,
        offering_price=offering_price,
        shares=_shares(clean),
        acquisition_cost=acquisition_cost,
        offering_expenses=offering_expenses,
        status=status,
        source_confidence=0.80,
    )
    exit_event = None
    if sale_price:
        exit_event = ExitEvent(
            exit_id=f"exit-{cik}-{accession_number}",
            series_name=series_name,
            sale_price=sale_price,
            sale_date=_sale_date(clean) or filing_date,
            realized_return=None,
            source_url=filing_url,
            source_confidence=0.80,
        )
    return series, exit_event


def parse_series_table_rows(
    *,
    cik: str,
    accession_number: str,
    filing_type: str,
    filing_date: date,
    filing_url: str,
    text: str,
) -> tuple[list[SecFilingSeries], list[ExitEvent]]:
    """Extract per-asset rows from RSE Collection offering tables.

    RSE periodic filings often include offering-summary tables where each row
    begins with a Rally ticker like ``#SOBLACK``. The older parser only captured
    the first Series mention in the whole filing, so these rows were invisible.
    """
    try:
        tables = pd.read_html(StringIO(text))
    except ValueError:
        return [], []

    series_rows: list[SecFilingSeries] = []
    exit_rows: list[ExitEvent] = []
    seen: set[str] = set()

    for table in tables:
        if table.shape[1] < 10:
            continue
        for _, row in table.iterrows():
            first_cell = str(row.iloc[0]) if len(row) else ""
            ticker_match = re.search(r"#([A-Za-z0-9]+)\b", first_cell)
            if not ticker_match:
                continue
            ticker = TICKER_ALIASES.get(ticker_match.group(1).upper(), ticker_match.group(1).upper())
            if ticker in seen:
                continue
            seen.add(ticker)

            asset_name = str(row.iloc[3]).strip() if len(row) > 3 and pd.notna(row.iloc[3]) else f"Series #{ticker}"
            status_text = str(row.iloc[4]).strip() if len(row) > 4 and pd.notna(row.iloc[4]) else ""
            offering_price = _parse_money(row.iloc[7]) if len(row) > 7 else None
            shares = _parse_int(row.iloc[8]) if len(row) > 8 else None
            offering_expenses = _parse_money(row.iloc[10]) if len(row) > 10 else None
            normalized_status = "exit" if re.search(r"\b(sold|liquidated)\b", status_text, re.I) else ("closed" if status_text else None)
            series_name = f"Series #{ticker}"
            series_rows.append(
                SecFilingSeries(
                    series_id=f"{cik}-{accession_number}-{series_name}",
                    cik=cik,
                    accession_number=accession_number,
                    filing_type=filing_type,
                    filing_date=filing_date,
                    filing_url=filing_url,
                    series_name=series_name,
                    asset_name=asset_name,
                    offering_price=offering_price,
                    shares=shares,
                    acquisition_cost=None,
                    offering_expenses=offering_expenses,
                    status=normalized_status,
                    source_confidence=0.88,
                )
            )

            sale_price = _first_money([r"sold[^$]{0,120}(\$[0-9,.]+)", r"liquidated[^$]{0,120}(\$[0-9,.]+)"], status_text)
            if sale_price:
                sale_dt = _sale_date(status_text) or filing_date
                exit_rows.append(
                    ExitEvent(
                        exit_id=f"exit-{cik}-{accession_number}-{ticker}",
                        series_name=series_name,
                        sale_price=sale_price,
                        sale_date=sale_dt,
                        realized_return=None,
                        source_url=filing_url,
                        source_confidence=0.88,
                    )
                )

    return series_rows, exit_rows


def build_sec_outputs(client: EdgarClient | None = None, *, max_filings: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    client = client or EdgarClient.from_env()
    series_rows: list[dict] = []
    exit_rows: list[dict] = []
    for _, issuer in issuer_ciks().iterrows():
        cik = str(issuer["cik"])
        try:
            filings = discover_filings(client, cik)
        except FileNotFoundError:
            continue
        if max_filings is not None:
            filings = filings.head(max_filings)
        for _, filing in filings.iterrows():
            accession = filing["accessionNumber"]
            primary = filing["primaryDocument"]
            compact = accession.replace("-", "")
            url = f"{SEC_ARCHIVES}/{int(cik)}/{compact}/{primary}"
            try:
                text = client.filing_text(cik, accession, primary)
            except (FileNotFoundError, RequestException):
                continue
            series, exit_event = parse_filing_text(
                cik=cik,
                accession_number=accession,
                filing_type=filing["form"],
                filing_date=pd.to_datetime(filing["filingDate"]).date(),
                filing_url=url,
                text=text,
            )
            series_rows.append(series.model_dump())
            if exit_event:
                exit_rows.append(exit_event.model_dump())
            table_series, table_exits = parse_series_table_rows(
                cik=cik,
                accession_number=accession,
                filing_type=filing["form"],
                filing_date=pd.to_datetime(filing["filingDate"]).date(),
                filing_url=url,
                text=text,
            )
            series_rows.extend(row.model_dump() for row in table_series)
            exit_rows.extend(row.model_dump() for row in table_exits)
    series = pd.DataFrame(series_rows)
    exits = pd.DataFrame(exit_rows)
    if not series.empty:
        series = series.drop_duplicates(subset=["series_id"], keep="last")
    if not exits.empty:
        exits = exits.drop_duplicates(subset=["exit_id"], keep="last")
    return series, exits
