from pathlib import Path
import json
import re
import subprocess
import tempfile
from types import SimpleNamespace
import unittest


WORKFLOW = Path(__file__).parent / "workflows" / "ci.yml"


def job_block(workflow, name):
    jobs = workflow.split("jobs:\n", maxsplit=1)[1]
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)",
        jobs,
    )
    if not match:
        raise AssertionError(f"missing workflow job: {name}")
    return match.group(1)


def job_value(workflow, job, key):
    prefix = f"    {key}:"
    for line in job_block(workflow, job).splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    raise AssertionError(f"missing {key} value in {job}")


def step_value(workflow, job, step, key):
    lines = job_block(workflow, job).splitlines()
    start = next(
        index for index, line in enumerate(lines)
        if line in (f"      - name: {step}", f"      - uses: {step}")
    )
    for line in lines[start + 1:]:
        if line.startswith("      - "):
            break
        if line.startswith(f"        {key}:"):
            return line[len(f"        {key}:"):].strip()
    raise AssertionError(f"missing {key} in {job}.{step}")


def github_context(event):
    pull_request = SimpleNamespace(
        head=SimpleNamespace(
            repo=SimpleNamespace(full_name=event.get("head_repo", ""))
        ),
        user=SimpleNamespace(login=event.get("author", "")),
        number=event.get("pr", 0),
    )
    return SimpleNamespace(
        actor=event["actor"],
        event_name=event["name"],
        event=SimpleNamespace(pull_request=pull_request),
        ref=event.get("ref", "refs/heads/main"),
        repository="moabualruz/crispy-iptv-tools",
        repository_id=event.get("repository_id", 123),
        repository_owner="moabualruz",
    )


def evaluate_workflow_expression(expression, event):
    expression = expression.strip()
    if expression.startswith("${{") and expression.endswith("}}"):
        expression = expression[3:-2].strip()
    expression = expression.replace("&&", " and ").replace("||", " or ")
    return eval(
        expression,
        {
            "__builtins__": {},
            "github": github_context(event),
            "fromJSON": json.loads,
            "format": lambda template, *values: template.format(*values),
        },
        {},
    )


def selected_runner(event):
    workflow = WORKFLOW.read_text()
    return evaluate_workflow_expression(
        job_value(workflow, "prepare", "runs-on"), event
    )


def job_runs(event):
    workflow = WORKFLOW.read_text()
    return bool(
        evaluate_workflow_expression(job_value(workflow, "prepare", "if"), event)
    )


def checkout_required(event):
    workflow = WORKFLOW.read_text()
    return bool(
        evaluate_workflow_expression(
            step_value(workflow, "prepare", "actions/checkout@v4", "if"), event
        )
    )


def step_script(workflow, job, name):
    lines = job_block(workflow, job).splitlines()
    start = lines.index(f"      - name: {name}")
    run_index = next(
        index for index in range(start + 1, len(lines))
        if lines[index].startswith("        run:")
    )
    if lines[run_index] != "        run: |":
        return lines[run_index].removeprefix("        run: ")
    script = []
    for line in lines[run_index + 1:]:
        if line and not line.startswith("          "):
            break
        script.append(line[10:] if line.startswith("          ") else "")
    return "\n".join(script)


