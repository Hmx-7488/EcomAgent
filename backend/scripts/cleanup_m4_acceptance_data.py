"""Remove only legacy M4 acceptance artifacts from the selected database."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal
from app.services.image_service import UPLOAD_DIR


ACCEPTANCE_USERS = (
    "m4_acceptance_admin",
    "m4_acceptance_operator",
    "m4_acceptance_service",
)


def _ids(session, sql: str, parameters=None) -> list[int]:
    return [
        int(row[0])
        for row in session.execute(text(sql), parameters or {}).all()
    ]


def _in_params(prefix: str, values: list[int]) -> tuple[str, dict]:
    names = [f"{prefix}_{index}" for index in range(len(values))]
    return (
        ", ".join(f":{name}" for name in names),
        dict(zip(names, values, strict=True)),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply cleanup; without this flag the command is read-only.",
    )
    args = parser.parse_args()
    session = SessionLocal()
    paths_to_remove: list[Path] = []
    try:
        product_ids = _ids(
            session,
            """
            SELECT id FROM products
            WHERE name LIKE 'M4 acceptance product %'
              AND brand = 'EcomAgent'
            ORDER BY id
            """,
        )
        user_ids = _ids(
            session,
            """
            SELECT id FROM users
            WHERE username IN (
                'm4_acceptance_admin',
                'm4_acceptance_operator',
                'm4_acceptance_service'
            )
            ORDER BY id
            """,
        )
        summary = {
            "mode": "apply" if args.apply else "dry_run",
            "product_ids": product_ids,
            "user_ids": user_ids,
        }
        if not args.apply:
            print(json.dumps(summary, sort_keys=True))
            return 0
        if not product_ids and not user_ids:
            print(json.dumps({**summary, "deleted": False}, sort_keys=True))
            return 0

        product_sql, product_params = _in_params("product", product_ids)
        user_sql, user_params = _in_params("user", user_ids)
        parameters = {**product_params, **user_params}

        if product_ids:
            asset_rows = session.execute(
                text(
                    f"SELECT id, url FROM assets WHERE product_id IN ({product_sql})"
                ),
                product_params,
            ).all()
            upload_root = Path(UPLOAD_DIR).resolve()
            for _asset_id, url in asset_rows:
                if not isinstance(url, str) or not url.startswith("/uploads/"):
                    continue
                candidate = (upload_root / url.rsplit("/", 1)[-1]).resolve()
                if candidate.parent == upload_root:
                    paths_to_remove.append(candidate)

            package_ids = _ids(
                session,
                f"SELECT id FROM content_packages WHERE product_id IN ({product_sql})",
                product_params,
            )
            task_ids = _ids(
                session,
                f"SELECT id FROM image_generation_tasks WHERE product_id IN ({product_sql})",
                product_params,
            )
            conversation_ids = _ids(
                session,
                f"SELECT id FROM conversations WHERE product_id IN ({product_sql})",
                product_params,
            )
            sku_ids = _ids(
                session,
                f"SELECT id FROM skus WHERE product_id IN ({product_sql})",
                product_params,
            )
            asset_ids = [int(row[0]) for row in asset_rows]

            for target_type, target_ids in (
                ("content_package", package_ids),
                ("image_task", task_ids),
                ("conversation", conversation_ids),
                ("sku", sku_ids),
                ("media_asset", asset_ids),
                ("product", product_ids),
            ):
                if target_ids:
                    target_sql, target_params = _in_params("target", target_ids)
                    session.execute(
                        text(
                            f"DELETE FROM audit_events "
                            f"WHERE target_type = :target_type "
                            f"AND target_id IN ({target_sql})"
                        ),
                        {"target_type": target_type, **target_params},
                    )

            if conversation_ids:
                value_sql, value_params = _in_params(
                    "conversation", conversation_ids
                )
                decision_ids = _ids(
                    session,
                    f"SELECT id FROM conversation_decisions "
                    f"WHERE conversation_id IN ({value_sql})",
                    value_params,
                )
                if decision_ids:
                    decision_sql, decision_params = _in_params(
                        "decision", decision_ids
                    )
                    session.execute(
                        text(
                            f"DELETE FROM conversation_fact_sources "
                            f"WHERE decision_id IN ({decision_sql})"
                        ),
                        decision_params,
                    )
                session.execute(
                    text(
                        f"DELETE FROM conversation_decisions "
                        f"WHERE conversation_id IN ({value_sql})"
                    ),
                    value_params,
                )
                session.execute(
                    text(
                        f"DELETE FROM tool_call_logs "
                        f"WHERE conversation_id IN ({value_sql})"
                    ),
                    value_params,
                )
                session.execute(
                    text(
                        f"DELETE FROM conversation_messages "
                        f"WHERE conversation_id IN ({value_sql})"
                    ),
                    value_params,
                )
                session.execute(
                    text(
                        f"DELETE FROM conversations WHERE id IN ({value_sql})"
                    ),
                    value_params,
                )

            if package_ids:
                value_sql, value_params = _in_params("package", package_ids)
                session.execute(
                    text(
                        f"DELETE FROM approval_records "
                        f"WHERE target_type = 'content_package' "
                        f"AND target_id IN ({value_sql})"
                    ),
                    value_params,
                )
                session.execute(
                    text(
                        f"DELETE FROM content_versions "
                        f"WHERE package_id IN ({value_sql})"
                    ),
                    value_params,
                )
                session.execute(
                    text(
                        f"DELETE FROM content_packages WHERE id IN ({value_sql})"
                    ),
                    value_params,
                )

            if task_ids:
                value_sql, value_params = _in_params("task", task_ids)
                session.execute(
                    text(
                        f"DELETE FROM approval_records "
                        f"WHERE target_type = 'image_task' "
                        f"AND target_id IN ({value_sql})"
                    ),
                    value_params,
                )
                session.execute(
                    text(
                        f"DELETE FROM image_generation_tasks "
                        f"WHERE id IN ({value_sql})"
                    ),
                    value_params,
                )

            if sku_ids:
                value_sql, value_params = _in_params("sku", sku_ids)
                session.execute(
                    text(f"DELETE FROM sku_costs WHERE sku_id IN ({value_sql})"),
                    value_params,
                )
                session.execute(
                    text(f"DELETE FROM inventory WHERE sku_id IN ({value_sql})"),
                    value_params,
                )
                session.execute(
                    text(f"DELETE FROM order_items WHERE sku_id IN ({value_sql})"),
                    value_params,
                )
                session.execute(
                    text(f"DELETE FROM skus WHERE id IN ({value_sql})"),
                    value_params,
                )

            session.execute(
                text(
                    f"DELETE FROM order_items WHERE product_id IN ({product_sql})"
                ),
                product_params,
            )
            session.execute(
                text(
                    f"DELETE FROM after_sales_rules "
                    f"WHERE product_id IN ({product_sql})"
                ),
                product_params,
            )
            session.execute(
                text(
                    f"DELETE FROM generated_contents "
                    f"WHERE product_id IN ({product_sql})"
                ),
                product_params,
            )
            session.execute(
                text(f"DELETE FROM assets WHERE product_id IN ({product_sql})"),
                product_params,
            )
            session.execute(
                text(f"DELETE FROM products WHERE id IN ({product_sql})"),
                product_params,
            )

        if user_ids:
            session.execute(
                text(f"DELETE FROM audit_events WHERE actor_id IN ({user_sql})"),
                user_params,
            )
            session.execute(
                text(
                    f"DELETE FROM approval_records WHERE actor_id IN ({user_sql})"
                ),
                user_params,
            )
            session.execute(
                text(f"DELETE FROM users WHERE id IN ({user_sql})"),
                user_params,
            )
        session.commit()
        for path in paths_to_remove:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        print(
            json.dumps(
                {
                    **summary,
                    "deleted": True,
                    "removed_upload_files": len(paths_to_remove),
                },
                sort_keys=True,
            )
        )
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
