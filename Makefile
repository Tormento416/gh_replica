.PHONY: setup check test demo serve scaffold compose evidence offline-bundle

setup:
	uv sync --frozen

check:
	uv run --frozen python -m unittest discover -s tests -v
	uv run --frozen hyrlink validate
	git diff --check

test: check

demo:
	uv run --frozen hyrlink demo

serve:
	uv run --frozen hyrlink serve

scaffold:
	uv run --frozen hyrlink scaffold --output ../platform-modules --git

compose:
	uv run --frozen hyrlink compose --modules client-crm,recruiting --output .local/composition

evidence:
	uv run --frozen hyrlink verify --output docs/reports/verification.json --module-root ../platform-modules

offline-bundle:
	uv build
	uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file .local/requirements.txt
	python3 -m pip download --require-hashes --only-binary=:all: --requirement .local/requirements.txt --dest .local/wheelhouse
