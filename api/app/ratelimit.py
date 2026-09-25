import ipaddress
import threading
import time

from fastapi import Request


def client_ip(request: Request) -> str:
    """IP thật (uvicorn --proxy-headers đã áp X-Forwarded-For của Caddy)."""
    return request.client.host if request.client else "unknown"


def rate_key(ip: str) -> str:
    """IPv4 theo /32, IPv6 theo /64."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return ip


class FixedWindowLimiter:
    # ponytail: bộ đếm trong bộ nhớ, đúng khi api chạy 1 process; nhiều process thì chuyển sang bảng Postgres.
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, now: float | None = None) -> bool:
        """Trả True nếu còn trong hạn mức."""
        bucket = int((now if now is not None else time.time()) // self.window)
        with self._lock:
            current_bucket, count = self._hits.get(key, (bucket, 0))
            if current_bucket != bucket:
                count = 0
            count += 1
            self._hits[key] = (bucket, count)
            return count <= self.limit

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