class RunnerRoutingTests(unittest.TestCase):
    def test_actual_runner_expression_routes_trusted_fork_and_push_events(self):
        workflow = WORKFLOW.read_text()
        prepare_runner = job_value(workflow, "prepare", "runs-on")
        gate_runner = job_value(workflow, "gate", "runs-on")
        self.assertEqual(prepare_runner, gate_runner)

        trusted = {
            "name": "pull_request",
            "head_repo": "moabualruz/crispy-iptv-tools",
            "author": "moabualruz",
            "actor": "moabualruz",
            "pr": 2,
            "repository_id": 123,
        }
        self.assertEqual(
            selected_runner(trusted),
            ["self-hosted", "linux", "x64", "generic", "pr-123-2"],
        )

        fork = dict(trusted, head_repo="contributor/crispy-iptv-tools")
        self.assertEqual(selected_runner(fork), "ubuntu-latest")

        non_owner = dict(trusted, author="contributor")
        self.assertEqual(selected_runner(non_owner), "ubuntu-latest")

        push = {"name": "push", "actor": "moabualruz", "repository_id": 123}
        self.assertEqual(
            selected_runner(push), ["self-hosted", "linux", "x64", "generic"]
        )

    def test_actual_job_and_checkout_conditions_route_forks_and_non_owner_prs(self):
        owner = {
            "name": "pull_request",
            "head_repo": "moabualruz/crispy-iptv-tools",
            "author": "moabualruz",
            "actor": "moabualruz",
            "pr": 2,
        }
        self.assertTrue(job_runs(owner))
        self.assertFalse(checkout_required(owner))

        fork = dict(owner, head_repo="contributor/crispy-iptv-tools")
        self.assertTrue(job_runs(fork))
        self.assertTrue(checkout_required(fork))

        non_owner = dict(owner, author="contributor")
        self.assertTrue(job_runs(non_owner))
        self.assertTrue(checkout_required(non_owner))

        non_owner_push = {"name": "push", "actor": "contributor"}
        self.assertFalse(job_runs(non_owner_push))

    def test_prepare_and_each_matrix_gate_check_head_against_event_sha(self):
        workflow = WORKFLOW.read_text()
        self.assertIn("gate: [fmt, clippy, test, doc, package]", job_block(workflow, "gate"))
        scripts = [
            step_script(workflow, job, "Verify checkout matches GITHUB_SHA")
            for job in ("prepare", "gate")
        ]
        with tempfile.TemporaryDirectory() as repository:
            subprocess.run(["git", "init", "-q", repository], check=True)
            subprocess.run(["git", "-C", repository, "config", "user.name", "CI contract"], check=True)
            subprocess.run(["git", "-C", repository, "config", "user.email", "ci-contract@example.invalid"], check=True)
            Path(repository, "source.txt").write_text("workflow source\n")
            subprocess.run(["git", "-C", repository, "add", "source.txt"], check=True)
            subprocess.run(["git", "-C", repository, "commit", "-qm", "fixture"], check=True)
            sha = subprocess.run(
                ["git", "-C", repository, "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            for script in scripts:
                subprocess.run(
                    ["bash", "-e", "-c", script],
                    cwd=repository,
                    env={"GITHUB_SHA": sha},
                    check=True,
                )
                mismatch = subprocess.run(
                    ["bash", "-e", "-c", script],
                    cwd=repository,
                    env={"GITHUB_SHA": "0" * 40},
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(mismatch.returncode, 0)

    def test_required_aggregate_fails_when_any_job_fails(self):
        workflow = WORKFLOW.read_text()
        aggregate = job_block(workflow, "required")
        self.assertEqual(job_value(workflow, "required", "if"), "${{ always() }}")
        self.assertEqual(job_value(workflow, "required", "runs-on"), "ubuntu-latest")
        self.assertEqual(
            job_value(workflow, "required", "needs"), "[prepare, gate]"
        )
        script = step_script(workflow, "required", "Require all CI gates to pass")
        for result in ("failure", "cancelled", "skipped"):
            completed = subprocess.run(
                ["bash", "-e", "-o", "pipefail", "-c", script],
                env={"PREPARE_RESULT": "success", "GATE_RESULT": result},
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0, aggregate)
        success = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", script],
            env={"PREPARE_RESULT": "success", "GATE_RESULT": "success"},
        )
        self.assertEqual(success.returncode, 0)

    def test_required_aggregate_tolerates_only_intentional_skips(self):
        workflow = WORKFLOW.read_text()
        script = step_script(workflow, "required", "Require all CI gates to pass")

        def run(event, actor, prepare, gate):
            return subprocess.run(
                ["bash", "-e", "-o", "pipefail", "-c", script],
                env={
                    "PREPARE_RESULT": prepare, "GATE_RESULT": gate,
                    "EVENT_NAME": event, "ACTOR": actor, "OWNER": "moabualruz",
                },
                capture_output=True,
                text=True,
            ).returncode

        self.assertEqual(run("push", "contributor", "skipped", "skipped"), 0)
        self.assertEqual(run("workflow_dispatch", "contributor", "skipped", "skipped"), 0)
        self.assertNotEqual(run("push", "moabualruz", "skipped", "skipped"), 0)
        self.assertNotEqual(run("pull_request", "contributor", "skipped", "skipped"), 0)
        self.assertNotEqual(run("push", "contributor", "success", "failure"), 0)

    def test_gate_condition_runs_for_prs_and_owner_pushes_only(self):
        workflow = WORKFLOW.read_text()
        condition = job_value(workflow, "gate", "if")
        for event, expected in [
            ({"name": "pull_request", "actor": "contributor"}, True),
            ({"name": "push", "actor": "moabualruz"}, True),
            ({"name": "push", "actor": "contributor"}, False),
            ({"name": "workflow_dispatch", "actor": "contributor"}, False),
        ]:
            self.assertEqual(bool(evaluate_workflow_expression(condition, event)), expected, event)


if __name__ == "__main__":
    unittest.main()
