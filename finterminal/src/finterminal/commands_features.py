from __future__ import annotations

import duckdb
from rich.table import Table
from rich.console import Console

console = Console()


def features_inspect(conn: duckdb.DuckDBPyConnection, signal_id: str) -> None:
    rows = conn.execute(
        "SELECT feature_name, feature_value, is_missing "
        "FROM signal_features WHERE signal_id = ? ORDER BY feature_name",
        [signal_id],
    ).fetchall()
    if not rows:
        console.print(f"[yellow]No features found for signal_id {signal_id}[/yellow]")
        return
    t = Table(title=f"Features for {signal_id}")
    t.add_column("Feature")
    t.add_column("Value", justify="right")
    t.add_column("Missing")
    for name, value, missing in rows:
        v = "—" if missing else f"{value:.6g}" if value is not None else "NULL"
        t.add_row(name, v, "yes" if missing else "")
    console.print(t)
