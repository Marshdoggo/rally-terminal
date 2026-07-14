from datetime import date
from pathlib import Path

from alt_asset_explorer.connectors.sec_edgar import parse_filing_text, parse_series_table_rows


def test_sec_parser_extracts_series_and_exit():
    text = Path("tests/fixtures/sec_sample_1u.html").read_text(encoding="utf-8")
    series, exit_event = parse_filing_text(
        cik="0001688804",
        accession_number="0001688804-26-000001",
        filing_type="1-U",
        filing_date=date(2026, 2, 1),
        filing_url="https://www.sec.gov/example",
        text=text,
    )
    assert series.series_name == "Series #HermesBirkin35"
    assert series.offering_price == 10.00
    assert series.shares == 14000
    assert exit_event is not None
    assert exit_event.sale_price == 210000


def test_sec_table_parser_extracts_multiple_rally_series_rows():
    html = """
    <table>
      <tr>
        <td>#BIRKINTAN</td><td>4/30/2020</td><td>Offering Statement</td>
        <td>2015 Hermès 30cm Birkin Tangerine Ostrich with Palladium Hardware</td>
        <td>Closed</td><td>6/17/2020</td><td>6/25/2020</td><td>$28.00</td>
        <td>1000</td><td>$28,000</td><td>$1,520</td>
      </tr>
      <tr>
        <td>#FAUBOURG2</td><td>1/8/2021</td><td>Offering Statement</td>
        <td>2019 Hermès 20cm Sellier Faubourg Blue Multicolor Birkin with Palladium Hardware</td>
        <td>Sold - $180,000 Acquisition Offer Accepted on 12/14/2024</td>
        <td>12/28/2020</td><td>3/8/2021</td><td>$15.00</td>
        <td>11000</td><td>$165,000</td><td>$11,483</td>
      </tr>
    </table>
    """
    series, exits = parse_series_table_rows(
        cik="0001688804",
        accession_number="0001688804-25-000007",
        filing_type="1-SA",
        filing_date=date(2025, 9, 29),
        filing_url="https://www.sec.gov/example",
        text=html,
    )

    assert [row.series_name for row in series] == ["Series #BIRKINTAN", "Series #FAUBOURG2"]
    assert series[0].asset_name == "2015 Hermès 30cm Birkin Tangerine Ostrich with Palladium Hardware"
    assert series[0].offering_price == 28
    assert series[0].shares == 1000
    assert exits[0].series_name == "Series #FAUBOURG2"
    assert exits[0].sale_price == 180000
    assert exits[0].sale_date == date(2024, 12, 14)
