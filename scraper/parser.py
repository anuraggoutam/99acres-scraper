from .models import Property
from .utils import (
    normalize_price, epoch_to_date, facing_map, availability_map,
    furnish_map, age_map, parse_parking, parse_overlooking,
)
import logging

logger = logging.getLogger(__name__)


def _g(raw: dict, *keys, default=None, skip_zero=False):
    """Return first non-empty value from candidate keys.

    By default keeps numeric zeros (e.g. BATHROOM_NUM='0').
    Set skip_zero=True for IDs where '0' means 'not applicable'.
    """
    for k in keys:
        val = raw.get(k)
        if val is None or val == "":
            continue
        if skip_zero and (val == 0 or val == "0"):
            continue
        return val
    return default


def _s(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def parse_property(raw: dict) -> Property | None:
    try:
        # SPID is always clean numeric; PROP_ID may have letter prefix
        raw_id = _g(raw, "SPID", "PROP_ID", "propId", "id")
        if raw_id is None:
            return None
        prop_id = str(raw_id).strip()
        # Strip single leading letter (e.g. "N87338500" -> "87338500")
        import re as _re
        m = _re.match(r'^[A-Z]?(\d{5,})$', prop_id)
        prop_id = m.group(1) if m else prop_id
        if not prop_id or not any(c.isdigit() for c in prop_id):
            return None

        fmt = raw.get("FORMATTED") or {}
        map_d = raw.get("MAP_DETAILS") or {}
        loc_d = raw.get("location") or {}
        profile = raw.get("profile") or {}
        profile_super = profile.get("super") or {}
        xid = raw.get("xid") or {}
        avail = fmt.get("AVAIL") or {}
        fomo = raw.get("FOMO") or {}

        # -- Listing link --
        pd_url = _g(raw, "PD_URL", "PROP_DETAILS_URL", "propUrl", "url")
        listing_link = None
        if pd_url:
            pd_url = str(pd_url)
            listing_link = pd_url if pd_url.startswith("http") else "https://www.99acres.com/" + pd_url.lstrip("/")

        # -- Deal type --
        pref = _g(raw, "PREFERENCE")
        deal_type = {"S": "Buy", "R": "Rent", "P": "PG"}.get(str(pref), _s(pref)) if pref else None

        # -- Transaction type --
        transact = _g(raw, "TRANSACT_TYPE")
        transaction_type = {"1": "Resale", "2": "New Booking"}.get(str(transact), _s(transact)) if transact else None

        # -- Availability --
        avail_code = _g(raw, "AVAILABILITY")
        avail_label = availability_map(str(avail_code)) if avail_code else None
        avail_date = _s(avail.get("AVAILABILITY_DATE")) or None

        # -- Agent type --
        class_label = _g(raw, "CLASS_LABEL", "CLASS")
        agency_type = {"O": "Owner", "A": "Agent/Dealer", "B": "Builder"}.get(str(class_label), _s(class_label)) if class_label else None

        # -- RERA --
        rera_status = _g(raw, "IS_POSTER_RERA_REGISTERED", "IS_DEALER_RERA_REGISTERED")
        xid_rera = xid.get("PROJ_RERA_REGISTRATION_ID")
        xid_reg_status = xid.get("REGISTRATION_STATUS")

        # -- Tags --
        secondary_tags = raw.get("SECONDARY_TAGS") or []
        tags_str = ", ".join(secondary_tags) if isinstance(secondary_tags, list) and secondary_tags else None

        # -- Parking --
        parking_raw = _g(raw, "RESERVED_PARKING")
        parking = parse_parking(parking_raw) if parking_raw else None

        # -- Furnishing --
        furnish_code = _g(raw, "FURNISH", skip_zero=True)
        furnish_label = fmt.get("FURNISH_LABEL") or (furnish_map(str(furnish_code)) if furnish_code else None)
        furnish_attrs = fmt.get("FURNISHING_ATTRIBUTES")

        # -- BHK / Config --
        bedrooms = _g(raw, "BEDROOM_NUM", skip_zero=True)
        bathrooms = _g(raw, "BATHROOM_NUM")
        balcony = _g(raw, "BALCONY_NUM", skip_zero=True) or _g(raw, "BALCONY_ATTACHED")
        prop_type = _g(raw, "PROPERTY_TYPE") or fmt.get("PROP_TYPE_LABEL")
        config_short = f"{bedrooms} BHK" if bedrooms else None
        config_long = f"{bedrooms} BHK {prop_type}" if bedrooms and prop_type else _s(prop_type)

        # -- Price --
        price_label = _s(_g(raw, "PRICE", "FORMATTED_PRICE"))
        price_text = _s(fmt.get("PRICE_IN_WORDS"))
        price_num = normalize_price(_g(raw, "MIN_PRICE", "MAX_PRICE") or price_label or "")

        # -- Member since --
        member_since_epoch = profile_super.get("SINCE")
        member_since = epoch_to_date(member_since_epoch) if member_since_epoch else None

        # -- Corner --
        corner = _g(raw, "CORNER_PROPERTY")
        is_corner = "Yes" if corner == "Y" else ("No" if corner == "N" else None)

        # -- Overlooking --
        overlooking_raw = _g(raw, "OVERLOOKING")
        overlooking = parse_overlooking(overlooking_raw) if overlooking_raw else None

        # -- Highlights --
        top_usps = raw.get("TOP_USPS")
        highlights = ", ".join(top_usps) if isinstance(top_usps, list) and top_usps else None
        proj_highlights = xid.get("PROJECT_HIGHLIGHTS")
        if isinstance(proj_highlights, list) and proj_highlights and not highlights:
            highlights = ", ".join(proj_highlights)

        # -- Building ID (skip '0' = no building) --
        building_id = _g(raw, "BUILDING_ID", skip_zero=True) or (loc_d.get("BUILDING_ID") if loc_d.get("BUILDING_ID") not in (None, "", "0", 0) else None)

        # -- Floor label --
        floor_num = _g(raw, "FLOOR_NUM", skip_zero=True) or fmt.get("FLOOR_NUMBER")
        total_floor = _g(raw, "TOTAL_FLOOR", skip_zero=True)
        floor_label = f"{floor_num} of {total_floor}" if floor_num and total_floor else _s(floor_num)

        return Property(
            listing_link=listing_link,
            listing_id=prop_id,
            building_id=_s(building_id),

            title=_s(_g(raw, "PROP_HEADING", "title", "ALT_TAG")),
            property_type=_s(prop_type),
            deal_type=deal_type,
            posted_date=epoch_to_date(_g(raw, "POSTING_DATE__U", "POSTING_DATE")),
            modified_date=epoch_to_date(_g(raw, "UPDATE_DATE__U", "UPDATE_DATE")),
            status=_s(_g(raw, "PRODUCT_TYPE", "LISTING")),
            is_verified=_s(_g(raw, "VERIFIED", "SELF_VERIFIED")),

            availability_label=_s(avail_label),
            availability_date=avail_date,

            bedrooms=_s(bedrooms),
            bathrooms=_s(bathrooms),
            balcony=_s(balcony),
            living_room=None,
            kitchen=None,
            additional_rooms_qty=None,
            additional_rooms=None,

            super_built_up_area_sq_ft=_s(_g(raw, "SUPERBUILTUP_SQFT", "SUPERBUILTUP_AREA")),
            built_up_area_sq_ft=_s(_g(raw, "BUILTUP_AREA", "BUILTUP_SQFT")),
            carpet_area=_s(_g(raw, "CARPET_AREA", "CARPET_SQFT")),
            configuration_short=config_short,
            configuration_long=config_long,
            is_corner_property=is_corner,

            price_label=price_label,
            price_num=price_num,
            price_text=price_text,
            price_per_sq_ft=_s(_g(raw, "PRICE_SQFT", "PRICE_PER_UNIT_AREA") or fmt.get("PRICE_SQFT")),
            rent_price_sq_ft=None,
            all_inclusive_price=_s(_g(raw, "ALL_INCLUSIVE_PRICE")),
            is_price_negotiable=_s(_g(raw, "IS_PRICE_NEGOTIABLE")),
            tax_govt_charges=_s(_g(raw, "TAX_AND_GOVT_CHARGES")),
            early_leaving_charges=None,

            city=_s(_g(raw, "CITY") or loc_d.get("CITY_NAME")),
            society=_s(_g(raw, "SOCIETY_NAME", "PROP_NAME", skip_zero=True) or loc_d.get("SOCIETY_NAME")),
            address=_s(loc_d.get("ADDRESS") or _g(raw, "LOCALITY")),
            address_desc=_s(_g(raw, "LOCALITY", "localityLabel") or loc_d.get("SHOW_CASE_LABEL")),
            floor_number=_s(floor_num),
            total_floor=_s(total_floor),
            floor_label=floor_label,
            lat=_s(map_d.get("LATITUDE")),
            lon=_s(map_d.get("LONGITUDE")),

            facing=facing_map(str(_g(raw, "FACING"))) if _g(raw, "FACING") else None,
            overlooking=overlooking,
            property_age=age_map(str(_g(raw, "AGE"))) if _g(raw, "AGE", skip_zero=True) else None,
            key_highlights=highlights,
            transaction_type=transaction_type,
            width_of_facing_road=_s(_g(raw, "WIDTH_OF_FACING_ROAD")),
            wheelchair_friendly=_s(_g(raw, "WHEELCHAIR_FRIENDLY")),
            property_ownership=_s(_g(raw, "VALUE_LABEL")),
            gated_community="Yes" if _g(raw, "GATED") == "Y" else ("No" if _g(raw, "GATED") == "N" else None),
            pet_friendly=_s(_g(raw, "PET_FRIENDLY")),
            flooring=None,
            corner_property=is_corner,
            water_source=None,

            furnishing=_s(furnish_label),
            parking=parking,
            power_backup=None,
            about=_s(_g(raw, "DESCRIPTION")),
            furnishing_details=_s(furnish_attrs),
            features=_s(_g(raw, "AMENITIES", "FEATURES")),

            agent_name=_s(_g(raw, "CONTACT_NAME") or profile.get("CONTACT_NAME")),
            agency_name=_s(_g(raw, "CONTACT_COMPANY_NAME") or profile.get("CONTACT_COMPANY_NAME")),
            agency_address=_s(profile.get("CONTACT_CITY")),
            agency_url=_s(profile.get("URL") or profile.get("DEALER_SEO_URL")),
            agency_type=agency_type,
            agency_profile=_s(raw.get("CLASS_HEADING")),
            agency_photo_url=_s(_g(raw, "DEALER_PHOTO_URL") or profile.get("PHOTO_URL")),
            agency_hidden_phone=None,
            agency_hidden_mobile=None,
            member_since=member_since,
            brokerage_type=_s(_g(raw, "BROKERAGE")),

            people_activities=_s(fomo.get("text")),
            ad_keywords=tags_str,

            rera_reg_status=_s(xid_reg_status or rera_status),
            rera_reg_num=_s(xid_rera),
        )
    except Exception as e:
        logger.warning(f"Failed to parse property: {e}", exc_info=True)
        return None
