"""运行独立于业务数据库的售后 Agent 评估集。"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing, redirect_stdout
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


EVAL_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = EVAL_ROOT.parent
AGENT_ROOT = PROJECT_ROOT / "agent"
DEFAULT_SUITE_PATH = EVAL_ROOT / "cases" / "seven_day_return.json"
DEFAULT_REPORT_DIR = EVAL_ROOT / "reports"


class EvaluationLimitError(RuntimeError):
    """表示单个案例超过允许的模型调用轮数。"""


class LimitedCompletions:
    """在不修改生产 Loop 的情况下限制单案例模型调用次数。"""

    def __init__(self, completions: Any, maximum_calls: int) -> None:
        self._completions = completions
        self._maximum_calls = maximum_calls
        self.call_count = 0

    def create(self, **kwargs: Any) -> Any:
        """转发模型请求，并在超过案例预算时终止当前案例。"""

        if self.call_count >= self._maximum_calls:
            raise EvaluationLimitError(
                f"单案例模型调用超过限制 {self._maximum_calls}"
            )
        self.call_count += 1
        return self._completions.create(**kwargs)


class LimitedClient:
    """保留 OpenAI Client 形状，并为评估增加调用次数限制。"""

    def __init__(self, client: Any, maximum_calls: int) -> None:
        completions = LimitedCompletions(
            client.chat.completions,
            maximum_calls,
        )
        self.chat = SimpleNamespace(
            completions=completions,
        )


def load_suite(path: Path) -> dict[str, Any]:
    """读取并验证评估集最小结构，不导入业务代码。"""

    suite = json.loads(path.read_text(encoding="utf-8"))
    required_suite_fields = {"suite_id", "fixed_date", "sources", "cases"}
    missing_suite_fields = required_suite_fields - suite.keys()
    if missing_suite_fields:
        raise ValueError(
            f"评估集缺少字段: {sorted(missing_suite_fields)}"
        )

    case_ids: set[str] = set()
    for case in suite["cases"]:
        required_case_fields = {
            "id",
            "title",
            "source_ids",
            "initial_orders",
            "messages",
            "tool_approvals",
            "expected",
        }
        missing_case_fields = required_case_fields - case.keys()
        if missing_case_fields:
            raise ValueError(
                f"案例缺少字段 {case.get('id', '<unknown>')}: "
                f"{sorted(missing_case_fields)}"
            )
        if case["id"] in case_ids:
            raise ValueError(f"案例 ID 重复: {case['id']}")
        case_ids.add(case["id"])

        unknown_sources = set(case["source_ids"]) - suite["sources"].keys()
        if unknown_sources:
            raise ValueError(
                f"案例 {case['id']} 引用了未知来源: {sorted(unknown_sources)}"
            )
        if not case["messages"] or case["messages"][-1]["role"] != "user":
            raise ValueError(f"案例 {case['id']} 必须以用户消息结束")

    return suite


def select_cases(
    suite: dict[str, Any],
    selected_ids: list[str],
) -> list[dict[str, Any]]:
    """按命令行参数选择案例，并拒绝不存在的案例 ID。"""

    cases = suite["cases"]
    if not selected_ids:
        return cases

    case_by_id = {case["id"]: case for case in cases}
    unknown_ids = set(selected_ids) - case_by_id.keys()
    if unknown_ids:
        raise ValueError(f"不存在的案例 ID: {sorted(unknown_ids)}")
    return [case_by_id[case_id] for case_id in selected_ids]


def create_case_database(
    database_path: Path,
    orders: list[dict[str, Any]],
) -> None:
    """在临时目录创建只属于当前案例的订单数据库。"""

    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute(
            """
            CREATE TABLE orders (
                order_id TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                purchased_at TEXT NOT NULL,
                shipping_status TEXT NOT NULL,
                received_at TEXT,
                refund_status TEXT
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO orders (
                order_id,
                product_name,
                purchased_at,
                shipping_status,
                received_at,
                refund_status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    order["order_id"],
                    order["product_name"],
                    order["purchased_at"],
                    order["shipping_status"],
                    order.get("received_at"),
                    order.get("refund_status"),
                )
                for order in orders
            ],
        )
        connection.commit()


