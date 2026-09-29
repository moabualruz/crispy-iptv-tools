# Mirrors .github/workflows/ci.yml
ci:
    python3 .github/test-ci-runner-routing.py
    cargo fmt --check
    cargo clippy --all-targets --all-features -- -D warnings
    cargo test --all-features
    cargo doc --no-deps
    cargo package
