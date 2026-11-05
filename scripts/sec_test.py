"""Level 0 check: fetch Apple's filing history from SEC EDGAR and list its 10-Ks."""
import requests

from backend.config import SEC_USER_AGENT, require

CIK = "0000320193"  # Apple. CIKs are always 10 digits with leading zeros here.
URL = f"https://data.sec.gov/submissions/CIK{CIK}.json"

headers = {"User-Agent": require("SEC_USER_AGENT", SEC_USER_AGENT)}

response = requests.get(URL, headers=headers, timeout=30)
print("Status code:", response.status_code)
response.raise_for_status()  # turns 4xx/5xx status codes into a Python error

data = response.json()  # JSON text -> Python dict
print("Company:", data["name"])
print("Tickers:", data["tickers"])
print("Fiscal year end (MMDD):", data["fiscalYearEnd"])

# 'recent' holds PARALLEL lists: position i in every list describes the same filing.
recent = data["filings"]["recent"]
print("\nfiling date | period end | accession number | document URL")
for i, form in enumerate(recent["form"]):
    if form == "10-K":
        accession = recent["accessionNumber"][i]
        document = recent["primaryDocument"][i]
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}/"
            f"{accession.replace('-', '')}/{document}"
        )
        print(recent["filingDate"][i], recent["reportDate"][i], accession, url)
