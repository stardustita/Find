from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def _coerce(current, raw: str):
    if isinstance(current, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int):
        return int(float(raw))
    if isinstance(current, float):
        return float(raw)
    if isinstance(current, tuple):
        return tuple(x.strip() for x in raw.split(",") if x.strip())
    return raw.strip().strip('"').strip("'")

def _read_simple_yaml(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out

def _read_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

@dataclass
class Settings:
    db_path: str = str(ROOT / "data" / "radar.db")
    rpc_ws_urls: tuple = (
        "wss://api.mainnet-beta.solana.com",
        "wss://solana-rpc.publicnode.com",
    )
    feed: str = "onchain"                 # onchain | pumpportal | both
    ws_url: str = "wss://pumpportal.fun/api/data"
    ws_apikey: str = ""
    rpc_url: str = "https://api.mainnet-beta.solana.com"
    rpc_url_2: str = ""
    jup_price_url: str = "https://api.jup.ag/price/v3"
    dexscreener_url: str = "https://api.dexscreener.com/latest/dex/tokens"
    ipfs_gateways: tuple = ("https://ipfs.io/ipfs/", "https://cf-ipfs.com/ipfs/")
    amm_enabled: bool = True

    tick_seconds: float = 2.0
    snapshot_every_s: float = 5.0
    max_watch_seconds: float = 900.0
    trade_stream: bool = True
    max_trade_subscriptions: int = 120
    prefilter_min_sol_60s: float = 0.8
    prefilter_min_buyers: int = 3
    prefilter_max_age_s: float = 180.0
    kill_no_buy_seconds: float = 150.0
    grad_vsol: float = 115.0

    bankroll_sol: float = 10.0
    position_sol: float = 0.10
    max_open_positions: int = 25
    max_daily_loss_sol: float = 1.0
    slippage_bps: int = 1500
    pump_fee_bps: int = 100
    priority_fee_sol: float = 0.0004
    curve_stop_pct: float = 0.35

    # Ingresso curva (taratura su dati reali 2026-11: ingressi oltre meta' curva = EV negativo)
    max_entry_mcap_sol: float = 150.0
    entry_min_progress: float = 0.03
    entry_max_progress: float = 0.45
    entry_max_ret_30s: float = 0.85
    entry_confirm_ticks: int = 2

    telegram_token: str = ""
    telegram_chat: str = ""
    webhook_url: str = ""
    min_alert_score: float = 0.44
    min_strong_score: float = 0.54
    watch_score: float = 0.34
    max_entry_per_hour: int = 12
    max_signals_per_hour: int = 40

    # Runner post-graduazione
    runner_size_sol: float = 0.15
    runner_stop_pct: float = 0.45
    runner_min_liq_sol: float = 8.0
    runner_max_age_s: float = 21600.0
    runner_min_turnover: float = 0.10
    runner_min_buyers: int = 12
    runner_max_ath_mult: float = 25.0
    runner_watch_score: float = 0.45
    runner_entry_score: float = 0.60
    runner_strong_score: float = 0.75
    runner_max_tracked_pools: int = 400
    runner_max_open: int = 10

    narrative_enabled: bool = False
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    api_host: str = "127.0.0.1"   # override con PR_API_HOST=0.0.0.0 solo se serve accesso LAN
    api_port: int = 8787

    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Settings":
        _read_env_file(ROOT / ".env")
        s = cls()
        cfg = _read_simple_yaml(ROOT / "config.yaml")
        known = set(s.__dataclass_fields__)
        for k, v in cfg.items():
            if k in known:
                try:
                    setattr(s, k, _coerce(getattr(s, k), str(v)))
                except Exception:
                    pass
            else:
                s.extra[k] = v
        for name in known:
            raw = os.getenv("PR_" + name.upper())
            if raw is not None:
                try:
                    setattr(s, name, _coerce(getattr(s, name), raw))
                except Exception:
                    pass
        s.ws_apikey = os.getenv("PUMPPORTAL_API_KEY", s.ws_apikey) or ""
        s.telegram_token = os.getenv("TELEGRAM_TOKEN", s.telegram_token) or ""
        s.telegram_chat = os.getenv("TELEGRAM_CHAT", s.telegram_chat) or ""
        rpc_urls = os.getenv("PR_RPC_WS_URLS")
        if rpc_urls:
            s.rpc_ws_urls = tuple(x.strip() for x in rpc_urls.split(",") if x.strip())
        Path(s.db_path).parent.mkdir(parents=True, exist_ok=True)
        return s

try:
    SETTINGS = Settings.load()
except Exception:
    SETTINGS = Settings()
