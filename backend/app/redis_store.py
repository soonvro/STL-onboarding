from __future__ import annotations

from dataclasses import dataclass

import redis


UNLOCK_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
"""


@dataclass(slots=True)
class RedisStateStore:
    client: redis.Redis

    def close(self) -> None:
        self.client.close()

    def get_inquiry_state(self, dedup_key: str) -> dict[str, str]:
        key = self._inquiry_state_key(dedup_key)
        raw = self.client.hgetall(key)
        return {str(k): str(v) for k, v in raw.items()}

    def set_inquiry_state(
        self,
        dedup_key: str,
        *,
        status: str,
        request_id: str,
        notion_page_id: str | None = None,
        error_code: str | None = None,
    ) -> None:
        ttl = 120 if status == "pending" else 2_592_000 if status == "confirmed" else 300
        mapping = {
            "status": status,
            "request_id": request_id,
            "updated_at": str(self.client.time()[0]),
        }
        if notion_page_id:
            mapping["notion_page_id"] = notion_page_id
        if error_code:
            mapping["error_code"] = error_code
        pipe = self.client.pipeline()
        pipe.hset(self._inquiry_state_key(dedup_key), mapping=mapping)
        pipe.expire(self._inquiry_state_key(dedup_key), ttl)
        pipe.execute()

    def record_page_mapping(self, notion_page_id: str, dedup_key: str) -> None:
        self.client.set(self._page_map_key(notion_page_id), dedup_key)

    def acquire_inquiry_lock(self, dedup_key: str, token: str, *, ttl_seconds: int = 60) -> bool:
        return bool(self.client.set(self._inquiry_lock_key(dedup_key), token, nx=True, ex=ttl_seconds))

    def release_inquiry_lock(self, dedup_key: str, token: str) -> None:
        self.client.eval(UNLOCK_SCRIPT, 1, self._inquiry_lock_key(dedup_key), token)

    def acquire_page_lock(self, notion_page_id: str, token: str, *, ttl_seconds: int = 30) -> bool:
        return bool(self.client.set(self._page_lock_key(notion_page_id), token, nx=True, ex=ttl_seconds))

    def release_page_lock(self, notion_page_id: str, token: str) -> None:
        self.client.eval(UNLOCK_SCRIPT, 1, self._page_lock_key(notion_page_id), token)

    def _inquiry_lock_key(self, dedup_key: str) -> str:
        return f"lock:inquiry:{dedup_key}"

    def _inquiry_state_key(self, dedup_key: str) -> str:
        return f"state:inquiry:{dedup_key}"

    def _page_lock_key(self, notion_page_id: str) -> str:
        return f"lock:page:{notion_page_id}"

    def _page_map_key(self, notion_page_id: str) -> str:
        return f"map:page:{notion_page_id}"