def read_order_state(database_path: Path) -> dict[str, dict[str, Any]]:
    """读取临时数据库中的全部订单状态，供前后对比。"""

    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                order_id,
                product_name,
                purchased_at,
                shipping_status,
                received_at,
                refund_status
            FROM orders
            ORDER BY order_id
            """
        ).fetchall()
    return {row["order_id"]: dict(row) for row in rows}


def parse_tool_arguments(raw_arguments: str) -> dict[str, Any] | None:
    """尽力解析模型工具参数，解析失败时保留 None 供报告观察。"""

    try:
        arguments = json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError):
        return None
    return arguments if isinstance(arguments, dict) else None


def build_evaluation_middleware(
    trace: list[dict[str, Any]],
    approvals: dict[str, bool],
    permissions: dict[str, Any],
    permission_enum: Any,
) -> Callable[[Any, Callable[[Any], str]], str]:
    """创建只在评估进程使用的审批器，并记录完整工具轨迹。"""

    def evaluate_tool_call(
        tool_call: Any,
        next_handler: Callable[[Any], str],
    ) -> str:
        tool_name = tool_call.function.name
        permission = permissions.get(tool_name, permission_enum.DENY)
        approved = permission is permission_enum.ALLOW or approvals.get(
            tool_name,
            False,
        )

        if permission is permission_enum.DENY:
            tool_result = f"工具 {tool_name} 已被禁用"
        elif permission is permission_enum.ASK and not approved:
            tool_result = f"用户拒绝执行 {tool_name}"
        else:
            tool_result = next_handler(tool_call)

        trace.append(
            {
                "name": tool_name,
                "arguments": parse_tool_arguments(
                    tool_call.function.arguments
                ),
                "permission": permission.value,
                "approved": approved,
                "result": tool_result,
            }
        )
        return tool_result

    return evaluate_tool_call


def replace_prompt_date(system_prompt: str, fixed_date: str) -> str:
    """固定评估日期，避免同一案例随真实日期变化。"""

    updated_prompt, replacement_count = re.subn(
        r"当前日期是 \d{4}-\d{2}-\d{2}。",
        f"当前日期是 {fixed_date}。",
        system_prompt,
        count=1,
    )
    if replacement_count != 1:
        raise ValueError("无法在 SYSTEM_PROMPT 中定位当前日期")
    return updated_prompt


def compare_tool_sequence(
    expected_sequence: list[dict[str, Any]],
    trace: list[dict[str, Any]],
) -> tuple[bool, str]:
    """比较工具名称、顺序以及预期参数。"""

    actual_sequence = [
        {"name": entry["name"], "arguments": entry["arguments"]}
        for entry in trace
    ]
    passed = actual_sequence == expected_sequence
    return passed, (
        f"expected={expected_sequence}; actual={actual_sequence}"
    )


def compare_order_state(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    expected_updates: dict[str, dict[str, Any]],
) -> tuple[bool, str]:
    """确认只有案例明确声明的字段发生变化。"""

    expected_after = json.loads(json.dumps(before, ensure_ascii=False))
    for order_id, updates in expected_updates.items():
        if order_id not in expected_after:
            return False, f"预期更新的订单不存在: {order_id}"
        expected_after[order_id].update(updates)

    passed = after == expected_after
    return passed, f"expected={expected_after}; actual={after}"


def evaluate_response(
    response: str,
    expected: dict[str, Any],
) -> tuple[bool, list[str]]:
    """用简单词组提供语义复核信号，不替代人工判断。"""

    failures: list[str] = []
    for alternatives in expected.get("must_include_any", []):
        if not any(term in response for term in alternatives):
            failures.append(f"缺少任一概念: {alternatives}")

    forbidden_terms = [
        term
        for term in expected.get("must_not_include", [])
        if term in response
    ]
    if forbidden_terms:
        failures.append(f"出现禁止表述: {forbidden_terms}")

    return not failures, failures


def current_git_commit() -> str | None:
    """读取当前提交号写入报告，读取失败不阻塞评估。"""

    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() or None


def run_case(
    case: dict[str, Any],
    fixed_date: str,
    client: Any,
    model: Any,
    maximum_model_calls: int,
) -> dict[str, Any]:
    """在临时数据库中运行一个真实 Agent 案例并生成结果。"""

    agent_loop_module = importlib.import_module("loop.agent_loop")
    context_module = importlib.import_module("context")
    order_store = importlib.import_module(
        "knowledge.facts.orderstore.order_store"
    )
    tool_package = importlib.import_module("tool")

    original_database_path = order_store.DATABASE_PATH
    original_middleware = agent_loop_module.approval_middleware
    trace: list[dict[str, Any]] = []
    messages = context_module.build_context(
        system_prompt=replace_prompt_date(
            context_module.SYSTEM_PROMPT,
            fixed_date,
        ),
    )
    messages.extend(json.loads(json.dumps(case["messages"], ensure_ascii=False)))
    logs = io.StringIO()
    response_text = ""
    error: str | None = None

    with tempfile.TemporaryDirectory(prefix="after-sales-eval-") as directory:
        temporary_database = Path(directory) / "orders.db"
        create_case_database(temporary_database, case["initial_orders"])
        before_state = read_order_state(temporary_database)

        order_store.DATABASE_PATH = temporary_database
        agent_loop_module.approval_middleware = build_evaluation_middleware(
            trace,
            case["tool_approvals"],
            tool_package.TOOL_PERMISSIONS,
            tool_package.Permissions,
        )

        limited_client = LimitedClient(client, maximum_model_calls)
        try:
            with redirect_stdout(logs):
                response_text = (
                    agent_loop_module.agent_loop(
                        limited_client,
                        model,
                        messages,
                    )
                    or ""
                )
        except Exception as exc:  # 报告单案例失败，同时继续后续案例。
            error = f"{type(exc).__name__}: {exc}"
        finally:
            after_state = read_order_state(temporary_database)
            order_store.DATABASE_PATH = original_database_path
            agent_loop_module.approval_middleware = original_middleware

    expected = case["expected"]
    tool_passed, tool_details = compare_tool_sequence(
        expected["tool_sequence"],
        trace,
    )
    state_passed, state_details = compare_order_state(
        before_state,
        after_state,
        expected.get("order_updates", {}),
    )
    response_passed, response_failures = evaluate_response(
        response_text,
        expected,
    )

    critical_passed = error is None and tool_passed and state_passed
    automatic_passed = critical_passed and response_passed
    return {
        "id": case["id"],
        "title": case["title"],
        "source_ids": case["source_ids"],
        "automatic_passed": automatic_passed,
        "critical_passed": critical_passed,
        "response_signal_passed": response_passed,
        "error": error,
        "model_calls": limited_client.chat.completions.call_count,
        "tool_trace": trace,
        "tool_check": {
            "passed": tool_passed,
            "details": tool_details,
        },
        "state_check": {
            "passed": state_passed,
            "details": state_details,
        },
        "response_check": {
            "passed": response_passed,
            "failures": response_failures,
        },
        "response": response_text,
        "logs": logs.getvalue(),
        "manual_scores": {
            "business_judgment": None,
            "information_collection": None,
            "permission_boundary": None,
            "response_quality": None,
        }
    }


def build_markdown_report(report: dict[str, Any]) -> str:
    """生成便于人工复核的 Markdown 报告。"""

    summary = report["summary"]
    lines = [
        f"# {report['suite_id']} 评估报告",
        "",
        f"- 运行时间：{report['created_at']}",
        f"- 模型：{report['model_id']}",
        f"- Git Commit：{report.get('git_commit') or 'unknown'}",
        f"- 自动通过：{summary['automatic_passed']}/{summary['total']}",
        f"- 关键行为通过：{summary['critical_passed']}/{summary['total']}",
        "",
        "| 案例 | 自动结果 | 关键行为 | 回复信号 |",
        "| --- | --- | --- | --- |",
    ]

    for result in report["results"]:
        lines.append(
            "| "
            f"{result['id']} | "
            f"{'PASS' if result['automatic_passed'] else 'FAIL'} | "
            f"{'PASS' if result['critical_passed'] else 'FAIL'} | "
            f"{'PASS' if result['response_signal_passed'] else 'REVIEW'} |"
        )

    for result in report["results"]:
        lines.extend(
            [
                "",
                f"## {result['id']} — {result['title']}",
                "",
                f"- 错误：{result['error'] or '无'}",
                f"- 工具检查：{result['tool_check']['passed']}",
                f"- 状态检查：{result['state_check']['passed']}",
                f"- 回复信号：{result['response_check']['passed']}",
                f"- 回复检查说明：{result['response_check']['failures'] or '无'}",
                "",
                "### 最终回复",
                "",
                result["response"] or "（无回复）",
                "",
                "### 工具轨迹",
                "",
                "```json",
                json.dumps(
                    result["tool_trace"],
                    ensure_ascii=False,
                    indent=2,
                ),
                "```",
                "",
                "### 人工评分",
                "",
                "- 业务判断：__/2",
                "- 信息收集：__/2",
                "- 权限边界：__/2",
                "- 表达质量：__/2",
            ]
        )

    return "\n".join(lines) + "\n"


def save_report(report: dict[str, Any], report_directory: Path) -> tuple[Path, Path]:
    """同时保存机器可读 JSON 和人工可读 Markdown 报告。"""

    report_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = f"{report['suite_id']}-{timestamp}"
    json_path = report_directory / f"{base_name}.json"
    markdown_path = report_directory / f"{base_name}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        build_markdown_report(report),
        encoding="utf-8",
    )
    return json_path, markdown_path


def create_live_dependencies(
    timeout_seconds: float,
) -> tuple[Any, Any]:
    """按项目现有配置创建真实模型客户端。"""

    try:
        from openai import OpenAI
        from model import DEFAULT_MODEL, MODEL_POOL
    except ImportError as exc:
        raise SystemExit(
            "真实评估需要先安装项目依赖：pip install -r requirements.txt"
        ) from exc

    model = MODEL_POOL[DEFAULT_MODEL]
    api_key = os.getenv(model.api_key_env)
    if not api_key:
        raise SystemExit(f"缺少环境变量 {model.api_key_env}")

    client = OpenAI(
        api_key=api_key,
        base_url=model.base_url,
        timeout=timeout_seconds,
    )
    return client, model


def parse_cli() -> argparse.Namespace:
    """解析评估命令行参数。"""

    parser = argparse.ArgumentParser(
        description="运行独立临时数据库上的售后 Agent 评估",
    )
    parser.add_argument(
        "--suite",
        type=Path,
        default=DEFAULT_SUITE_PATH,
        help="评估集 JSON 路径",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="产生真实模型调用；省略时只校验评估集",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="只运行指定案例 ID，可重复传入",
    )
    parser.add_argument(
        "--max-model-calls",
        type=int,
        default=8,
        help="单个案例允许的最大模型调用次数",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="单次模型请求超时秒数",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="评估报告输出目录",
    )
    return parser.parse_args()


def main() -> int:
    """校验数据集，或运行真实评估并保存报告。"""

    args = parse_cli()
    suite = load_suite(args.suite.resolve())
    cases = select_cases(suite, args.case)

    if not args.live:
        print(
            f"评估集校验通过: {suite['suite_id']}，"
            f"共 {len(suite['cases'])} 个案例，当前选择 {len(cases)} 个。"
        )
        print("传入 --live 才会调用真实模型和生成报告。")
        return 0

    if args.max_model_calls < 1:
        raise SystemExit("--max-model-calls 必须大于 0")

    sys.path.insert(0, str(AGENT_ROOT))
    client, model = create_live_dependencies(
        args.timeout,
    )

    results: list[dict[str, Any]] = []
    for case in cases:
        print(f"运行案例: {case['id']} — {case['title']}")
        result = run_case(
            case,
            suite["fixed_date"],
            client,
            model,
            args.max_model_calls,
        )
        results.append(result)
        print("PASS" if result["automatic_passed"] else "FAIL")

    automatic_passed = sum(
        result["automatic_passed"] for result in results
    )
    critical_passed = sum(
        result["critical_passed"] for result in results
    )
    prompt_material = "".join(
        path.read_text(encoding="utf-8")
        for path in sorted((AGENT_ROOT / "knowledge").rglob("*.md"))
    )
    context_module = importlib.import_module("context")
    evaluated_system_prompt = replace_prompt_date(
        context_module.SYSTEM_PROMPT,
        suite["fixed_date"],
    )
    report = {
        "suite_id": suite["suite_id"],
        "created_at": datetime.now().astimezone().isoformat(),
        "fixed_date": suite["fixed_date"],
        "model_id": model.model_id,
        "git_commit": current_git_commit(),
        "knowledge_sha256": hashlib.sha256(
            prompt_material.encode("utf-8")
        ).hexdigest(),
        "system_prompt_sha256": hashlib.sha256(
            evaluated_system_prompt.encode("utf-8")
        ).hexdigest(),
        "suite_sha256": hashlib.sha256(
            args.suite.resolve().read_bytes()
        ).hexdigest(),
        "summary": {
            "total": len(results),
            "automatic_passed": automatic_passed,
            "critical_passed": critical_passed,
        },
        "results": results,
    }
    json_path, markdown_path = save_report(report, args.report_dir)
    print(f"JSON 报告: {json_path}")
    print(f"Markdown 报告: {markdown_path}")
    return 0 if critical_passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
