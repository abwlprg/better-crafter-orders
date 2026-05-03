"""
ShopGoodwill API — Test Suite
Corre esto localmente: python test_shopgoodwill.py
Pega el output completo en el chat para continuar con el plan.
"""
import requests
import json
import time

API = "https://buyerapi.shopgoodwill.com/api"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://shopgoodwill.com",
    "Referer": "https://shopgoodwill.com/",
    "Content-Type": "application/json",
}

BASE_BODY = {
    "isSize": False, "isWeeklyDeal": False,
    "isOneCentShippingOnly": False, "isGreatDealsOnly": False,
    "searchText": "vintage levis",
    "selectedGroup": "", "selectedCategoryIds": "",
    "selectedSellerIds": "", "lowPrice": "0", "highPrice": "999999",
    "searchBuyNowOnly": "", "searchPickupOnly": "false",
    "searchNoPickupOnly": "false", "searchOneCentShippingOnly": "false",
    "searchDescriptions": "false",
    "searchClosedAuctions": "false",
    "closedAuctionEndingDate": "1/1/2001",
    "closedAuctionDaysBack": "0",
    "savedSearchId": 0,
    "sortColumn": "1",
    "page": "1", "pageSize": "3",
    "sortDescending": "false",
}

def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

# ── TEST 1: Open listings anonymous ──────────────────────────
separator("TEST 1: Open listings — anonymous")
try:
    body = {**BASE_BODY, "searchClosedAuctions": "false"}
    r = requests.post(f"{API}/Search/ItemListing", json=body, headers=HEADERS, timeout=20)
    print(f"Status: {r.status_code}")
    j = r.json()
    cat_none = j.get("categoryListModel") is None
    print(f"categoryListModel is None: {cat_none}")
    items = j.get("searchResults", {}).get("items", [])
    total = j.get("searchResults", {}).get("itemCount", 0)
    print(f"Total count: {total} | Returned: {len(items)}")
    if items:
        print(f"\nItem keys: {list(items[0].keys())}")
        print(f"\nFirst item:\n{json.dumps(items[0], indent=2)}")
except Exception as e:
    print(f"ERROR: {e}")

time.sleep(1)

# ── TEST 2: Closed listings anonymous ────────────────────────
separator("TEST 2: Closed listings — anonymous (no Bearer)")
try:
    body = {
        **BASE_BODY,
        "searchClosedAuctions": "true",
        "closedAuctionEndingDate": "1/1/2001",
        "closedAuctionDaysBack": "0",
        "sortColumn": "4",
        "sortDescending": "true",
    }
    r = requests.post(f"{API}/Search/ItemListing", json=body, headers=HEADERS, timeout=20)
    print(f"Status: {r.status_code}")
    j = r.json()
    cat_none = j.get("categoryListModel") is None
    print(f"categoryListModel is None: {cat_none}")
    items = j.get("searchResults", {}).get("items", [])
    total = j.get("searchResults", {}).get("itemCount", 0)
    print(f"Total count: {total} | Returned: {len(items)}")
    if items:
        print(f"\nItem keys: {list(items[0].keys())}")
        print(f"\nFirst item:\n{json.dumps(items[0], indent=2)}")
    elif not cat_none:
        print("Empty items — closed auctions may need auth")
except Exception as e:
    print(f"ERROR: {e}")

time.sleep(1)

# ── TEST 3: Item Detail endpoint ──────────────────────────────
separator("TEST 3: Item Detail — single item (uses itemId from Test 1)")
try:
    # Re-fetch to get a real itemId
    body = {**BASE_BODY, "searchClosedAuctions": "false", "pageSize": "1"}
    r = requests.post(f"{API}/Search/ItemListing", json=body, headers=HEADERS, timeout=20)
    items = r.json().get("searchResults", {}).get("items", [])
    if items:
        item_id = items[0]["itemId"]
        print(f"Testing itemId: {item_id}")
        r2 = requests.get(
            f"{API}/itemDetail/GetItemDetailModelByItemId/{item_id}",
            headers=HEADERS, timeout=20
        )
        print(f"Status: {r2.status_code}")
        detail = r2.json()
        print(f"Detail keys: {list(detail.keys())}")
        # Show price/status fields
        for k in ["currentPrice", "status", "message", "auctionEnded", "isClosed", "endTime", "numBids"]:
            if k in detail:
                print(f"  {k}: {detail[k]}")
    else:
        print("No items from Test 1 to use")
except Exception as e:
    print(f"ERROR: {e}")

time.sleep(1)

# ── TEST 4: Check what fields closed items have (if Test 2 returned items) ─
separator("TEST 4: Field check — closed item currentPrice / endTime")
try:
    body = {
        **BASE_BODY,
        "searchClosedAuctions": "true",
        "closedAuctionEndingDate": "1/1/2001",
        "sortDescending": "true",
        "pageSize": "1",
    }
    r = requests.post(f"{API}/Search/ItemListing", json=body, headers=HEADERS, timeout=20)
    items = r.json().get("searchResults", {}).get("items", [])
    if items:
        item = items[0]
        for field in ["currentPrice", "endTime", "numBids", "auctionEnded",
                      "isClosed", "isAvailable", "sellerId", "sellerName",
                      "title", "imageURL", "imageServer", "imageName"]:
            print(f"  {field}: {item.get(field, '<<MISSING>>')}")
    else:
        print("No closed items returned (may need auth)")
except Exception as e:
    print(f"ERROR: {e}")

print("\n✅ Tests complete — pega este output en el chat")