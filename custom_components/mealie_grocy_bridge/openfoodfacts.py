"""Fill missing calories and product pictures in Grocy from Open Food Facts.

Only empty fields are filled; values maintained in Grocy are never
overwritten. ``dry_run`` (the default) looks everything up and reports what
would change, without writing to Grocy.

Open Food Facts allows 15 product reads per minute and IP, so lookups are
spaced out and their results are cached (hits for a week, misses for a
month). A dry run therefore makes the following real run fast.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .const import CONF_GROCY_TOKEN, CONF_GROCY_URL, DOMAIN, REQUEST_TIMEOUT, normalize_base_url
from .nutrition_plan import (
    filter_excluded_products,
    format_package,
    names_match,
    parse_off_product,
    picture_file_name,
    plan_update,
    select_candidates,
)

_LOGGER = logging.getLogger(__name__)

EVENT_OFF_ENRICHED = f"{DOMAIN}_openfoodfacts_enriched"
OFF_PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
OFF_FIELDS = (
    "product_name,product_name_de,nutriments,product_quantity,product_quantity_unit,"
    "quantity,image_front_url,image_url"
)
OFF_MIN_INTERVAL = 4.5  # seconds between product reads → about 13 per minute (limit: 15)
OFF_TIMEOUT = aiohttp.ClientTimeout(total=20)
CACHE_HIT_DAYS = 7
CACHE_MISS_DAYS = 30
MAX_IMAGE_BYTES = 5 * 1024 * 1024
STORAGE_KEY = f"{DOMAIN}.openfoodfacts_cache"
STORAGE_VERSION = 1
DEFAULT_LIMIT = 15


class _OffClient:
    """Rate-limited, cached Open Food Facts lookups."""

    def __init__(self, hass: HomeAssistant, runtime_data: dict, user_agent: str) -> None:
        self._session = async_get_clientsession(hass)
        self._runtime = runtime_data
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._cache: dict = {}
        self.lookups = 0

    async def async_load(self) -> None:
        self._cache = (await self._store.async_load()) or {}

    async def async_save(self) -> None:
        await self._store.async_save(self._cache)

    def _cached(self, barcode: str):
        entry = self._cache.get(barcode)
        if not isinstance(entry, dict):
            return False, None
        try:
            checked = dt_util.parse_datetime(entry.get("checked", ""))
        except (TypeError, ValueError):
            checked = None
        if checked is None:
            return False, None
        max_age = timedelta(days=CACHE_HIT_DAYS if entry.get("product") else CACHE_MISS_DAYS)
        if dt_util.utcnow() - checked > max_age:
            return False, None
        return True, entry.get("product")

    async def async_lookup(self, barcode: str) -> dict | None:
        """Return the parsed product, or None when Open Food Facts has no usable entry."""
        found, product = self._cached(barcode)
        if found:
            return product

        wait = self._runtime.get("off_last_request", 0) + OFF_MIN_INTERVAL - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._runtime["off_last_request"] = time.monotonic()
        self.lookups += 1

        async with self._session.get(
            OFF_PRODUCT_URL.format(barcode=barcode),
            params={"fields": OFF_FIELDS},
            headers=self._headers,
            timeout=OFF_TIMEOUT,
        ) as response:
            if response.status == 404:
                payload = {"status": 0}
            elif response.status == 429:
                raise RuntimeError("Open Food Facts: zu viele Anfragen (HTTP 429), später erneut versuchen")
            elif response.status != 200:
                raise RuntimeError(f"Open Food Facts: HTTP {response.status}")
            else:
                payload = await response.json(content_type=None)

        product = parse_off_product(payload)
        self._cache[barcode] = {"checked": dt_util.utcnow().isoformat(), "product": product}
        return product

    async def async_download_image(self, url: str) -> bytes:
        async with self._session.get(url, headers={"User-Agent": self._headers["User-Agent"]}, timeout=OFF_TIMEOUT) as response:
            if response.status != 200:
                raise RuntimeError(f"Bild nicht ladbar (HTTP {response.status})")
            data = await response.content.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise RuntimeError("Bild größer als 5 MB")
        return data


async def _grocy_get(session, url, headers):
    async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT) as response:
        if response.status != 200:
            raise RuntimeError(f"{url.rsplit('/api/', 1)[-1]}: HTTP {response.status}")
        return await response.json()


async def _grocy_write(session, method, url, headers, **kwargs) -> None:
    async with session.request(method, url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs) as response:
        if response.status not in (200, 204):
            text = (await response.text())[:200]
            raise RuntimeError(f"Grocy HTTP {response.status}: {text}")


async def async_enrich_from_openfoodfacts(
    hass: HomeAssistant,
    runtime_data: dict,
    *,
    dry_run: bool = True,
    limit: int = DEFAULT_LIMIT,
    include_calories: bool = True,
    include_images: bool = True,
    exclude_product_groups=(),
    name_check: bool = True,
    confirm_barcodes=(),
) -> dict:
    """Look up products missing calories or pictures and (unless dry_run) fill them in Grocy."""
    lock: asyncio.Lock = runtime_data.setdefault("off_enrich_lock", asyncio.Lock())
    if lock.locked():
        return {"status": "busy", "dry_run": dry_run}

    async with lock:
        result = await _async_run(
            hass,
            runtime_data,
            dry_run,
            max(1, int(limit)),
            include_calories,
            include_images,
            exclude_product_groups,
            name_check,
            {str(code).strip() for code in confirm_barcodes or []},
        )

    runtime_data["last_off_enrichment"] = result
    hass.bus.async_fire(EVENT_OFF_ENRICHED, result)
    _LOGGER.info(
        "Open-Food-Facts-Abgleich (%s): %s Produkte geprüft, %s mit Änderungen, %s Namen prüfen, %s ohne Treffer, %s offen",
        "Probelauf" if dry_run else "geschrieben",
        result.get("processed", 0),
        len(result.get("updates", [])),
        len(result.get("name_mismatch", [])),
        len(result.get("not_found", [])),
        result.get("remaining", 0),
    )
    return result


async def _async_run(
    hass, runtime_data, dry_run, limit, include_calories, include_images, exclude_groups, name_check, confirmed
) -> dict:
    result = {
        "status": "ok",
        "dry_run": dry_run,
        "time": dt_util.now().isoformat(),
        "processed": 0,
        "lookups": 0,
        "remaining": 0,
        "updates": [],
        "name_mismatch": [],
        "not_found": [],
        "skipped": [],
        "without_barcode": [],
        "excluded_groups": [],
        "errors": [],
    }
    grocy_url = normalize_base_url(runtime_data[CONF_GROCY_URL])
    headers = {"GROCY-API-KEY": runtime_data[CONF_GROCY_TOKEN]}
    session = async_get_clientsession(hass)

    try:
        products, barcodes, quantity_units, product_groups = await asyncio.gather(
            _grocy_get(session, f"{grocy_url}/api/objects/products", headers),
            _grocy_get(session, f"{grocy_url}/api/objects/product_barcodes", headers),
            _grocy_get(session, f"{grocy_url}/api/objects/quantity_units", headers),
            _grocy_get(session, f"{grocy_url}/api/objects/product_groups", headers),
        )
    except (aiohttp.ClientError, TimeoutError, RuntimeError) as err:
        result["status"] = "error"
        result["errors"].append(f"Grocy nicht abrufbar: {err}")
        return result

    products, excluded = filter_excluded_products(products, product_groups, exclude_groups)
    result["excluded_groups"] = excluded
    candidates, without_barcode = select_candidates(
        products, barcodes, quantity_units, include_calories, include_images
    )
    result["without_barcode"] = without_barcode

    integration = await async_get_integration(hass, DOMAIN)
    client = _OffClient(
        hass,
        runtime_data,
        f"MealieGrocyBridge/{integration.version or 'dev'} (https://github.com/SniperWCW/Grocy-Mealie_Bridge)",
    )
    await client.async_load()

    try:
        for index, candidate in enumerate(candidates):
            if result["processed"] >= limit:
                result["remaining"] = len(candidates) - index
                break
            result["processed"] += 1

            off_product, barcode = None, candidate.barcodes[0]
            try:
                for code in candidate.barcodes:
                    off_product = await client.async_lookup(code)
                    if off_product:
                        barcode = code
                        break
            except (aiohttp.ClientError, TimeoutError, RuntimeError) as err:
                result["errors"].append(f"{candidate.name}: {err}")
                if "429" in str(err):
                    result["remaining"] = len(candidates) - index
                    break
                continue

            if not off_product:
                result["not_found"].append(candidate.name)
                continue

            update = plan_update(candidate, barcode, off_product)
            if not update.has_changes:
                result["skipped"].append({"name": candidate.name, "reason": ", ".join(update.notes)})
                continue

            entry = {
                "name": update.name,
                "barcode": update.barcode,
                "off_name": off_product.get("name", ""),
                "stock_unit": candidate.stock_unit,
            }
            package = format_package(off_product.get("package_amount"), off_product.get("package_unit"))
            if package:
                entry["package"] = package
            if update.calories is not None:
                entry["calories"] = update.calories
            if update.image_url:
                entry["image"] = update.image_url
            if update.notes:
                entry["notes"] = ", ".join(update.notes)

            if name_check and update.barcode not in confirmed and not names_match(
                candidate.name, off_product.get("name", "")
            ):
                # Barcode may belong to another product: report, but do not write.
                result["name_mismatch"].append(entry)
                continue

            if not dry_run:
                try:
                    await _apply_update(session, client, grocy_url, headers, update)
                except (aiohttp.ClientError, TimeoutError, RuntimeError) as err:
                    result["errors"].append(f"{candidate.name}: nicht geschrieben ({err})")
                    continue
            result["updates"].append(entry)
    finally:
        result["lookups"] = client.lookups
        await client.async_save()

    if result["errors"]:
        result["status"] = "partial" if result["updates"] else "error"
    return result


async def _apply_update(session, client, grocy_url, headers, update) -> None:
    """Write calories and picture of one product to Grocy."""
    product_url = f"{grocy_url}/api/objects/products/{update.product_id}"
    if update.calories is not None:
        await _grocy_write(session, "PUT", product_url, headers, json={"calories": update.calories})
    if update.image_url:
        image = await client.async_download_image(update.image_url)
        file_name = picture_file_name(update.barcode, update.image_url)
        encoded = base64.b64encode(file_name.encode()).decode()
        await _grocy_write(
            session,
            "PUT",
            f"{grocy_url}/api/files/productpictures/{encoded}",
            {**headers, "Content-Type": "application/octet-stream"},
            data=image,
        )
        await _grocy_write(session, "PUT", product_url, headers, json={"picture_file_name": file_name})
