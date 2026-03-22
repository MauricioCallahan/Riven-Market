API_BASE_URL = "https://api.warframe.market/v1"
AUCTION_BASE_URL = "https://warframe.market/auction/"

API_HEADERS = {
    "User-Agent" : "Riven-pricer/0.1",
    "Accept" : "application/json",
    "Accept-Language" : "en",
}

VALID_PLATFORMS = {"pc", "ps4", "xbox", "switch"}

WARFRAMESTAT_WEAPONS_URL = "https://api.warframestat.us/weapons"

# Fields that use a dropdown instead of a free-text entry box.
# Keys match API param names; values are the valid choices.
DROPDOWN_OPTIONS = {
    "sort_by": ["price_asc", "price_desc"],  # positive_attr_asc/desc removed — API returns 500 for these
    "buyout_policy": ["direct", "auction"],  # "auction" = bid-only; "with_bid" was wrong and returns 400
    "polarity": ["any", "madurai", "vazarin", "naramon", "zenurik", "unairu", "penjaga"],
}
