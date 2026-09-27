from pathlib import Path
import unittest


WORKFLOW = Path(__file__).parent / "workflows" / "ci.yml"
TRUSTED_PR_RUNNER = (
    "${{ github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository && "
    "github.event.pull_request.user.login == github.repository_owner && github.actor == github.repository_owner && "
    "fromJSON(format('[\"self-hosted\", \"linux\", \"x64\", \"generic\", \"pr-{0}-{1}\"]', "
    "github.repository_id, github.event.pull_request.number)) || "
    "github.event_name == 'pull_request' && 'ubuntu-latest' || "
    "fromJSON('[\"self-hosted\", \"linux\", \"x64\", \"generic\"]') }}"
)
UNTRUSTED_CHECKOUT_CONDITION = (
    "github.event_name != 'pull_request' || "
    "github.event.pull_request.head.repo.full_name != github.repository || "
    "github.event.pull_request.user.login != github.repository_owner || "
    "github.actor != github.repository_owner"
)


def selected_runner(event, base_repo="moabualruz/crispy-iptv-tools", repository_id=123):
    if event["name"] == "pull_request":
        trusted = (
            event["head_repo"] == base_repo
            and event["author"] == "moabualruz"
            and event["actor"] == "moabualruz"
        )
        if trusted:
            return (
                "self-hosted:pr-"
                f"{repository_id}-{event['pr']}"
            )
        return "ubuntu-latest"
    return ["self-hosted", "linux", "x64", "generic"]


def job_runs(event):
    return event["name"] not in {"push", "workflow_dispatch"} or event["actor"] == "moabualruz"


def checkout_required(event):
    return not (
        event["name"] == "pull_request"
        and event["head_repo"] == "moabualruz/crispy-iptv-tools"
        and event["author"] == "moabualruz"
        and event["actor"] == "moabualruz"
    )


class RunnerRoutingTests(unittest.TestCase):
    def test_ci_uses_base_repo_identity_for_fork_routing(self):
        workflow = WORKFLOW.read_text()
        self.assertEqual(workflow.count(f"runs-on: {TRUSTED_PR_RUNNER}"), 2)
        runs_on = "\n".join(line for line in workflow.splitlines() if line.strip().startswith("runs-on:"))
        self.assertNotIn("github.event.pull_request.user.login !=", runs_on)
        self.assertIn("group: crispy-iptv-tools-pr-${{ github.event.pull_request.number || github.ref }}", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn(
            "github.event.pull_request.head.repo.full_name == github.repository",
            TRUSTED_PR_RUNNER,
        )

    def test_ci_prepares_once_then_reuses_source_in_parallel(self):
        workflow = WORKFLOW.read_text()
        gate = workflow.split("  gate:\n", maxsplit=1)[1]
        self.assertEqual(workflow.count("uses: actions/checkout@v4"), 1)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("    needs: prepare\n", gate)
        self.assertIn("gate: [fmt, clippy, test, doc, package]", gate)
        self.assertNotIn("uses: actions/checkout@v4", gate)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("actions/download-artifact@v4", gate)
        self.assertIn("cargo fetch", workflow)

    def test_trusted_pr_uses_host_prepared_tree_without_checkout_or_artifact(self):
        workflow = WORKFLOW.read_text()
        self.assertEqual(workflow.count(f"if: {UNTRUSTED_CHECKOUT_CONDITION}"), 5)
        event = {
            "name": "pull_request",
            "head_repo": "moabualruz/crispy-iptv-tools",
            "author": "moabualruz",
            "actor": "moabualruz",
            "pr": 2,
            "run": 44,
            "attempt": 1,
        }
        self.assertFalse(checkout_required(event))

    def test_fork_pr_runs_all_checks_on_hosted_runner_even_if_owner_authored(self):
        event = {
            "name": "pull_request",
            "head_repo": "contributor/crispy-iptv-tools",
            "author": "moabualruz",
            "actor": "moabualruz",
            "pr": 2,
            "run": 44,
            "attempt": 1,
        }
        self.assertTrue(job_runs(event))
        self.assertEqual(selected_runner(event), "ubuntu-latest")
        self.assertTrue(checkout_required(event))

    def test_non_owner_same_repo_pr_stays_hosted(self):
        event = {
            "name": "pull_request",
            "head_repo": "moabualruz/crispy-iptv-tools",
            "author": "contributor",
            "actor": "moabualruz",
            "pr": 2,
            "run": 44,
            "attempt": 1,
        }
        self.assertEqual(selected_runner(event), "ubuntu-latest")
        self.assertTrue(checkout_required(event))

    def test_owner_same_repo_pr_reuses_one_label_without_checkout(self):
        event = {
            "name": "pull_request",
            "head_repo": "moabualruz/crispy-iptv-tools",
            "author": "moabualruz",
            "actor": "moabualruz",
            "pr": 2,
            "run": 44,
            "attempt": 3,
        }
        self.assertEqual(selected_runner(event), "self-hosted:pr-123-2")
        retry = dict(event, run=99, attempt=4)
        self.assertEqual(selected_runner(retry), "self-hosted:pr-123-2")
        self.assertFalse(checkout_required(event))

    def test_only_owner_pushes_and_dispatches_run_on_existing_generic_pool(self):
        for event_name in ("push", "workflow_dispatch"):
            owner = {"name": event_name, "actor": "moabualruz"}
            other = {"name": event_name, "actor": "contributor"}
            self.assertTrue(job_runs(owner))
            self.assertEqual(selected_runner(owner), ["self-hosted", "linux", "x64", "generic"])
            self.assertFalse(job_runs(other))


if __name__ == "__main__":
    unittest.main()
