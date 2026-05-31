class Ticker:
    def __init__(self, raw_symbol: str):
        if not isinstance(raw_symbol, str):
            # Fallback if something else is passed
            raw_symbol = str(raw_symbol)
        self.raw = raw_symbol
        self.canonical = self._to_canonical(raw_symbol)

    @staticmethod
    def _to_canonical(symbol: str) -> str:
        if not symbol:
            return ""
        # Convert to uppercase and strip whitespace
        symbol = symbol.upper().strip()
        # Replace space or dash with a dot
        symbol = symbol.replace(" ", ".").replace("-", ".")
        # Reduce multiple consecutive dots to a single dot
        while ".." in symbol:
            symbol = symbol.replace("..", ".")
        return symbol

    @property
    def yfinance(self) -> str:
        """Returns the yfinance-compatible representation (e.g. BRK.B -> BRK-B)"""
        return self.canonical.replace(".", "-")

    @property
    def ibkr(self) -> str:
        """Returns the IBKR-compatible representation (e.g. BRK.B -> BRK B)"""
        return self.canonical.replace(".", " ")

    def __str__(self) -> str:
        return self.canonical

    def __repr__(self) -> str:
        return f"Ticker({self.canonical!r})"

    def __eq__(self, other) -> bool:
        if isinstance(other, Ticker):
            return self.canonical == other.canonical
        if isinstance(other, str):
            return self.canonical == self._to_canonical(other)
        return False

    def __hash__(self) -> int:
        return hash(self.canonical)
