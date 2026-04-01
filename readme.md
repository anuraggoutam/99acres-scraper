# 99acres Property Scraper

Production-ready scraper for 99acres.com residential property listings. Built for **bulk scraping up to 500 pages** with crash recovery, incremental saves, and anti-ban protection. Extracts **77 data fields** per listing.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Quick Start

```bash
python main.py --pages 5 --output data/noida_buy.csv
```

A Chromium browser window will open. If 99acres shows a CAPTCHA on the first run, solve it manually -- the script waits and continues automatically. Your CAPTCHA session is saved so you won't need to solve it again on the next run.

## Bulk Scraping (100-500 pages)

```bash
# Scrape 500 pages -- data is saved after EVERY page
python main.py --pages 500 --output data/noida_all.csv

# If it gets interrupted (Ctrl+C, crash, block), resume exactly where you left off
python main.py --pages 500 --output data/noida_all.csv --resume

# With proxy for extra safety on large runs
python main.py --pages 500 --proxy http://user:pass@host:port --output data/noida_all.csv
```

### What happens during a 500-page run

- **Every page**: data is saved to CSV/JSON + checkpoint. Nothing is ever lost.
- **Every 25 pages**: automatic 1-2 minute cooldown break (mimics human taking a break)
- **CAPTCHA appears**: script pauses, you solve it in the browser, it continues
- **Access denied**: auto-retry with backoff, up to 3 times before stopping to protect your IP
- **Ctrl+C**: data saved instantly. Run `--resume` to continue.
- **Crash/power loss**: checkpoint has all data. Run `--resume` to continue.
- **Progress display**: shows ETA, listings/page rate, and total count in real-time

### Resume after any interruption

```bash
# Start a big run
python main.py --pages 300

# ... interrupted at page 87 (no matter how -- Ctrl+C, crash, ban, power loss)
# CSV/JSON already has all data from pages 1-87

# Resume from page 88
python main.py --pages 300 --resume
```

## Filtering by BHK

```bash
# Only 2 BHK
python main.py --pages 10 --url "https://www.99acres.com/property-in-noida-ffid?city=7&preference=S&area_unit=1&res_com=R&bedroom_num=2"

# Only 3 BHK
python main.py --pages 10 --url "https://www.99acres.com/property-in-noida-ffid?city=7&preference=S&area_unit=1&res_com=R&bedroom_num=3"

# 2 BHK + 3 BHK combined
python main.py --pages 10 --url "https://www.99acres.com/property-in-noida-ffid?city=7&preference=S&area_unit=1&res_com=R&bedroom_num=2,3"
```

## Filtering by Budget

```bash
# Under 1 Crore
python main.py --pages 10 --url "https://www.99acres.com/property-in-noida-ffid?city=7&preference=S&area_unit=1&res_com=R&budget_max=10000000"

# 50 Lac to 2 Crore
python main.py --pages 10 --url "https://www.99acres.com/property-in-noida-ffid?city=7&preference=S&area_unit=1&res_com=R&budget_min=5000000&budget_max=20000000"
```

## Combined Filters

```bash
# 2-3 BHK flats under 2 Crore in Noida
python main.py --pages 100 \
  --url "https://www.99acres.com/property-in-noida-ffid?city=7&preference=S&area_unit=1&res_com=R&bedroom_num=2,3&budget_max=20000000" \
  --output data/noida_2_3bhk_under2cr.csv
```

## Different Cities

```bash
# Gurugram
python main.py --pages 100 --url "https://www.99acres.com/property-in-gurgaon-ffid?city=74&preference=S&area_unit=1&res_com=R"

# Delhi
python main.py --pages 100 --url "https://www.99acres.com/property-in-new-delhi-ffid?city=1&preference=S&area_unit=1&res_com=R"

# Mumbai
python main.py --pages 100 --url "https://www.99acres.com/property-in-mumbai-ffid?city=12&preference=S&area_unit=1&res_com=R"

# Bangalore
python main.py --pages 100 --url "https://www.99acres.com/property-in-bengaluru-ffid?city=21&preference=S&area_unit=1&res_com=R"
```

