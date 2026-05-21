REGISTRY ?= docker.xkqq.top
IMAGE_NAME ?= xingqiux/hermes-agent
IMAGE ?= $(REGISTRY)/$(IMAGE_NAME)
REF ?= main
PLATFORM ?= linux/amd64
REMOTE ?= xkqq
REMOTE_DIR ?= /home/ziyu/services/hermes-agent
REMOTE_DATA_DIR ?= /home/ziyu/services/hermes-agent-data
REMOTE_UID ?= 1001
REMOTE_GID ?= 1001
force ?= 0
FORCE ?= $(force)

COMMIT = $(shell git rev-parse HEAD)
SHORT_COMMIT = $(shell git rev-parse --short HEAD)
TAG ?= $(SHORT_COMMIT)

.PHONY: help status check-clean pull build push publish deploy update

help:
	@echo "Hermes localized Docker workflow"
	@echo "  make status   - show git and image settings"
	@echo "  make pull     - fetch/rebase $(REF) from origin"
	@echo "  make build    - build $(IMAGE):$(TAG) and :latest for $(PLATFORM)"
	@echo "  make push     - push $(IMAGE):$(TAG) and :latest"
	@echo "  make publish  - build and push"
	@echo "  make deploy   - copy compose to $(REMOTE), pull image, docker compose up -d"
	@echo "  make update   - pull remote changes, publish and deploy only when code changed"
	@echo "  make update FORCE=1 - rebuild, push, and deploy even when source is current"
	@echo "                         also accepts lowercase: make update force=1"

status:
	@git status --short --branch
	@echo "IMAGE=$(IMAGE)"
	@echo "TAG=$(TAG)"
	@echo "COMMIT=$(COMMIT)"
	@echo "PLATFORM=$(PLATFORM)"
	@echo "REMOTE=$(REMOTE):$(REMOTE_DIR)"

check-clean:
	@test -z "$$(git status --porcelain)" || (git status --short && echo "Working tree must be clean for this target." >&2 && exit 1)

pull: check-clean
	git fetch origin $(REF)
	git rebase origin/$(REF)

build:
	docker buildx build \
		--platform $(PLATFORM) \
		--build-arg HERMES_BUILD_COMMIT=$(COMMIT) \
		--build-arg HERMES_BUILD_REF=$(REF) \
		--build-arg HERMES_BUILD_REMOTE=https://github.com/xingqiux/hermes-agent.git \
		-t $(IMAGE):$(TAG) \
		-t $(IMAGE):latest \
		--load \
		.

push:
	docker push $(IMAGE):$(TAG)
	docker push $(IMAGE):latest

publish: build push

deploy:
	ssh $(REMOTE) 'mkdir -p $(REMOTE_DIR) $(REMOTE_DATA_DIR)'
	scp docker-compose.xkqq.yml $(REMOTE):$(REMOTE_DIR)/docker-compose.yml
	ssh $(REMOTE) 'cd $(REMOTE_DIR) && HERMES_IMAGE=$(IMAGE):latest HERMES_DATA_DIR=$(REMOTE_DATA_DIR) HERMES_UID=$(REMOTE_UID) HERMES_GID=$(REMOTE_GID) docker compose pull && HERMES_IMAGE=$(IMAGE):latest HERMES_DATA_DIR=$(REMOTE_DATA_DIR) HERMES_UID=$(REMOTE_UID) HERMES_GID=$(REMOTE_GID) docker compose up -d'

update:
	@set -e; \
	dirty=$$(git status --porcelain); \
	before=$$(git rev-parse HEAD); \
	git fetch origin $(REF); \
	if [ -n "$$dirty" ]; then \
		echo "Working tree has local changes; skipping git rebase and publishing the current workspace."; \
		git status --short; \
		behind=$$(git rev-list --count HEAD..origin/$(REF) 2>/dev/null || echo 0); \
		if [ "$$behind" != "0" ]; then \
			echo "Warning: origin/$(REF) is $$behind commit(s) ahead; clean or commit local changes to rebase first."; \
		fi; \
		after=$$before; \
	else \
		git rebase origin/$(REF); \
		after=$$(git rev-parse HEAD); \
	fi; \
	if [ -z "$$dirty" ] && [ "$$before" = "$$after" ]; then \
		case "$(FORCE)" in \
			1|true|TRUE|yes|YES|on|ON) \
				echo "No code updates on origin/$(REF), but FORCE=$(FORCE); publishing current source."; \
				;; \
			*) \
				echo "No code updates on origin/$(REF); skipping build, push, and deploy."; \
				exit 0; \
				;; \
		esac; \
	fi; \
	tag=$$(git rev-parse --short HEAD); \
	commit=$$(git rev-parse HEAD); \
	if [ -n "$$dirty" ]; then \
		tag="$${tag}-dirty"; \
		commit="$${commit}-dirty"; \
		echo "Publishing dirty workspace as $(IMAGE):$$tag and :latest"; \
	elif [ "$$before" = "$$after" ]; then \
		echo "Publishing $(IMAGE):$$tag and :latest"; \
	else \
		echo "Updated $$before..$$after; publishing $(IMAGE):$$tag and :latest"; \
	fi; \
	$(MAKE) publish COMMIT=$$commit TAG=$$tag; \
	$(MAKE) deploy TAG=$$tag
