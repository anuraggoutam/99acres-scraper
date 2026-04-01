# 99acres Property Scraper

Production-ready scraper for 99acres.com residential property listings. Extracts **77 data fields** per listing including price, location, agent info, RERA status, and more.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Quick Start

```bash
python main.py --pages 5 --output data/noida_buy.csv
```

A Chromium browser window will open. If 99acres shows a CAPTCHA on the first run, solve it manually in the browser -- the script waits and then continues automatically.

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
python main.py --pages 15 \
  --url "https://www.99acres.com/property-in-noida-ffid?city=7&preference=S&area_unit=1&res_com=R&bedroom_num=2,3&budget_max=20000000" \
  --output data/noida_2_3bhk_under2cr.csv
```

## Different Cities

```bash
# Gurugram
python main.py --pages 10 --url "https://www.99acres.com/property-in-gurgaon-ffid?city=74&preference=S&area_unit=1&res_com=R"

# Delhi
python main.py --pages 10 --url "https://www.99acres.com/property-in-new-delhi-ffid?city=1&preference=S&area_unit=1&res_com=R"

# Mumbai
python main.py --pages 10 --url "https://www.99acres.com/property-in-mumbai-ffid?city=12&preference=S&area_unit=1&res_com=R"

# Bangalore
python main.py --pages 10 --url "https://www.99acres.com/property-in-bengaluru-ffid?city=21&preference=S&area_unit=1&res_com=R"
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
| `--pages` | `3` | Pages to scrape (hard limit: 50) |
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

## Anti-Ban Measures (Built-in)

The scraper is designed to mimic real human browsing:

- **Real browser** -- runs Chromium in headful mode (not headless), so 99acres' Akamai WAF sees normal traffic
- **playwright-stealth** -- patches all browser fingerprinting APIs (webdriver, plugins, WebGL, etc.)
- **Human-like behavior** -- random mouse movements, natural scrolling patterns, variable timing
- **Exponential backoff** -- delay between pages increases gradually (4-7s base + ~2s per page)
- **Smart stopping** -- automatically stops after 2 consecutive empty pages instead of hammering the server
- **Graceful recovery** -- detects CAPTCHA / access-denied and waits for manual resolution

### Safe Usage Guidelines

| Pages per run | Risk level | Notes |
|---------------|------------|-------|
| 1-10 | Safe | Normal browsing behavior |
| 10-20 | Low risk | Add a few minutes between runs |
| 20-50 | Moderate | Use `--proxy` with a residential proxy |
| 50+ | Not recommended | Hard limit at 50 pages |

### If you get blocked

1. **CAPTCHA shows up** -- solve it in the browser window, the script waits automatically
2. **403 Access Denied** -- wait 15-30 minutes, your IP resets. Not a permanent ban
3. **Frequent blocking** -- use a residential proxy: `--proxy http://user:pass@host:port`

## Resume & Crash Recovery

The scraper saves a checkpoint file (`data/_checkpoint.json`) after every page. If it crashes, gets blocked, or you press Ctrl+C, **no data is lost**.

### How it works

- After each page is scraped, all raw listings + progress are saved to disk
- On Ctrl+C or crash, partial results are still written to your CSV/JSON output
- Use `--resume` to pick up exactly where you left off

### Usage

```bash
# Start scraping 20 pages
python main.py --pages 20

# ... you press Ctrl+C at page 8, or the script crashes
# Partial data (pages 1-8) is saved to CSV/JSON automatically

# Resume from page 9
python main.py --pages 20 --resume

# The checkpoint auto-clears when a fresh (non-resume) run starts
```

### Important notes

- `--resume` only works if the `--url` matches the previous run (different URL = fresh start)
- The checkpoint file is at `data/_checkpoint.json` -- you can delete it manually to force a fresh start
- A fresh run (without `--resume`) automatically clears any old checkpoint

## How It Works

1. Opens 99acres search page in real Chromium with stealth patches
2. Intercepts XHR API responses for structured JSON data
3. Falls back to embedded `<script>` JSON parsing if XHR is empty
4. Falls back to DOM element parsing as last resort
5. Saves checkpoint to disk after every page (crash-safe)
6. Deduplicates across pages, saves CSV + JSON

## Project Structure

```
99acres-scraper/
├── main.py                  # CLI entry point
├── requirements.txt
├── .env                     # Optional proxy config
├── scraper/
│   ├── __init__.py
│   ├── config.py            # Search URL and defaults
│   ├── browser_scraper.py   # Playwright browser automation
│   ├── parser.py            # Raw API -> structured Property
│   ├── models.py            # Pydantic data model (77 fields)
│   └── utils.py             # Price/date/code normalization
├── data/                    # Output CSV + JSON + checkpoint file
└── logs/                    # scraper.log + debug screenshots
```