**Tip:** Apply filters on [99acres.com](https://www.99acres.com) in your browser, then copy the URL and pass it with `--url`.

## URL Parameters Reference

| Filter | Parameter | Example Values |
|--------|-----------|----------------|
| City | `city` | `7` Noida, `74` Gurugram, `1` Delhi, `12` Mumbai, `21` Bangalore |
| BHK | `bedroom_num` | `1`, `2`, `3`, `4`, `5` (comma-separate for multiple) |
| Budget min | `budget_min` | Amount in rupees (e.g. `5000000` = 50 Lac) |
| Budget max | `budget_max` | Amount in rupees (e.g. `20000000` = 2 Cr) |
| Property type | `property_type` | `1` Flat, `3` Plot, `17` Villa |
| Buy / Rent | `preference` | `S` Buy, `R` Rent |
| Residential / Commercial | `res_com` | `R` Residential, `C` Commercial |
| Ready to move | `availability` | `I` Immediate |

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--pages` | `3` | Pages to scrape (max 500) |
| `--output` | `data/noida_buy.csv` | Output CSV (JSON auto-generated alongside) |
| `--url` | Noida residential | Override with any 99acres search URL |
| `--proxy` | None | Residential proxy URL |
| `--resume` | off | Resume from last checkpoint after crash or Ctrl+C |

## Output Fields (77 columns)

| Category | Fields |
|----------|--------|
| **Identifiers** | listing_link, listing_id, building_id |
| **Basic Info** | title, property_type, deal_type, posted_date, modified_date, status, is_verified |
| **Availability** | availability_label, availability_date |
| **Rooms** | bedrooms, bathrooms, balcony, living_room, kitchen, additional_rooms_qty, additional_rooms |
| **Area** | super_built_up_area_sq_ft, built_up_area_sq_ft, carpet_area, configuration_short, configuration_long, is_corner_property |
| **Pricing** | price_label, price_num, price_text, price_per_sq_ft, rent_price_sq_ft, all_inclusive_price, is_price_negotiable, tax_govt_charges, early_leaving_charges |
| **Location** | city, society, address, address_desc, floor_number, total_floor, floor_label, lat, lon |
| **Characteristics** | facing, overlooking, property_age, key_highlights, transaction_type, width_of_facing_road, wheelchair_friendly, property_ownership, gated_community, pet_friendly, flooring, corner_property, water_source |
| **Amenities** | furnishing, parking, power_backup, about, furnishing_details, features |
| **Agent** | agent_name, agency_name, agency_address, agency_url, agency_type, agency_profile, agency_photo_url, agency_hidden_phone, agency_hidden_mobile, member_since, brokerage_type |
| **Activity** | people_activities, ad_keywords |
| **RERA** | rera_reg_status, rera_reg_num |

## Data Safety & Crash Recovery

### How data is protected

| Layer | What it protects | When |
|-------|------------------|------|
| **Checkpoint file** | Raw scraped data + page progress | After every page |
| **CSV/JSON output** | Parsed & structured data | After every page |
| **Cookie session** | CAPTCHA solution | Across restarts |
| **Atomic writes** | File integrity (write to .tmp, then rename) | Every save |

### Resume workflow

```
Fresh run                    Interrupted              Resume
---------                    -----------              ------
python main.py --pages 500   Ctrl+C at page 87        python main.py --pages 500 --resume
                             ↓                        ↓
                             CSV has 870 listings      Loads 870 listings from CSV
                             Checkpoint at page 87     Loads checkpoint, starts page 88
                             Cookies saved             Loads cookies (no CAPTCHA)
```

### Files saved by the scraper

| File | Purpose | Safe to delete? |
|------|---------|-----------------|
| `data/noida_buy.csv` | Final output (CSV) | Yes (will be recreated) |
| `data/noida_buy.json` | Final output (JSON) | Yes (will be recreated) |
| `data/_checkpoint.json` | Resume state | Yes (forces fresh start) |
| `data/_cookies.json` | CAPTCHA session | Yes (may need to re-solve CAPTCHA) |
| `logs/scraper.log` | Activity log | Yes |
| `logs/browser_page_N.png` | Debug screenshot for empty pages | Yes |

## Anti-Ban Measures (Built-in)

The scraper is designed for bulk runs of hundreds of pages:

- **Real browser** -- Chromium in headful mode, invisible to Akamai WAF
- **playwright-stealth** -- patches all browser fingerprinting APIs
- **Human-like behavior** -- random mouse movements, natural scrolling, variable timing
- **Progressive backoff** -- delay between pages increases gradually (5-9s base + ~1s per page)
- **Batch breaks** -- every 25 pages, takes a 1-2 minute cooldown break
- **Cookie persistence** -- solve CAPTCHA once, reuse across multiple runs
- **Block retry with backoff** -- if blocked, waits and retries (max 3 times before stopping)
- **Smart stopping** -- stops after 5 consecutive empty pages instead of hammering the server

### Safe Usage Guidelines

| Pages per run | Risk level | Notes |
|---------------|------------|-------|
| 1-25 | Safe | Normal browsing behavior |
| 25-100 | Low risk | Built-in batch breaks handle this |
| 100-250 | Moderate | Consider `--proxy` for extra safety |
| 250-500 | Use proxy | Residential proxy strongly recommended |

### If you get blocked

1. **CAPTCHA shows up** -- solve it in the browser window, the script waits automatically
2. **403 Access Denied** -- script auto-retries with backoff. If persistent, wait 15-30 min
3. **Frequent blocking** -- use a residential proxy: `--proxy http://user:pass@host:port`
4. **IP ban (rare)** -- switch to a different proxy or wait 24h. Not permanent.

## How It Works

1. Opens 99acres search page in real Chromium with stealth patches
2. Reads listing data from `window.__initialData__` (embedded page data)
3. Intercepts XHR API responses for additional/prefetched listings
4. Falls back to DOM element parsing as last resort
5. Parses raw data into 77 structured fields
6. Saves checkpoint + CSV/JSON to disk after every page (crash-safe)
7. Deduplicates across all pages using property IDs

## Project Structure

```
99acres-scraper/
├── main.py                  # CLI entry point + incremental saver
├── requirements.txt
├── .env                     # Optional proxy config
├── scraper/
│   ├── __init__.py
│   ├── config.py            # Search URL and defaults
│   ├── browser_scraper.py   # Playwright browser automation + checkpoint
│   ├── parser.py            # Raw API -> structured Property (77 fields)
│   ├── models.py            # Pydantic data model
│   └── utils.py             # Price/date/code normalization
├── data/                    # Output CSV + JSON + checkpoint + cookies
└── logs/                    # scraper.log + debug screenshots
```
