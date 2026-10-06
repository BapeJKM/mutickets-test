import math


def ceil_penny(raw):
    return math.ceil(raw * 100 - 1e-9) / 100


def price_for_margin(cost, fee_rate, margin):
    return ceil_penny(cost * (1 + margin) / (1 - fee_rate))


def margin_at(cost, fee_rate, list_price):
    payout = list_price * (1 - fee_rate)
    return (payout - cost) / cost


def undercut(cost, fee_rate, competitor, step=1.0, floor_margin=0.08):
    floor_price = price_for_margin(cost, fee_rate, floor_margin)
    candidate = round(competitor - step, 2)
    if candidate < floor_price:
        return None
    if margin_at(cost, fee_rate, candidate) < floor_margin:
        return None
    return candidate
