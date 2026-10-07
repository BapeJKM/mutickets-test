def sample_event():
    return {
        "event": "Steven Wilson",
        "date": "Wed 28 Oct 2026, 18:45",
        "venue": "Royal Albert Hall, London",
        "sections": "WCHOIR, ECHOIR, plus map labels Gallery, Second Tier, Grand Tier, Loggia, East Choir, West Choir",
        "price": "53.50 GBP seated on the event page, quantity filter left at 2",
        "availability": "Heading said 2 results. Four offers were on the list. Not a full hall count.",
        "offers": [
            {"section": "WCHOIR", "row": "7", "price_gbp": "53.50", "kind": "seated"},
            {"section": "WCHOIR", "row": "8", "price_gbp": "53.50", "kind": "seated"},
            {"section": "ECHOIR", "row": "4", "price_gbp": "63.13", "kind": "verified resale"},
            {"section": "WCHOIR", "row": "4", "price_gbp": "63.13", "kind": "verified resale"},
        ],
        "limit": 6,
        "source_url": "https://www.ticketmaster.co.uk/steven-wilson-london-28-10-2026/event/1F00644DBDE34D01",
        "fetch_date": "2026-10-07",
        "resale": {
            "source_url": "https://needaticket.co.uk/events/steven-wilson-london-london-royal-albert-hall",
            "checked": "2026-10-07 13:25",
            "listings": 49,
            "sections_listed": 12,
            "cheapest_section": "Second Tier Box 9",
            "cheapest_price_gbp": 75,
            "note": "StubHub resale asks, not Ticketmaster primary stock",
        },
    }
