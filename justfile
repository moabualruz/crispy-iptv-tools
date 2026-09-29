# Mirrors .github/workflows/ci.yml
ci:
    python3 .github/test-ci-runner-routing.py
    cargo fmt --check
    cargo clippy --locked --all-targets --all-features -- -D warnings
    cargo test --locked --all-features
    cargo doc --locked --no-deps
    cargo package --locked
