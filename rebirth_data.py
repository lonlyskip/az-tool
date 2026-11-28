"""Authoritative jump and cumulative rebirth costs supplied by the AZ Tool user."""
from decimal import Decimal, InvalidOperation

# Values are represented in the game's base unit (plain numbers); each suffix is x1000.
UNIT_EXPONENT = {
    "": 0, "K": 1, "M": 2, "B": 3, "T": 4,
    "QA": 5, "QI": 6, "SX": 7, "SP": 8, "OC": 9, "NO": 10,
}

JUMP_COST_TEXT = (
    "259|1.6K|9.95K|61.6K|381K|2.36M|14.7M|90.5M|560M|3.47B|21.4B|133B|824B|5.1T|31.57T|195T|1.21Qa|7.5Qa|46.4Qa|287Qa|"
    "1.78qi|11.0qi|68.2qi|422qi|2.61sx|10.9sx|28.3sx|70.9sx|160sx|303sx|499sx|814sx|1.32sp|2.12sp|3.33sp|5.12sp|7.61sp|10.8sp|14.6sp|18.6sp|"
    "22.7sp|27.7sp|83.78sp|41.1sp|50.1sp|60.5sp|73sp|87.3sp|103sp|122sp|143sp|165sp|189sp|214sp|239sp|277sp|338sp|412sp|503sp|612sp|"
    "745sp|905sp|1.09oc|1.32oc|1.6oc|1.93oc|2.32oc|2.79oc|3.33oc|3.97oc|4.71oc|5.56oc|6.54oc|7.65oc|8.91oc|10.38oc|12.09oc|14.08oc|16.39oc|19.09oc|"
    "22.23oc|25.89oc|30.15oc|35.11oc|40.89oc|47.62oc|55.46oc|64.59oc|75.22oc|87.61oc|102.03oc|118.81oc|138.37oc|161.15oc|187.67oc|59.4oc"
).split("|")

REBIRTH_COST_TEXT = (
    "259|1.859K|11.809K|73.409K|454.409K|2.814409M|17.514409M|108.014409M|668.014409M|4.138014B|"
    "25.538014B|158.538014B|982.538014B|6.082538T|37.652538T|232.652538T|1.442653Qa|8.942653Qa|55.342653Qa|342.342653Qa|"
    "2.122343qi|13.122343qi|81.322343qi|503.322343qi|3.113322sx|14.013322sx|42.313322sx|113.213322sx|273.213322sx|576.213322sx|"
    "1.075213sp|1.889213sp|3.209213sp|5.329213sp|8.659213sp|13.779213sp|21.389213sp|32.189213sp|46.789213sp|65.389213sp|"
    "88.089213sp|115.789213sp|199.569213sp|240.669213sp|290.769213sp|351.269213sp|424.269213sp|511.569213sp|614.569213sp|736.569213sp|879.569213sp|"
    "1.044569oc|1.233569oc|1.447569oc|1.686569oc|1.963569oc|2.301569oc|2.713569oc|3.216569oc|3.828569oc|"
    "4.573569oc|5.478569oc|6.568569oc|7.888569oc|9.488569oc|11.418569oc|13.738569oc|16.528569oc|19.858569oc|23.828569oc|"
    "28.538569oc|34.098569oc|40.638569oc|48.288569oc|57.198569oc|67.578569oc|79.668569oc|93.748569oc|110.138569oc|129.228569oc|"
    "151.458569oc|177.348569oc|207.498569oc|242.608569oc|283.498569oc|331.118569oc|386.578569oc|451.168569oc|526.388569oc|613.998569oc|"
    "716.028569oc|834.838569oc|973.208569oc|1.134359no|1.381429no"
).split("|")


def parse_game_money(value):
    """Parse a game amount such as 1.381429no into an exact Decimal base value."""
    raw = str(value or "").strip().replace(",", "").replace(" ", "")
    import re
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([a-zA-Z]*)", raw)
    if not match:
        raise ValueError("صيغة المبلغ غير صحيحة.")
    number, suffix = match.groups()
    suffix = suffix.upper()
    if suffix not in UNIT_EXPONENT:
        raise ValueError(f"وحدة غير معروفة: {suffix}")
    return Decimal(number) * (Decimal(1000) ** UNIT_EXPONENT[suffix])


def format_game_money(value):
    amount = Decimal(value)
    if amount <= 0:
        return "0.00"
    suffixes = ("", "K", "M", "B", "T", "Qa", "qi", "sx", "sp", "oc", "no")
    exponent = 0
    while amount >= 1000 and exponent < len(suffixes) - 1:
        amount /= 1000
        exponent += 1
    return f"{amount:,.2f}{suffixes[exponent]}"


JUMP_COSTS = tuple(parse_game_money(item) for item in JUMP_COST_TEXT)
REBIRTH_COSTS = tuple(parse_game_money(item) for item in REBIRTH_COST_TEXT)
if len(JUMP_COSTS) != 96 or len(REBIRTH_COSTS) != 95:
    raise RuntimeError("AZ Tool cost table is incomplete.")


def next_rebirth(balance):
    balance = Decimal(balance)
    for number, cost in enumerate(REBIRTH_COSTS, start=1):
        if balance < cost:
            return number, cost, False
    return len(REBIRTH_COSTS), REBIRTH_COSTS[-1], True


def remaining_time(balance, income_per_second):
    balance = Decimal(balance)
    income = Decimal(income_per_second)
    if income <= 0:
        raise ValueError("الدخل بالثانية يجب أن يكون أكبر من صفر.")
    number, cost, complete = next_rebirth(balance)
    if complete:
        return number, cost, Decimal(0)
    return number, cost, max(Decimal(0), (cost - balance) / income)
