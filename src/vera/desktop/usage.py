"""Persist provider-reported token usage and aggregate local daily statistics."""

import sqlite3
from contextlib import closing
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from vera.desktop.performance import PerformanceStats
from vera.models.utils.usage import token_usage as token_usage


class UsageStats:
    """Keep aggregate inputs separate from conversation text; queries never contact providers."""

    def __init__(self, store):
        self.store = store
        self.performance = PerformanceStats(store)
        with store.lock, closing(sqlite3.connect(store.path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS model_usage (id TEXT PRIMARY KEY, timestamp INTEGER NOT NULL, project TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, cache_read INTEGER NOT NULL, cache_reported INTEGER NOT NULL)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS usage_filters ON model_usage(project, provider, model, timestamp)")
            db.execute("CREATE INDEX IF NOT EXISTS usage_time ON model_usage(timestamp)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS model_request_context (id TEXT PRIMARY KEY, session TEXT NOT NULL, "
                "task TEXT NOT NULL, cohort TEXT NOT NULL)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS request_session ON model_request_context(session, cohort)")
            db.execute("CREATE TABLE IF NOT EXISTS usage_request_links (id TEXT PRIMARY KEY, request TEXT NOT NULL)")

    def begin_request(
        self, identifier: str, session: str, task: str, delegated: bool = False, has_history: bool = False
    ) -> None:
        """Classify requests at execution time across the session's lifetime, never from a date-filtered view."""
        with self.store.lock, closing(sqlite3.connect(self.store.path)) as db, db:
            existing = db.execute(
                "SELECT 1 FROM model_request_context WHERE session=? AND cohort!='delegated' LIMIT 1", (session,)
            ).fetchone()
            db.execute(
                "INSERT OR IGNORE INTO model_request_context VALUES (?,?,?,?)",
                (
                    identifier,
                    session,
                    task,
                    "delegated" if delegated else "continued" if existing or has_history else "first",
                ),
            )

    def record(self, identifier: str, message: dict, project: str) -> None:
        """Record each reported model response once, independently of UI rendering/reconnects."""
        if not message.get("usageReported"):
            return
        usage = message["usage"]
        with self.store.lock, closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO model_usage VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    message["timestamp"],
                    project,
                    message.get("provider", ""),
                    message.get("model", "") or "unknown",
                    usage["input"],
                    usage["output"],
                    usage["cacheRead"],
                    int(usage.get("cacheReported", False)),
                ),
            )
            if request := message.get("requestId"):
                db.execute("INSERT OR IGNORE INTO usage_request_links VALUES (?,?)", (identifier, request))

    def query(self, args: dict) -> dict:
        """Aggregate 180 heatmap days and the selected trend range in the requested timezone.

        Cache hit rate is cached-read tokens / input tokens from responses that
        actually report cache counters. Unreported usage stays unknown, not zero.
        """
        days = args.get("days", 30)
        if days not in {7, 30, 90, 180}:
            raise ValueError("请选择最近 7、30、90 或 180 天。")
        group = args.get("cacheGroup", "all")
        if group not in {"all", "first", "continued"}:
            raise ValueError("请选择全部、首次请求或后续请求。")
        zone = ZoneInfo(args.get("timezone", "Asia/Shanghai"))
        today = datetime.now(zone).date()
        start = today - timedelta(days=179)
        lower = int(datetime.combine(start, time(), zone).timestamp() * 1000)
        upper = int(datetime.combine(today + timedelta(days=1), time(), zone).timestamp() * 1000)
        clauses, parameters = ["timestamp >= ?", "timestamp < ?"], [lower, upper]
        if args.get("project"):
            clauses.append("project = ?")
            parameters.append(args["project"])
        if args.get("model"):
            provider, _, model = args["model"].partition("/")
            clauses.extend(["provider = ?", "model = ?"])
            parameters.extend([provider, model])
        performance_clauses = clauses.copy()
        performance_parameters = parameters.copy()
        performance_parameters[0] = int(
            datetime.combine(today - timedelta(days=days - 1), time(), zone).timestamp() * 1000
        )
        buckets = {
            (start + timedelta(days=index)).isoformat(): {
                "date": (start + timedelta(days=index)).isoformat(),
                "input": 0,
                "output": 0,
                "cacheRead": 0,
                "cacheInput": 0,
                "cacheResponses": 0,
                "requests": 0,
                "totalTokens": 0,
            }
            for index in range(180)
        }
        grouped = buckets if group == "all" else {date: row.copy() for date, row in buckets.items()}
        with self.store.lock, closing(sqlite3.connect(self.store.path)) as db:
            options = db.execute(
                "SELECT project, provider, model FROM model_usage UNION "
                "SELECT project, provider, model FROM desktop_performance ORDER BY project, provider, model"
            ).fetchall()
            for timestamp, incoming, outgoing, cached, reported, cohort in db.execute(
                "SELECT timestamp, input_tokens, output_tokens, cache_read, cache_reported, context.cohort FROM model_usage "
                "LEFT JOIN usage_request_links links ON links.id=model_usage.id "
                "LEFT JOIN model_request_context context ON context.id=links.request WHERE " + " AND ".join(clauses),
                parameters,
            ):
                date = datetime.fromtimestamp(timestamp / 1000, zone).date().isoformat()
                targets = [buckets[date]]
                if group != "all" and cohort == group:
                    targets.append(grouped[date])
                for row in targets:
                    row["input"] += incoming
                    row["output"] += outgoing
                    row["totalTokens"] += incoming + outgoing
                    row["requests"] += 1
                    if reported:
                        row["cacheRead"] += cached
                        row["cacheInput"] += incoming
                        row["cacheResponses"] += 1
        heatmap = list(buckets.values())
        for row in [*heatmap, *grouped.values()]:
            row["cacheHitRate"] = row["cacheRead"] / row["cacheInput"] if row["cacheInput"] else None
        trend = list(grouped.values())[-days:]
        totals = {
            key: sum(row[key] for row in trend)
            for key in ("input", "output", "totalTokens", "requests", "cacheRead", "cacheInput", "cacheResponses")
        }
        totals["cacheHitRate"] = totals["cacheRead"] / totals["cacheInput"] if totals["cacheInput"] else None
        providers = self.store.get("settings", "providers", {})
        labels = {}
        for _, provider, model in options:
            configured = providers.get(provider, {})
            definition = next((item for item in configured.get("models", []) if item["id"] == model), {})
            labels[f"{provider}/{model}"] = f"{configured.get('name', provider)} · {definition.get('name') or model}"
        return {
            "heatmap": heatmap,
            "trend": trend,
            "totals": totals,
            "overviewTotals": {
                key: sum(row[key] for row in heatmap[-days:]) for key in ("input", "output", "totalTokens", "requests")
            },
            "performance": self.performance.query(performance_clauses, performance_parameters),
            "projects": sorted({row[0] for row in options}),
            "models": sorted({f"{row[1]}/{row[2]}" for row in options}),
            "modelLabels": labels,
            "timezone": str(zone),
            "days": days,
            "cacheGroup": group,
        }
